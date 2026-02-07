"""Meal plan optimization algorithms."""

from dataclasses import dataclass, field
from typing import Any

from foodplanner.graph.models import RecipeWithIngredients
from foodplanner.graph.service import GraphService
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DietaryPreference:
    """User dietary preference."""

    name: str
    type: str  # "allergy", "preference", "restriction"


@dataclass
class RecipeScore:
    """Scored recipe for optimization."""

    recipe: RecipeWithIngredients
    discount_count: int = 0
    discounted_ingredients: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_savings: float = 0.0
    ingredient_overlap_score: float = 0.0
    total_score: float = 0.0
    suggestion_reason: str = ""


@dataclass
class OptimizedRecipe:
    """Recipe selected for the meal plan."""

    recipe_id: str
    recipe_name: str
    thumbnail: str | None
    category: str | None
    area: str | None
    estimated_cost: float
    estimated_savings: float
    suggestion_reason: str
    discounted_ingredients: list[str]
    ingredients: list[dict[str, Any]]


class MealPlanOptimizer:
    """
    Optimizes meal plan selection based on:
    - Discount availability (prioritize discounted ingredients)
    - Dietary preferences (filter by restrictions)
    - Ingredient reuse (minimize waste)
    - Budget constraints
    """

    # Weights for scoring (can be tuned)
    DISCOUNT_WEIGHT = 3.0  # Points per discounted ingredient
    COST_WEIGHT = -0.1  # Negative weight (lower cost = better)
    OVERLAP_WEIGHT = 1.5  # Points for reusing ingredients
    VARIETY_PENALTY = -2.0  # Penalty for same category

    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service

    async def optimize(
        self,
        days: int,
        people_count: int,
        store_ids: list[str] | None = None,
        dietary_preferences: list[DietaryPreference] | None = None,
        budget_max: float | None = None,
        excluded_recipe_ids: list[str] | None = None,
    ) -> list[OptimizedRecipe]:
        """
        Generate an optimized meal plan.

        Args:
            days: Number of days to plan for.
            people_count: Number of people to serve.
            store_ids: Preferred store IDs (not yet used, for future filtering).
            dietary_preferences: Dietary restrictions/preferences.
            budget_max: Maximum total budget (optional).
            excluded_recipe_ids: Recipe IDs to exclude.

        Returns:
            List of optimized recipes, one per day.
        """
        logger.info(f"Optimizing meal plan: {days} days, {people_count} people")

        # Step 1: Fetch candidate recipes with discount info
        candidates = await self._fetch_candidates(dietary_preferences)

        if not candidates:
            logger.warning("No candidate recipes found")
            return []

        # Step 2: Filter excluded recipes
        if excluded_recipe_ids:
            candidates = [c for c in candidates if c.recipe.id not in excluded_recipe_ids]

        # Step 3: Score all candidates
        scored = await self._score_candidates(candidates, people_count)

        # Step 4: Select recipes using greedy algorithm
        selected = self._greedy_select(scored, days, budget_max, people_count)

        logger.info(f"Selected {len(selected)} recipes for meal plan")

        return selected

    async def _fetch_candidates(
        self,
        dietary_preferences: list[DietaryPreference] | None = None,
    ) -> list[RecipeScore]:
        """Fetch candidate recipes with discount information."""
        # First, get recipes with discounts
        discount_recipes = await self.graph_service.find_recipes_with_discounts(
            min_discounted_ingredients=1,
            limit=100,
        )

        # Create RecipeScore objects from discount results
        candidates: list[RecipeScore] = []

        for result in discount_recipes:
            recipe = result.recipe
            discount_count = result.discounted_ingredients

            # Get full recipe details with ingredients
            full_recipe = await self.graph_service.get_recipe(recipe.id)
            if not full_recipe:
                continue

            # Filter by dietary preferences
            if dietary_preferences and not self._matches_dietary(full_recipe, dietary_preferences):
                continue

            # Get cost estimate
            cost_estimate = await self.graph_service.estimate_recipe_cost(recipe.id)
            estimated_cost = cost_estimate.get("total_cost", 0.0) if cost_estimate else 0.0
            estimated_savings = cost_estimate.get("total_savings", 0.0) if cost_estimate else 0.0

            # Extract discounted ingredient names
            discounted_items = cost_estimate.get("items", []) if cost_estimate else []
            discounted_names = [
                item.get("ingredient", "") for item in discounted_items if item.get("has_discount")
            ]

            candidates.append(
                RecipeScore(
                    recipe=full_recipe,
                    discount_count=discount_count,
                    discounted_ingredients=discounted_names,
                    estimated_cost=estimated_cost,
                    estimated_savings=estimated_savings,
                )
            )

        # Also fetch some non-discount recipes for variety
        if len(candidates) < 50:
            regular_recipes = await self.graph_service.search_recipes(limit=50)
            existing_ids = {c.recipe.id for c in candidates}

            for recipe in regular_recipes:
                if recipe.id in existing_ids:
                    continue

                if dietary_preferences and not self._matches_dietary(recipe, dietary_preferences):
                    continue

                cost_estimate = await self.graph_service.estimate_recipe_cost(recipe.id)
                estimated_cost = cost_estimate.get("total_cost", 0.0) if cost_estimate else 0.0

                candidates.append(
                    RecipeScore(
                        recipe=recipe,
                        discount_count=0,
                        discounted_ingredients=[],
                        estimated_cost=estimated_cost,
                        estimated_savings=0.0,
                    )
                )

        logger.info(f"Found {len(candidates)} candidate recipes")
        return candidates

    def _matches_dietary(
        self,
        recipe: RecipeWithIngredients,
        preferences: list[DietaryPreference],
    ) -> bool:
        """Check if recipe matches dietary preferences."""
        # Simple keyword-based filtering
        # This will be enhanced in Phase 4 with proper dietary inference

        ingredient_names = [
            ing.get("name", "").lower() if isinstance(ing, dict) else ing.lower()
            for ing in recipe.ingredients
        ]
        # Note: recipe.tags could be used for dietary filtering in future

        def contains_any_keyword(keywords: set[str]) -> bool:
            """Check if any ingredient name contains any of the keywords."""
            for ing in ingredient_names:
                for kw in keywords:
                    if kw in ing:
                        return True
            return False

        for pref in preferences:
            pref_lower = pref.name.lower()

            if pref.type == "allergy":
                # Check if any ingredient contains the allergen
                if any(pref_lower in ing for ing in ingredient_names):
                    return False

            elif pref_lower == "vegetarian":
                # Check for meat
                meat_keywords = {
                    "chicken",
                    "beef",
                    "pork",
                    "lamb",
                    "fish",
                    "bacon",
                    "ham",
                    "salmon",
                }
                if contains_any_keyword(meat_keywords):
                    return False

            elif pref_lower == "vegan":
                # Check for animal products
                animal_keywords = {
                    "chicken",
                    "beef",
                    "pork",
                    "lamb",
                    "fish",
                    "bacon",
                    "ham",
                    "salmon",
                    "milk",
                    "cheese",
                    "butter",
                    "cream",
                    "egg",
                    "honey",
                }
                if contains_any_keyword(animal_keywords):
                    return False

            elif pref_lower == "gluten-free":
                gluten_keywords = {"flour", "bread", "pasta", "wheat", "barley"}
                if contains_any_keyword(gluten_keywords):
                    return False

        return True

    async def _score_candidates(
        self,
        candidates: list[RecipeScore],
        people_count: int,
    ) -> list[RecipeScore]:
        """Score all candidate recipes."""
        for candidate in candidates:
            # Base score from discounts
            discount_score = candidate.discount_count * self.DISCOUNT_WEIGHT

            # Cost score (adjusted for people count)
            cost_per_person = candidate.estimated_cost / max(people_count, 1)
            cost_score = cost_per_person * self.COST_WEIGHT

            # Total score
            candidate.total_score = discount_score + cost_score

            # Generate suggestion reason
            candidate.suggestion_reason = self._generate_reason(candidate)

        # Sort by score (highest first)
        candidates.sort(key=lambda x: x.total_score, reverse=True)

        return candidates

    def _generate_reason(self, scored: RecipeScore) -> str:
        """Generate human-readable suggestion reason."""
        reasons = []

        if scored.discount_count > 0:
            reasons.append(f"Uses {scored.discount_count} discounted ingredient(s)")

        if scored.estimated_savings > 0:
            reasons.append(f"Save {scored.estimated_savings:.0f} kr")

        if scored.estimated_cost > 0 and scored.estimated_cost < 50:
            reasons.append("Budget-friendly")

        if not reasons:
            reasons.append("Good variety option")

        return " · ".join(reasons)

    def _greedy_select(
        self,
        scored: list[RecipeScore],
        days: int,
        budget_max: float | None,
        people_count: int,
    ) -> list[OptimizedRecipe]:
        """Use greedy algorithm to select recipes."""
        selected: list[OptimizedRecipe] = []
        used_categories: dict[str, int] = {}  # Track category usage
        used_ingredients: set[str] = set()  # Track ingredient overlap
        total_cost = 0.0

        for candidate in scored:
            if len(selected) >= days:
                break

            # Budget check
            recipe_cost = candidate.estimated_cost * people_count
            if budget_max and (total_cost + recipe_cost) > budget_max:
                continue

            # Variety check: penalize too many from same category
            category = candidate.recipe.category or "Other"
            if used_categories.get(category, 0) >= 2:
                continue

            # Calculate ingredient overlap bonus
            recipe_ingredients = {
                ing.get("name", "").lower() if isinstance(ing, dict) else ing.lower()
                for ing in candidate.recipe.ingredients
            }
            overlap = len(recipe_ingredients & used_ingredients)

            # Log overlap for debugging (could be used for re-ranking in future)
            if overlap > 0:
                logger.debug(
                    f"Recipe {candidate.recipe.name} shares {overlap} ingredients with selection"
                )

            # Add to selection
            selected.append(
                OptimizedRecipe(
                    recipe_id=candidate.recipe.id,
                    recipe_name=candidate.recipe.name,
                    thumbnail=candidate.recipe.thumbnail,
                    category=candidate.recipe.category,
                    area=candidate.recipe.area,
                    estimated_cost=candidate.estimated_cost * people_count,
                    estimated_savings=candidate.estimated_savings * people_count,
                    suggestion_reason=candidate.suggestion_reason,
                    discounted_ingredients=candidate.discounted_ingredients,
                    ingredients=[
                        ing if isinstance(ing, dict) else {"name": ing}
                        for ing in candidate.recipe.ingredients
                    ],
                )
            )

            # Update tracking
            total_cost += recipe_cost
            used_categories[category] = used_categories.get(category, 0) + 1
            used_ingredients.update(recipe_ingredients)

        return selected

    async def find_replacement(
        self,
        recipe_id: str,
        criteria: str = "cheaper",
        excluded_ids: list[str] | None = None,
        limit: int = 5,
    ) -> list[OptimizedRecipe]:
        """
        Find replacement recipes for a given recipe.

        Args:
            recipe_id: Recipe to replace.
            criteria: "cheaper", "healthier", or "different".
            excluded_ids: Recipe IDs to exclude.
            limit: Max results.

        Returns:
            List of alternative recipes.
        """
        # Get the original recipe
        original = await self.graph_service.get_recipe(recipe_id)
        if not original:
            return []

        original_cost = await self.graph_service.estimate_recipe_cost(recipe_id)
        original_cost_value = original_cost.get("total_cost", 0.0) if original_cost else 0.0

        # Search for alternatives
        if criteria == "cheaper":
            # Same category, lower cost
            candidates = await self.graph_service.search_recipes(
                category=original.category,
                limit=50,
            )
        elif criteria == "different":
            # Different category
            candidates = await self.graph_service.search_recipes(limit=50)
            candidates = [c for c in candidates if c.category != original.category]
        else:
            # Default: similar recipes
            candidates = await self.graph_service.search_recipes(
                category=original.category,
                limit=50,
            )

        # Filter and score
        excluded = set(excluded_ids or [])
        excluded.add(recipe_id)

        results: list[OptimizedRecipe] = []
        for recipe in candidates:
            if recipe.id in excluded:
                continue

            cost_estimate = await self.graph_service.estimate_recipe_cost(recipe.id)
            estimated_cost = cost_estimate.get("total_cost", 0.0) if cost_estimate else 0.0
            estimated_savings = cost_estimate.get("total_savings", 0.0) if cost_estimate else 0.0

            # For "cheaper" criteria, filter by cost
            if criteria == "cheaper" and estimated_cost >= original_cost_value:
                continue

            reason = f"Alternative to {original.name}"
            if estimated_cost < original_cost_value:
                reason += f" · {original_cost_value - estimated_cost:.0f} kr cheaper"

            results.append(
                OptimizedRecipe(
                    recipe_id=recipe.id,
                    recipe_name=recipe.name,
                    thumbnail=recipe.thumbnail,
                    category=recipe.category,
                    area=recipe.area,
                    estimated_cost=estimated_cost,
                    estimated_savings=estimated_savings,
                    suggestion_reason=reason,
                    discounted_ingredients=[],
                    ingredients=[
                        ing if isinstance(ing, dict) else {"name": ing}
                        for ing in recipe.ingredients
                    ],
                )
            )

            if len(results) >= limit:
                break

        return results
