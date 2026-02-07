"""API routes for recipes and ingredients from the knowledge graph."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from foodplanner.graph.database import get_graph_db
from foodplanner.graph.matching import IngredientMatcher
from foodplanner.graph.models import (
    AreaNode,
    CategoryNode,
    IngredientNode,
    RecipeSearchResult,
    RecipeWithIngredients,
)
from foodplanner.graph.service import GraphService
from foodplanner.logging_config import get_logger
from foodplanner.tasks.graph_ingestion import (
    compute_ingredient_matches_task,
    full_graph_refresh_task,
    ingest_mealdb_recipes_task,
    sync_products_to_graph_task,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["recipes"])


# Request/Response schemas
class RecipeListResponse(BaseModel):
    """Paginated list of recipes."""

    recipes: list[RecipeWithIngredients]
    total: int
    offset: int
    limit: int


class RecipeResponse(BaseModel):
    """Single recipe response."""

    recipe: RecipeWithIngredients


class IngredientResponse(BaseModel):
    """Single ingredient with optional matched products."""

    name: str
    normalized_name: str
    description: str | None = None
    products: list[dict[str, Any]] = Field(default_factory=list)


class IngredientListResponse(BaseModel):
    """List of ingredients."""

    ingredients: list[IngredientNode]
    total: int


class CategoryListResponse(BaseModel):
    """List of categories."""

    categories: list[CategoryNode]
    total: int


class AreaListResponse(BaseModel):
    """List of areas/cuisines."""

    areas: list[AreaNode]
    total: int


class RecipeCostEstimate(BaseModel):
    """Cost estimate for a recipe."""

    recipe_id: str
    recipe_name: str
    items: list[dict[str, Any]]
    total_cost: float
    total_savings: float


class DiscountRecipesResponse(BaseModel):
    """Recipes sorted by discount opportunities."""

    recipes: list[RecipeSearchResult]
    total: int


class GraphStatsResponse(BaseModel):
    """Graph database statistics."""

    recipes: int = 0
    ingredients: int = 0
    products: int = 0
    categories: int = 0
    areas: int = 0
    stores: int = 0
    matches: int = 0


class TaskTriggerResponse(BaseModel):
    """Response when triggering a background task."""

    task_id: str
    status: str
    message: str


class IngredientMatchRequest(BaseModel):
    """Request to match an ingredient to products."""

    ingredient_name: str
    top_k: int = Field(default=5, ge=1, le=20)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class IngredientMatchResponse(BaseModel):
    """Response with matched products for an ingredient."""

    ingredient_name: str
    matches: list[dict[str, Any]]
    total: int


# Dependency to get graph service
async def get_graph_service() -> GraphService:
    """Get graph service instance."""
    db = await get_graph_db()
    return GraphService(db)


# =============================================================================
# Recipe Endpoints
# =============================================================================


@router.get("/recipes", response_model=RecipeListResponse)
async def list_recipes(
    name: Annotated[str | None, Query(description="Filter by recipe name")] = None,
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    area: Annotated[str | None, Query(description="Filter by area/cuisine")] = None,
    ingredient: Annotated[str | None, Query(description="Filter by ingredient")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Max recipes to return")] = 20,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    service: GraphService = Depends(get_graph_service),
) -> RecipeListResponse:
    """
    List recipes with optional filters.

    Filter by name (partial match), category, area/cuisine, or ingredient.
    Results are paginated.
    """
    logger.info(
        f"Listing recipes: name={name}, category={category}, "
        f"area={area}, ingredient={ingredient}, limit={limit}, offset={offset}"
    )

    try:
        recipes = await service.search_recipes(
            name=name,
            category=category,
            area=area,
            ingredient=ingredient,
            limit=limit,
            offset=offset,
        )

        return RecipeListResponse(
            recipes=recipes,
            total=len(recipes),  # Would need separate count query for accurate total
            offset=offset,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to list recipes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recipes from graph database",
        )


@router.get("/recipes/by-discounts", response_model=DiscountRecipesResponse)
async def get_recipes_by_discounts(
    min_discounted: Annotated[
        int, Query(ge=1, le=20, description="Minimum discounted ingredients")
    ] = 1,
    limit: Annotated[int, Query(ge=1, le=50, description="Max recipes to return")] = 20,
    service: GraphService = Depends(get_graph_service),
) -> DiscountRecipesResponse:
    """
    Find recipes that use currently discounted products.

    Returns recipes sorted by the number of ingredients that have active discounts,
    helping users save money by cooking with discounted items.
    """
    logger.info(f"Finding discount-optimized recipes: min={min_discounted}, limit={limit}")

    try:
        recipes = await service.find_recipes_with_discounts(
            min_discounted_ingredients=min_discounted,
            limit=limit,
        )

        return DiscountRecipesResponse(
            recipes=recipes,
            total=len(recipes),
        )
    except Exception as e:
        logger.error(f"Failed to find discount recipes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch discount-optimized recipes",
        )


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: str,
    service: GraphService = Depends(get_graph_service),
) -> RecipeResponse:
    """Get a specific recipe with all its ingredients."""
    logger.info(f"Fetching recipe: {recipe_id}")

    try:
        recipe = await service.get_recipe(recipe_id)

        if not recipe:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recipe {recipe_id} not found",
            )

        return RecipeResponse(recipe=recipe)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch recipe {recipe_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recipe from graph database",
        )


@router.get("/recipes/{recipe_id}/cost", response_model=RecipeCostEstimate)
async def estimate_recipe_cost(
    recipe_id: str,
    prefer_discounts: Annotated[
        bool, Query(description="Prefer discounted products when available")
    ] = True,
    service: GraphService = Depends(get_graph_service),
) -> RecipeCostEstimate:
    """
    Estimate the cost of a recipe based on matched products.

    Returns a breakdown of each ingredient with its matched product and price,
    along with total cost and potential savings from discounts.
    """
    logger.info(f"Estimating cost for recipe {recipe_id}, prefer_discounts={prefer_discounts}")

    try:
        estimate = await service.estimate_recipe_cost(recipe_id, prefer_discounts)

        if not estimate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recipe {recipe_id} not found or has no matched products",
            )

        return RecipeCostEstimate(
            recipe_id=estimate.get("recipe_id", recipe_id),
            recipe_name=estimate.get("recipe_name", "Unknown"),
            items=estimate.get("items", []),
            total_cost=estimate.get("total_cost", 0.0),
            total_savings=estimate.get("total_savings", 0.0),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to estimate cost for recipe {recipe_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to estimate recipe cost",
        )


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: str,
    service: GraphService = Depends(get_graph_service),
) -> None:
    """Delete a recipe from the knowledge graph."""
    logger.info(f"Deleting recipe: {recipe_id}")

    try:
        deleted = await service.delete_recipe(recipe_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Recipe {recipe_id} not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete recipe {recipe_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete recipe",
        )


# =============================================================================
# Ingredient Endpoints
# =============================================================================


@router.get("/ingredients", response_model=IngredientListResponse)
async def list_ingredients(
    limit: Annotated[int, Query(ge=1, le=1000, description="Max ingredients to return")] = 100,
    service: GraphService = Depends(get_graph_service),
) -> IngredientListResponse:
    """List all ingredients in the knowledge graph."""
    logger.info(f"Listing ingredients: limit={limit}")

    try:
        ingredients = await service.get_all_ingredients(limit=limit)

        return IngredientListResponse(
            ingredients=ingredients,
            total=len(ingredients),
        )
    except Exception as e:
        logger.error(f"Failed to list ingredients: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ingredients",
        )


@router.get("/ingredients/unmatched")
async def get_unmatched_ingredients(
    limit: Annotated[int, Query(ge=1, le=500, description="Max results")] = 100,
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    """Get ingredients that don't have any matched products."""
    logger.info(f"Fetching unmatched ingredients: limit={limit}")

    try:
        unmatched = await service.get_unmatched_ingredients(limit=limit)

        return {
            "ingredients": unmatched,
            "total": len(unmatched),
        }
    except Exception as e:
        logger.error(f"Failed to fetch unmatched ingredients: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch unmatched ingredients",
        )


@router.get("/ingredients/{ingredient_name}/products", response_model=IngredientResponse)
async def get_ingredient_products(
    ingredient_name: str,
    min_confidence: Annotated[
        float, Query(ge=0.0, le=1.0, description="Minimum match confidence")
    ] = 0.5,
    limit: Annotated[int, Query(ge=1, le=20, description="Max products to return")] = 10,
    service: GraphService = Depends(get_graph_service),
) -> IngredientResponse:
    """
    Get matching products for an ingredient.

    Returns products matched to this ingredient with confidence scores,
    sorted by confidence and price.
    """
    logger.info(
        f"Fetching products for ingredient: {ingredient_name}, "
        f"min_confidence={min_confidence}, limit={limit}"
    )

    try:
        # Get ingredient details
        ingredient = await service.get_ingredient(ingredient_name)

        # Get matched products
        products = await service.get_products_for_ingredient(
            ingredient_name,
            min_confidence=min_confidence,
            limit=limit,
        )

        return IngredientResponse(
            name=ingredient.name if ingredient else ingredient_name,
            normalized_name=ingredient.normalized_name if ingredient else ingredient_name.lower(),
            description=ingredient.description if ingredient else None,
            products=products,
        )
    except Exception as e:
        logger.error(f"Failed to fetch products for ingredient {ingredient_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ingredient products",
        )


@router.post("/ingredients/match", response_model=IngredientMatchResponse)
async def match_ingredient(
    request: IngredientMatchRequest,
) -> IngredientMatchResponse:
    """
    Find matching products for an ingredient using fuzzy matching.

    This endpoint performs live matching without storing results.
    Use the compute_matches task to store matches in the graph.
    """
    logger.info(
        f"Matching ingredient: {request.ingredient_name}, "
        f"top_k={request.top_k}, min_confidence={request.min_confidence}"
    )

    try:
        db = await get_graph_db()
        matcher = IngredientMatcher(db)

        matches = await matcher.find_matches(
            ingredient_name=request.ingredient_name,
            top_k=request.top_k,
            min_confidence=request.min_confidence,
        )

        return IngredientMatchResponse(
            ingredient_name=request.ingredient_name,
            matches=[
                {
                    "product_id": m.product_id,
                    "product_name": m.product_name,
                    "confidence_score": m.confidence_score,
                    "match_type": m.match_type,
                    "matched_term": m.matched_term,
                }
                for m in matches
            ],
            total=len(matches),
        )
    except Exception as e:
        logger.error(f"Failed to match ingredient {request.ingredient_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to match ingredient",
        )


# =============================================================================
# Category and Area Endpoints
# =============================================================================


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    service: GraphService = Depends(get_graph_service),
) -> CategoryListResponse:
    """List all recipe categories."""
    logger.info("Listing categories")

    try:
        categories = await service.get_categories()

        return CategoryListResponse(
            categories=categories,
            total=len(categories),
        )
    except Exception as e:
        logger.error(f"Failed to list categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch categories",
        )


@router.get("/areas", response_model=AreaListResponse)
async def list_areas(
    service: GraphService = Depends(get_graph_service),
) -> AreaListResponse:
    """List all cuisine areas/regions."""
    logger.info("Listing areas")

    try:
        areas = await service.get_areas()

        return AreaListResponse(
            areas=areas,
            total=len(areas),
        )
    except Exception as e:
        logger.error(f"Failed to list areas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch areas",
        )


# =============================================================================
# Graph Management Endpoints
# =============================================================================


@router.get("/graph/stats", response_model=GraphStatsResponse)
async def get_graph_stats(
    service: GraphService = Depends(get_graph_service),
) -> GraphStatsResponse:
    """Get statistics about the knowledge graph."""
    logger.info("Fetching graph statistics")

    try:
        stats = await service.get_stats()

        return GraphStatsResponse(
            recipes=stats.get("recipes", 0),
            ingredients=stats.get("ingredients", 0),
            products=stats.get("products", 0),
            categories=stats.get("categories", 0),
            areas=stats.get("areas", 0),
            stores=stats.get("stores", 0),
            matches=stats.get("matches", 0),
        )
    except Exception as e:
        logger.error(f"Failed to fetch graph stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch graph statistics",
        )


@router.post("/graph/ingest/mealdb", response_model=TaskTriggerResponse)
async def trigger_mealdb_ingestion() -> TaskTriggerResponse:
    """
    Trigger MealDB recipe ingestion task.

    Fetches all recipes from TheMealDB and imports them into the knowledge graph.
    This is a background task that may take several minutes.
    """
    logger.info("Triggering MealDB ingestion task")

    try:
        task = ingest_mealdb_recipes_task.delay()

        return TaskTriggerResponse(
            task_id=task.id,
            status="started",
            message="MealDB recipe ingestion task has been queued",
        )
    except Exception as e:
        logger.error(f"Failed to trigger MealDB ingestion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue ingestion task",
        )


@router.post("/graph/sync/products", response_model=TaskTriggerResponse)
async def trigger_product_sync() -> TaskTriggerResponse:
    """
    Trigger product sync from PostgreSQL to Neo4j.

    Syncs all stores and products (with current discounts) to the knowledge graph.
    """
    logger.info("Triggering product sync task")

    try:
        task = sync_products_to_graph_task.delay()

        return TaskTriggerResponse(
            task_id=task.id,
            status="started",
            message="Product sync task has been queued",
        )
    except Exception as e:
        logger.error(f"Failed to trigger product sync: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue product sync task",
        )


@router.post("/graph/compute-matches", response_model=TaskTriggerResponse)
async def trigger_ingredient_matching(
    min_confidence: Annotated[
        float, Query(ge=0.0, le=1.0, description="Minimum confidence to store")
    ] = 0.6,
    top_k: Annotated[int, Query(ge=1, le=10, description="Max matches per ingredient")] = 3,
) -> TaskTriggerResponse:
    """
    Trigger ingredient-to-product matching task.

    Computes matches for all unmatched ingredients in the graph.
    """
    logger.info(f"Triggering ingredient matching: min_confidence={min_confidence}, top_k={top_k}")

    try:
        task = compute_ingredient_matches_task.delay(min_confidence, top_k)

        return TaskTriggerResponse(
            task_id=task.id,
            status="started",
            message="Ingredient matching task has been queued",
        )
    except Exception as e:
        logger.error(f"Failed to trigger ingredient matching: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue matching task",
        )


@router.post("/graph/refresh", response_model=TaskTriggerResponse)
async def trigger_full_refresh() -> TaskTriggerResponse:
    """
    Trigger a full knowledge graph refresh.

    This runs MealDB ingestion, product sync, and ingredient matching in sequence.
    Useful for initial setup or periodic full refresh.
    """
    logger.info("Triggering full graph refresh task")

    try:
        task = full_graph_refresh_task.delay()

        return TaskTriggerResponse(
            task_id=task.id,
            status="started",
            message="Full graph refresh task has been queued (may take up to 2 hours)",
        )
    except Exception as e:
        logger.error(f"Failed to trigger full refresh: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue refresh task",
        )
