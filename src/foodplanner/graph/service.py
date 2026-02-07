"""Business logic service layer for graph operations."""

from typing import Any

from foodplanner.graph.database import GraphDatabase
from foodplanner.graph.models import (
    AreaNode,
    CategoryNode,
    ContainsRelationship,
    IngredientNode,
    ProductNode,
    RecipeNode,
    RecipeSearchResult,
    RecipeWithIngredients,
    StoreNode,
)
from foodplanner.graph.repository import GraphRepository
from foodplanner.ingest.connectors.mealdb import ParsedMeal
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


class GraphService:
    """Service layer for graph business logic."""

    def __init__(self, db: GraphDatabase):
        self.db = db
        self.repo = GraphRepository(db)

    async def setup(self) -> None:
        """Initialize the graph database with constraints and indexes."""
        await self.db.setup_constraints()

    # =========================================================================
    # Recipe Operations
    # =========================================================================

    async def import_meal_from_mealdb(self, meal: ParsedMeal) -> dict[str, Any]:
        """
        Import a meal from TheMealDB into the graph.

        Args:
            meal: Parsed meal data from MealDB connector.

        Returns:
            Summary of created entities.
        """
        # Create recipe node
        recipe = RecipeNode(
            id=meal.id,
            name=meal.name,
            instructions=meal.instructions,
            thumbnail=meal.thumbnail,
            source_url=meal.source_url,
            youtube_url=meal.youtube_url,
            tags=meal.tags,
        )

        # Create ingredients with relationships
        ingredients = [
            (
                IngredientNode(name=ing.name),
                ContainsRelationship(quantity="", measure=ing.measure),
            )
            for ing in meal.ingredients
        ]

        result = await self.repo.create_recipe(
            recipe=recipe,
            category=meal.category,
            area=meal.area,
            ingredients=ingredients,
        )

        logger.info(f"Imported recipe '{meal.name}' with {len(meal.ingredients)} ingredients")
        return result

    async def import_meals_batch(
        self, meals: list[ParsedMeal], batch_size: int = 50
    ) -> dict[str, Any]:
        """
        Import multiple meals in batches.

        Args:
            meals: List of parsed meals.
            batch_size: Number of meals per batch.

        Returns:
            Summary of import operation.
        """
        total_imported = 0
        total_failed = 0
        failed_meals: list[str] = []

        for i in range(0, len(meals), batch_size):
            batch = meals[i : i + batch_size]
            for meal in batch:
                try:
                    await self.import_meal_from_mealdb(meal)
                    total_imported += 1
                except Exception as e:
                    logger.error(f"Failed to import meal '{meal.name}': {e}")
                    total_failed += 1
                    failed_meals.append(meal.name)

            logger.info(f"Imported batch {i // batch_size + 1}, total: {total_imported}")

        return {
            "total_imported": total_imported,
            "total_failed": total_failed,
            "failed_meals": failed_meals,
        }

    async def get_recipe(self, recipe_id: str) -> RecipeWithIngredients | None:
        """Get a recipe by ID."""
        return await self.repo.get_recipe_by_id(recipe_id)

    async def search_recipes(
        self,
        name: str | None = None,
        category: str | None = None,
        area: str | None = None,
        ingredient: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[RecipeWithIngredients]:
        """Search recipes with filters."""
        return await self.repo.search_recipes(
            name=name,
            category=category,
            area=area,
            ingredient=ingredient,
            limit=limit,
            offset=offset,
        )

    async def delete_recipe(self, recipe_id: str) -> bool:
        """Delete a recipe."""
        return await self.repo.delete_recipe(recipe_id)

    # =========================================================================
    # Category and Area Operations
    # =========================================================================

    async def import_category(
        self,
        name: str,
        description: str | None = None,
        thumbnail: str | None = None,
    ) -> dict[str, Any]:
        """Import a category."""
        category = CategoryNode(
            name=name,
            description=description,
            thumbnail=thumbnail,
        )
        return await self.repo.create_category(category)

    async def import_area(self, name: str) -> dict[str, Any]:
        """Import an area/cuisine."""
        area = AreaNode(name=name)
        return await self.repo.create_area(area)

    async def get_categories(self) -> list[CategoryNode]:
        """Get all categories."""
        return await self.repo.get_all_categories()

    async def get_areas(self) -> list[AreaNode]:
        """Get all areas/cuisines."""
        return await self.repo.get_all_areas()

    # =========================================================================
    # Ingredient Operations
    # =========================================================================

    async def get_ingredient(self, name: str) -> IngredientNode | None:
        """Get an ingredient by name."""
        return await self.repo.get_ingredient(name)

    async def get_all_ingredients(self, limit: int = 1000) -> list[IngredientNode]:
        """Get all ingredients."""
        return await self.repo.get_all_ingredients(limit)

    async def get_products_for_ingredient(
        self,
        ingredient_name: str,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get products matched to an ingredient."""
        return await self.repo.get_products_for_ingredient(ingredient_name, min_confidence, limit)

    async def get_unmatched_ingredients(self, limit: int = 100) -> list[str]:
        """Get ingredients without product matches."""
        return await self.repo.get_unmatched_ingredients(limit)

    # =========================================================================
    # Product and Store Sync
    # =========================================================================

    async def sync_store(
        self,
        store_id: str,
        name: str,
        brand: str,
        city: str | None = None,
        zip_code: str | None = None,
    ) -> dict[str, Any]:
        """Sync a store from PostgreSQL to the graph."""
        store = StoreNode(
            id=store_id,
            name=name,
            brand=brand,
            city=city,
            zip_code=zip_code,
        )
        return await self.repo.upsert_store(store)

    async def sync_product(
        self,
        product_id: str,
        name: str,
        price: float,
        unit: str,
        store_id: str,
        brand: str | None = None,
        category: str | None = None,
        ean: str | None = None,
        discount_price: float | None = None,
        discount_percentage: float | None = None,
    ) -> dict[str, Any]:
        """Sync a product from PostgreSQL to the graph."""
        has_discount = discount_price is not None and discount_price < price

        product = ProductNode(
            id=product_id,
            name=name,
            brand=brand,
            category=category,
            price=price,
            unit=unit,
            ean=ean,
            discount_price=discount_price,
            discount_percentage=discount_percentage,
            has_active_discount=has_discount,
        )
        return await self.repo.upsert_product(product, store_id)

    async def sync_products_batch(self, products: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Sync multiple products in batch.

        Args:
            products: List of product dictionaries with all required fields.

        Returns:
            Summary of sync operation.
        """
        product_tuples = []
        for p in products:
            has_discount = p.get("discount_price") is not None and p["discount_price"] < p["price"]
            product = ProductNode(
                id=p["id"],
                name=p["name"],
                brand=p.get("brand"),
                category=p.get("category"),
                price=p["price"],
                unit=p["unit"],
                ean=p.get("ean"),
                discount_price=p.get("discount_price"),
                discount_percentage=p.get("discount_percentage"),
                has_active_discount=has_discount,
            )
            product_tuples.append((product, p["store_id"]))

        return await self.repo.bulk_upsert_products(product_tuples)

    # =========================================================================
    # Discount-Aware Queries
    # =========================================================================

    async def find_recipes_with_discounts(
        self,
        min_discounted_ingredients: int = 1,
        limit: int = 20,
    ) -> list[RecipeSearchResult]:
        """
        Find recipes that use currently discounted products.

        Args:
            min_discounted_ingredients: Minimum number of discounted ingredients.
            limit: Maximum results to return.

        Returns:
            List of recipes sorted by discount opportunities.
        """
        results = await self.repo.find_recipes_by_discounted_ingredients(
            min_discounted=min_discounted_ingredients,
            limit=limit,
        )

        recipes = []
        for r in results:
            recipe_data = r["r"]
            recipe = RecipeWithIngredients(
                id=recipe_data["id"],
                name=recipe_data["name"],
                instructions=recipe_data.get("instructions", ""),
                thumbnail=recipe_data.get("thumbnail"),
                source_url=recipe_data.get("source_url"),
                youtube_url=recipe_data.get("youtube_url"),
                tags=recipe_data.get("tags", []),
                category=r.get("category"),
                area=r.get("area"),
                ingredients=[],  # Not fetching full ingredients here
            )

            recipes.append(
                RecipeSearchResult(
                    recipe=recipe,
                    discounted_ingredients=r["discounted_count"],
                )
            )

        return recipes

    async def estimate_recipe_cost(
        self,
        recipe_id: str,
        prefer_discounts: bool = True,
    ) -> dict[str, Any]:
        """
        Estimate the cost of making a recipe.

        Args:
            recipe_id: Recipe ID.
            prefer_discounts: Whether to prefer discounted products.

        Returns:
            Cost breakdown with items, total, and savings.
        """
        return await self.repo.get_recipe_cost_estimate(recipe_id, prefer_discounts)

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self) -> dict[str, int]:
        """Get graph statistics."""
        return await self.repo.get_stats()
