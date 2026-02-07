"""API routes for meal plan generation and management."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from foodplanner.database import get_db
from foodplanner.graph.database import get_graph_db
from foodplanner.graph.service import GraphService
from foodplanner.logging_config import get_logger
from foodplanner.models import MealPlan, MealPlanRecipe, User
from foodplanner.plan.optimizer import DietaryPreference, MealPlanOptimizer
from foodplanner.plan.shopping_list import ShoppingListGenerator

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/meal-plans", tags=["meal-plans"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class DietaryPreferenceSchema(BaseModel):
    """Dietary preference for meal planning."""

    name: str
    type: str = Field(description="Type: allergy, preference, or restriction")


class MealPlanCreateRequest(BaseModel):
    """Request to generate a new meal plan."""

    user_id: str = Field(default="default-user")
    store_ids: list[str] = Field(default_factory=list, description="Preferred store IDs")
    start_date: date
    end_date: date
    people_count: int = Field(ge=1, le=20, default=2)
    dietary_preferences: list[DietaryPreferenceSchema] = Field(default_factory=list)
    budget_max: float | None = Field(None, description="Maximum budget in DKK")
    on_hand_ingredients: list[str] = Field(default_factory=list)
    preselected_recipe_ids: list[str] = Field(default_factory=list)


class MealPlanUpdateRequest(BaseModel):
    """Request to update an existing meal plan."""

    meals: list["MealSlotUpdate"] | None = None


class MealSlotUpdate(BaseModel):
    """Update a single meal slot in the plan."""

    scheduled_date: date
    meal_type: str = Field(description="breakfast, lunch, or dinner")
    recipe_id: str | None = Field(None, description="Recipe ID or null to clear slot")
    is_locked: bool = False


class RecipeInPlan(BaseModel):
    """Recipe as it appears in a meal plan."""

    id: str
    name: str
    thumbnail: str | None = None
    scheduled_date: date
    meal_type: str
    servings: int
    estimated_cost: float | None = None
    estimated_savings: float | None = None
    is_locked: bool = False
    suggestion_reason: str | None = None
    discounted_ingredients: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class MealPlanResponse(BaseModel):
    """Meal plan response with all recipes."""

    id: str
    user_id: str
    start_date: date
    end_date: date
    people_count: int
    total_cost: float
    total_savings: float
    recipes: list[RecipeInPlan]
    created_at: str

    class Config:
        from_attributes = True


class MealPlanListResponse(BaseModel):
    """Paginated list of meal plans."""

    plans: list[MealPlanResponse]
    total: int


class ShoppingListItem(BaseModel):
    """Single item in the shopping list."""

    ingredient_name: str
    normalized_name: str = ""
    quantity: str
    unit: str
    recipe_sources: list[str] = Field(default_factory=list)

    # Product match info
    product_name: str | None = None
    product_id: str | None = None
    product_brand: str | None = None
    price: float | None = None
    discount_price: float | None = None
    store_id: str | None = None
    store_name: str | None = None
    category: str | None = None

    # Match metadata
    match_confidence: float | None = None
    alternative_products: list[str] = Field(default_factory=list)


class ShoppingListResponse(BaseModel):
    """Aggregated shopping list for a meal plan."""

    meal_plan_id: str
    items: list[ShoppingListItem]
    total_cost: float
    total_savings: float
    matched_items_count: int = 0
    unmatched_items_count: int = 0
    items_by_category: dict[str, list[ShoppingListItem]]
    items_by_store: dict[str, list[ShoppingListItem]] = Field(default_factory=dict)


# =============================================================================
# Helper Functions
# =============================================================================


async def get_or_create_user(db: AsyncSession, user_id: str) -> User:
    """Get existing user or create a placeholder."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            id=user_id,
            email=f"{user_id}@placeholder.local",
            hashed_password="placeholder",
        )
        db.add(user)
        await db.flush()

    return user


async def get_graph_service() -> GraphService:
    """Get graph service instance."""
    db = await get_graph_db()
    return GraphService(db)


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/", response_model=MealPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_meal_plan(
    request: MealPlanCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> MealPlanResponse:
    """
    Generate a new meal plan based on preferences.

    The plan will include one dinner recipe per day within the date range,
    optimized for cost savings using discounted products where possible.
    Uses the MealPlanOptimizer for intelligent recipe selection.
    """
    from datetime import timedelta

    logger.info(
        f"Creating meal plan: {request.start_date} to {request.end_date}, "
        f"people={request.people_count}"
    )

    # Validate date range
    if request.end_date < request.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be after start_date",
        )

    days_count = (request.end_date - request.start_date).days + 1
    if days_count > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum plan duration is 30 days",
        )

    # Ensure user exists
    await get_or_create_user(db, request.user_id)

    # Convert dietary preferences to optimizer format
    dietary_prefs = [
        DietaryPreference(name=p.name, type=p.type) for p in request.dietary_preferences
    ]

    # Use optimizer for intelligent recipe selection
    total_cost = 0.0
    total_savings = 0.0
    recipes_in_plan: list[RecipeInPlan] = []

    try:
        graph_service = await get_graph_service()
        optimizer = MealPlanOptimizer(graph_service)

        optimized_recipes = await optimizer.optimize(
            days=days_count,
            people_count=request.people_count,
            store_ids=request.store_ids if request.store_ids else None,
            dietary_preferences=dietary_prefs if dietary_prefs else None,
            budget_max=request.budget_max,
            excluded_recipe_ids=None,
        )

        # Assign optimized recipes to days
        for i, opt_recipe in enumerate(optimized_recipes):
            scheduled_date = request.start_date + timedelta(days=i)

            recipes_in_plan.append(
                RecipeInPlan(
                    id=opt_recipe.recipe_id,
                    name=opt_recipe.recipe_name,
                    thumbnail=opt_recipe.thumbnail,
                    scheduled_date=scheduled_date,
                    meal_type="dinner",
                    servings=request.people_count,
                    estimated_cost=opt_recipe.estimated_cost,
                    estimated_savings=opt_recipe.estimated_savings,
                    is_locked=False,
                    suggestion_reason=opt_recipe.suggestion_reason,
                    discounted_ingredients=opt_recipe.discounted_ingredients,
                )
            )

            total_cost += opt_recipe.estimated_cost
            total_savings += opt_recipe.estimated_savings

        logger.info(f"Optimizer selected {len(optimized_recipes)} recipes")

    except Exception as e:
        logger.warning(f"Optimizer failed: {e}, falling back to simple selection")
        # Fallback to simple recipe selection if optimizer fails
        try:
            graph_service = await get_graph_service()
            recipes = await graph_service.search_recipes(limit=days_count)

            for i, recipe in enumerate(recipes):
                scheduled_date = request.start_date + timedelta(days=i)
                recipes_in_plan.append(
                    RecipeInPlan(
                        id=recipe.id,
                        name=recipe.name,
                        thumbnail=recipe.thumbnail,
                        scheduled_date=scheduled_date,
                        meal_type="dinner",
                        servings=request.people_count,
                        estimated_cost=None,
                        estimated_savings=None,
                        is_locked=False,
                        suggestion_reason="Random selection (optimizer unavailable)",
                        discounted_ingredients=[],
                    )
                )
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")

    # Create the meal plan
    plan_id = str(uuid.uuid4())

    meal_plan = MealPlan(
        id=plan_id,
        user_id=request.user_id,
        start_date=request.start_date,
        end_date=request.end_date,
        total_cost=total_cost,
        plan_metadata={
            "people_count": request.people_count,
            "total_savings": total_savings,
            "dietary_preferences": [p.model_dump() for p in request.dietary_preferences],
            "store_ids": request.store_ids,
        },
    )
    db.add(meal_plan)

    # Add meal plan recipes
    for recipe_in_plan in recipes_in_plan:
        meal_plan_recipe = MealPlanRecipe(
            meal_plan_id=plan_id,
            recipe_id=recipe_in_plan.id,
            scheduled_date=recipe_in_plan.scheduled_date,
            meal_type=recipe_in_plan.meal_type,
        )
        db.add(meal_plan_recipe)

    await db.commit()

    logger.info(f"Created meal plan {plan_id} with {len(recipes_in_plan)} recipes")

    return MealPlanResponse(
        id=plan_id,
        user_id=request.user_id,
        start_date=request.start_date,
        end_date=request.end_date,
        people_count=request.people_count,
        total_cost=total_cost,
        total_savings=total_savings,
        recipes=recipes_in_plan,
        created_at=meal_plan.created_at.isoformat(),
    )


@router.get("/", response_model=MealPlanListResponse)
async def list_meal_plans(
    user_id: Annotated[str, Query(description="Filter by user ID")] = "default-user",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: AsyncSession = Depends(get_db),
) -> MealPlanListResponse:
    """List meal plans for a user."""
    logger.info(f"Listing meal plans for user {user_id}")

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.user_id == user_id)
        .options(selectinload(MealPlan.recipes))
        .order_by(MealPlan.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    plans = result.scalars().all()

    plan_responses = []
    for plan in plans:
        people_count = plan.plan_metadata.get("people_count", 2) if plan.plan_metadata else 2
        total_savings = plan.plan_metadata.get("total_savings", 0.0) if plan.plan_metadata else 0.0

        recipes_in_plan = [
            RecipeInPlan(
                id=mpr.recipe_id,
                name=mpr.recipe.name if mpr.recipe else "Unknown",
                thumbnail=None,
                scheduled_date=mpr.scheduled_date,
                meal_type=mpr.meal_type,
                servings=people_count,
                estimated_cost=None,
                estimated_savings=None,
                is_locked=False,
            )
            for mpr in plan.recipes
        ]

        plan_responses.append(
            MealPlanResponse(
                id=plan.id,
                user_id=plan.user_id,
                start_date=plan.start_date,
                end_date=plan.end_date,
                people_count=people_count,
                total_cost=plan.total_cost,
                total_savings=total_savings,
                recipes=recipes_in_plan,
                created_at=plan.created_at.isoformat(),
            )
        )

    return MealPlanListResponse(plans=plan_responses, total=len(plan_responses))


@router.get("/{plan_id}", response_model=MealPlanResponse)
async def get_meal_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
) -> MealPlanResponse:
    """Get a specific meal plan by ID."""
    logger.info(f"Fetching meal plan {plan_id}")

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.recipes).selectinload(MealPlanRecipe.recipe))
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal plan {plan_id} not found",
        )

    people_count = plan.plan_metadata.get("people_count", 2) if plan.plan_metadata else 2
    total_savings = plan.plan_metadata.get("total_savings", 0.0) if plan.plan_metadata else 0.0

    recipes_in_plan = [
        RecipeInPlan(
            id=mpr.recipe_id,
            name=mpr.recipe.name if mpr.recipe else "Unknown",
            thumbnail=None,
            scheduled_date=mpr.scheduled_date,
            meal_type=mpr.meal_type,
            servings=people_count,
            estimated_cost=None,
            estimated_savings=None,
            is_locked=False,
        )
        for mpr in plan.recipes
    ]

    return MealPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        start_date=plan.start_date,
        end_date=plan.end_date,
        people_count=people_count,
        total_cost=plan.total_cost,
        total_savings=total_savings,
        recipes=recipes_in_plan,
        created_at=plan.created_at.isoformat(),
    )


@router.patch("/{plan_id}", response_model=MealPlanResponse)
async def update_meal_plan(
    plan_id: str,
    request: MealPlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> MealPlanResponse:
    """
    Update a meal plan by swapping or removing meals.

    Allows updating individual meal slots without regenerating the entire plan.
    """
    logger.info(f"Updating meal plan {plan_id}")

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.recipes).selectinload(MealPlanRecipe.recipe))
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal plan {plan_id} not found",
        )

    if request.meals:
        for meal_update in request.meals:
            # Find existing meal for this date/type
            existing = None
            for mpr in plan.recipes:
                if (
                    mpr.scheduled_date == meal_update.scheduled_date
                    and mpr.meal_type == meal_update.meal_type
                ):
                    existing = mpr
                    break

            if meal_update.recipe_id is None:
                # Remove meal
                if existing:
                    await db.delete(existing)
            elif existing:
                # Update existing
                existing.recipe_id = meal_update.recipe_id
            else:
                # Add new
                new_mpr = MealPlanRecipe(
                    meal_plan_id=plan_id,
                    recipe_id=meal_update.recipe_id,
                    scheduled_date=meal_update.scheduled_date,
                    meal_type=meal_update.meal_type,
                )
                db.add(new_mpr)

    await db.commit()
    await db.refresh(plan)

    # Re-fetch with updated data
    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.recipes).selectinload(MealPlanRecipe.recipe))
    )
    plan = result.scalar_one()

    people_count = plan.plan_metadata.get("people_count", 2) if plan.plan_metadata else 2
    total_savings = plan.plan_metadata.get("total_savings", 0.0) if plan.plan_metadata else 0.0

    recipes_in_plan = [
        RecipeInPlan(
            id=mpr.recipe_id,
            name=mpr.recipe.name if mpr.recipe else "Unknown",
            thumbnail=None,
            scheduled_date=mpr.scheduled_date,
            meal_type=mpr.meal_type,
            servings=people_count,
            estimated_cost=None,
            estimated_savings=None,
            is_locked=False,
        )
        for mpr in plan.recipes
    ]

    return MealPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        start_date=plan.start_date,
        end_date=plan.end_date,
        people_count=people_count,
        total_cost=plan.total_cost,
        total_savings=total_savings,
        recipes=recipes_in_plan,
        created_at=plan.created_at.isoformat(),
    )


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a meal plan."""
    logger.info(f"Deleting meal plan {plan_id}")

    result = await db.execute(select(MealPlan).where(MealPlan.id == plan_id))
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal plan {plan_id} not found",
        )

    await db.delete(plan)
    await db.commit()


@router.get("/{plan_id}/shopping-list", response_model=ShoppingListResponse)
async def get_shopping_list(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
) -> ShoppingListResponse:
    """
    Get aggregated shopping list for a meal plan.

    Combines ingredients from all recipes with proper quantity aggregation,
    unit normalization, and product matching with confidence scores.
    """
    logger.info(f"Generating shopping list for plan {plan_id}")

    result = await db.execute(
        select(MealPlan)
        .where(MealPlan.id == plan_id)
        .options(selectinload(MealPlan.recipes).selectinload(MealPlanRecipe.recipe))
    )
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Meal plan {plan_id} not found",
        )

    # Get store IDs from plan metadata
    store_ids = None
    if plan.plan_metadata:
        store_ids = plan.plan_metadata.get("store_ids")

    # Use ShoppingListGenerator for proper aggregation
    try:
        graph_service = await get_graph_service()
        generator = ShoppingListGenerator(graph_service)
        shopping_list = await generator.generate_from_db_plan(plan, store_ids)

        # Convert to response format
        items = [
            ShoppingListItem(
                ingredient_name=item.ingredient_name,
                normalized_name=item.normalized_name,
                quantity=item.quantity,
                unit=item.unit,
                recipe_sources=item.recipe_sources,
                product_name=item.product_name,
                product_id=item.product_id,
                product_brand=item.product_brand,
                price=item.price,
                discount_price=item.discount_price,
                store_id=item.store_id,
                store_name=item.store_name,
                category=item.category,
                match_confidence=item.match_confidence,
                alternative_products=item.alternative_products,
            )
            for item in shopping_list.items
        ]

        # Convert category grouping
        items_by_category: dict[str, list[ShoppingListItem]] = {}
        for cat, cat_items in shopping_list.items_by_category.items():
            items_by_category[cat] = [
                ShoppingListItem(
                    ingredient_name=item.ingredient_name,
                    normalized_name=item.normalized_name,
                    quantity=item.quantity,
                    unit=item.unit,
                    recipe_sources=item.recipe_sources,
                    product_name=item.product_name,
                    product_id=item.product_id,
                    product_brand=item.product_brand,
                    price=item.price,
                    discount_price=item.discount_price,
                    store_id=item.store_id,
                    store_name=item.store_name,
                    category=item.category,
                    match_confidence=item.match_confidence,
                    alternative_products=item.alternative_products,
                )
                for item in cat_items
            ]

        # Convert store grouping
        items_by_store: dict[str, list[ShoppingListItem]] = {}
        for store, store_items in shopping_list.items_by_store.items():
            items_by_store[store] = [
                ShoppingListItem(
                    ingredient_name=item.ingredient_name,
                    normalized_name=item.normalized_name,
                    quantity=item.quantity,
                    unit=item.unit,
                    recipe_sources=item.recipe_sources,
                    product_name=item.product_name,
                    product_id=item.product_id,
                    product_brand=item.product_brand,
                    price=item.price,
                    discount_price=item.discount_price,
                    store_id=item.store_id,
                    store_name=item.store_name,
                    category=item.category,
                    match_confidence=item.match_confidence,
                    alternative_products=item.alternative_products,
                )
                for item in store_items
            ]

        return ShoppingListResponse(
            meal_plan_id=plan_id,
            items=items,
            total_cost=shopping_list.total_cost,
            total_savings=shopping_list.total_savings,
            matched_items_count=shopping_list.matched_items_count,
            unmatched_items_count=shopping_list.unmatched_items_count,
            items_by_category=items_by_category,
            items_by_store=items_by_store,
        )

    except Exception as e:
        logger.error(f"Shopping list generation failed: {e}")
        # Fallback to basic list without aggregation
        return ShoppingListResponse(
            meal_plan_id=plan_id,
            items=[],
            total_cost=0.0,
            total_savings=0.0,
            matched_items_count=0,
            unmatched_items_count=0,
            items_by_category={},
            items_by_store={},
        )
