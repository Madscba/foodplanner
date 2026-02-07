"""Shopping list generation from meal plans."""

from dataclasses import dataclass, field
from typing import Any

from foodplanner.graph.service import GraphService
from foodplanner.logging_config import get_logger
from foodplanner.normalize.units import (
    AggregatedIngredient,
    aggregate_ingredients,
)

logger = get_logger(__name__)


@dataclass
class ShoppingItem:
    """A single item in the shopping list."""

    ingredient_name: str
    normalized_name: str
    quantity: str
    unit: str
    recipe_sources: list[str] = field(default_factory=list)

    # Product match info
    product_id: str | None = None
    product_name: str | None = None
    product_brand: str | None = None
    price: float | None = None
    discount_price: float | None = None
    store_id: str | None = None
    store_name: str | None = None
    category: str | None = None

    # Match metadata
    match_confidence: float | None = None
    alternative_products: list[str] = field(default_factory=list)

    @property
    def effective_price(self) -> float | None:
        """Get the effective price (discount or regular)."""
        if self.discount_price is not None:
            return self.discount_price
        return self.price

    @property
    def savings(self) -> float:
        """Calculate savings from discount."""
        if self.price and self.discount_price:
            return self.price - self.discount_price
        return 0.0

    @property
    def has_discount(self) -> bool:
        """Check if item has an active discount."""
        return self.discount_price is not None and self.price is not None


@dataclass
class ShoppingList:
    """Complete shopping list for a meal plan."""

    meal_plan_id: str
    items: list[ShoppingItem] = field(default_factory=list)

    # Computed totals
    total_cost: float = 0.0
    total_savings: float = 0.0
    matched_items_count: int = 0
    unmatched_items_count: int = 0

    # Grouped views
    items_by_category: dict[str, list[ShoppingItem]] = field(default_factory=dict)
    items_by_store: dict[str, list[ShoppingItem]] = field(default_factory=dict)

    def add_item(self, item: ShoppingItem) -> None:
        """Add an item and update computed fields."""
        self.items.append(item)

        # Update totals
        if item.effective_price:
            self.total_cost += item.effective_price
        self.total_savings += item.savings

        if item.product_id:
            self.matched_items_count += 1
        else:
            self.unmatched_items_count += 1

        # Group by category
        category = item.category or "Other"
        if category not in self.items_by_category:
            self.items_by_category[category] = []
        self.items_by_category[category].append(item)

        # Group by store
        store = item.store_name or "Unknown Store"
        if store not in self.items_by_store:
            self.items_by_store[store] = []
        self.items_by_store[store].append(item)


class ShoppingListGenerator:
    """
    Generates shopping lists from meal plans with:
    - Quantity aggregation across recipes
    - Unit normalization (e.g., 2 cups + 500ml -> 1L)
    - Product matching with confidence scores
    - Store-specific pricing
    """

    def __init__(self, graph_service: GraphService):
        self.graph_service = graph_service

    async def generate(
        self,
        meal_plan_id: str,
        recipes_ingredients: list[tuple[str, list[dict[str, Any]]]],
        store_ids: list[str] | None = None,
        people_count: int = 2,
    ) -> ShoppingList:
        """
        Generate a shopping list from meal plan recipes.

        Args:
            meal_plan_id: The meal plan ID.
            recipes_ingredients: List of (recipe_id, ingredients) tuples.
            store_ids: Preferred store IDs for product matching.
            people_count: Number of people to scale quantities for.

        Returns:
            Complete ShoppingList with matched products.
        """
        logger.info(f"Generating shopping list for plan {meal_plan_id}")

        # Step 1: Aggregate all ingredients across recipes
        aggregated = await self._aggregate_all_ingredients(
            recipes_ingredients,
            people_count,
        )

        # Step 2: Match ingredients to products
        shopping_list = ShoppingList(meal_plan_id=meal_plan_id)

        for agg_ing in aggregated.values():
            item = await self._create_shopping_item(
                agg_ing,
                store_ids,
            )
            shopping_list.add_item(item)

        logger.info(
            f"Generated shopping list: {len(shopping_list.items)} items, "
            f"{shopping_list.matched_items_count} matched, "
            f"total cost: {shopping_list.total_cost:.2f}"
        )

        return shopping_list

    async def _aggregate_all_ingredients(
        self,
        recipes_ingredients: list[tuple[str, list[dict[str, Any]]]],
        people_count: int,
    ) -> dict[str, AggregatedIngredient]:
        """Aggregate ingredients from all recipes."""
        all_aggregated: dict[str, AggregatedIngredient] = {}

        for recipe_id, ingredients in recipes_ingredients:
            # Aggregate within this recipe
            recipe_agg = aggregate_ingredients(ingredients, recipe_id)

            # Merge into overall aggregation
            for norm_name, agg_ing in recipe_agg.items():
                if norm_name in all_aggregated:
                    existing = all_aggregated[norm_name]
                    existing.total_quantity = existing.total_quantity + agg_ing.total_quantity
                    existing.recipe_sources.extend(agg_ing.recipe_sources)
                else:
                    all_aggregated[norm_name] = agg_ing

        # Scale quantities for people count (assuming base recipes serve 2-4)
        # This is a simple scaling - could be more sophisticated
        if people_count > 1:
            scale_factor = people_count / 2.0  # Assume recipes serve 2 by default
            for agg_ing in all_aggregated.values():
                agg_ing.total_quantity.value *= scale_factor

        return all_aggregated

    async def _create_shopping_item(
        self,
        agg_ing: AggregatedIngredient,
        store_ids: list[str] | None,
    ) -> ShoppingItem:
        """Create a shopping item with product match."""
        # Get display quantity
        qty, unit = agg_ing.total_quantity.to_display_string()

        item = ShoppingItem(
            ingredient_name=agg_ing.name,
            normalized_name=agg_ing.normalized_name,
            quantity=qty,
            unit=unit,
            recipe_sources=agg_ing.recipe_sources,
        )

        # Try to match to a product
        try:
            products = await self.graph_service.get_products_for_ingredient(
                agg_ing.name,
                min_confidence=0.5,
                limit=5,
            )

            if products:
                # Select best product (prefer discounted, then cheapest)
                best_product = self._select_best_product(products, store_ids)

                if best_product:
                    item.product_id = best_product.get("p", {}).get("id")
                    item.product_name = best_product.get("p", {}).get("name")
                    item.product_brand = best_product.get("p", {}).get("brand")
                    item.price = best_product.get("p", {}).get("price")
                    item.discount_price = best_product.get("p", {}).get("discount_price")
                    item.store_id = best_product.get("store_id")
                    item.store_name = best_product.get("store_name")
                    item.category = best_product.get("p", {}).get("category")
                    item.match_confidence = best_product.get("confidence")

                    # Store alternatives
                    item.alternative_products = [
                        p.get("p", {}).get("id") for p in products[1:4] if p.get("p", {}).get("id")
                    ]

        except Exception as e:
            logger.warning(f"Failed to match product for {agg_ing.name}: {e}")

        return item

    def _select_best_product(
        self,
        products: list[dict[str, Any]],
        store_ids: list[str] | None,
    ) -> dict[str, Any] | None:
        """
        Select the best product from matches.

        Priority:
        1. Preferred stores (if specified)
        2. Has active discount
        3. Lowest effective price
        4. Highest confidence score
        """
        if not products:
            return None

        def score_product(p: dict[str, Any]) -> tuple[int, int, float, float]:
            """Score a product for sorting (higher is better)."""
            product_data = p.get("p", {})
            store_id = p.get("store_id")

            # Preferred store bonus
            store_score = 1 if store_ids and store_id in store_ids else 0

            # Discount bonus
            has_discount = product_data.get("has_active_discount", False)
            discount_score = 1 if has_discount else 0

            # Price (lower is better, so negate)
            price = product_data.get("discount_price") or product_data.get("price") or 999
            price_score = -price

            # Confidence
            confidence = p.get("confidence", 0.5)

            return (store_score, discount_score, price_score, confidence)

        # Sort by score (highest first)
        sorted_products = sorted(products, key=score_product, reverse=True)

        return sorted_products[0] if sorted_products else None

    async def generate_from_db_plan(
        self,
        plan: Any,  # MealPlan SQLAlchemy model
        store_ids: list[str] | None = None,
    ) -> ShoppingList:
        """
        Generate shopping list directly from a database MealPlan object.

        Args:
            plan: MealPlan SQLAlchemy model with loaded recipes.
            store_ids: Preferred store IDs.

        Returns:
            Complete ShoppingList.
        """
        # Extract ingredients from each recipe in the plan
        recipes_ingredients: list[tuple[str, list[dict[str, Any]]]] = []

        for mpr in plan.recipes:
            if mpr.recipe and mpr.recipe.ingredients:
                ingredients = []
                for ing in mpr.recipe.ingredients:
                    if isinstance(ing, str):
                        ingredients.append({"name": ing})
                    elif isinstance(ing, dict):
                        ingredients.append(ing)
                    else:
                        ingredients.append({"name": str(ing)})

                recipes_ingredients.append((mpr.recipe_id, ingredients))

        # Get people count from plan metadata
        people_count = 2
        if plan.plan_metadata:
            people_count = plan.plan_metadata.get("people_count", 2)

        return await self.generate(
            meal_plan_id=plan.id,
            recipes_ingredients=recipes_ingredients,
            store_ids=store_ids,
            people_count=people_count,
        )
