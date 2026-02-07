"""Repository for graph database operations with Cypher queries."""

from typing import Any

from foodplanner.graph.database import GraphDatabase
from foodplanner.graph.models import (
    AreaNode,
    CategoryNode,
    ContainsRelationship,
    IngredientNode,
    MatchesRelationship,
    ProductNode,
    RecipeNode,
    RecipeWithIngredients,
    StoreNode,
)
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


class GraphRepository:
    """Repository for Neo4j graph operations."""

    def __init__(self, db: GraphDatabase):
        self.db = db

    # =========================================================================
    # Recipe Operations
    # =========================================================================

    async def create_recipe(
        self,
        recipe: RecipeNode,
        category: str | None = None,
        area: str | None = None,
        ingredients: list[tuple[IngredientNode, ContainsRelationship]] | None = None,
    ) -> dict[str, Any]:
        """
        Create a recipe with its relationships.

        Args:
            recipe: Recipe node data.
            category: Optional category name.
            area: Optional area/cuisine name.
            ingredients: List of (ingredient, relationship) tuples.

        Returns:
            Summary of created nodes/relationships.
        """
        query = """
        MERGE (r:Recipe {id: $recipe_id})
        SET r += $recipe_props
        WITH r
        """

        params: dict[str, Any] = {
            "recipe_id": recipe.id,
            "recipe_props": recipe.to_neo4j_properties(),
        }

        # Add category relationship
        if category:
            query += """
            MERGE (c:Category {name: $category})
            MERGE (r)-[:IN_CATEGORY]->(c)
            WITH r
            """
            params["category"] = category

        # Add area relationship
        if area:
            query += """
            MERGE (a:Area {name: $area})
            MERGE (r)-[:FROM_AREA]->(a)
            WITH r
            """
            params["area"] = area

        # Add ingredients
        if ingredients:
            query += """
            UNWIND $ingredients AS ing
            MERGE (i:Ingredient {name: ing.name})
            SET i.normalized_name = ing.normalized_name
            MERGE (r)-[rel:CONTAINS]->(i)
            SET rel.quantity = ing.quantity, rel.measure = ing.measure
            """
            params["ingredients"] = [
                {
                    "name": ing.name,
                    "normalized_name": ing.normalized_name,
                    "quantity": rel.quantity,
                    "measure": rel.measure,
                }
                for ing, rel in ingredients
            ]

        query += "RETURN r"
        return await self.db.execute_write(query, params)

    async def get_recipe_by_id(self, recipe_id: str) -> RecipeWithIngredients | None:
        """Get a recipe with all its relationships."""
        query = """
        MATCH (r:Recipe {id: $recipe_id})
        OPTIONAL MATCH (r)-[:IN_CATEGORY]->(c:Category)
        OPTIONAL MATCH (r)-[:FROM_AREA]->(a:Area)
        OPTIONAL MATCH (r)-[rel:CONTAINS]->(i:Ingredient)
        RETURN r, c.name as category, a.name as area,
               collect({
                   name: i.name,
                   normalized_name: i.normalized_name,
                   quantity: rel.quantity,
                   measure: rel.measure
               }) as ingredients
        """
        results = await self.db.execute_query(query, {"recipe_id": recipe_id})

        if not results:
            return None

        record = results[0]
        recipe_data = record["r"]

        return RecipeWithIngredients(
            id=recipe_data["id"],
            name=recipe_data["name"],
            instructions=recipe_data.get("instructions", ""),
            thumbnail=recipe_data.get("thumbnail"),
            source_url=recipe_data.get("source_url"),
            youtube_url=recipe_data.get("youtube_url"),
            tags=recipe_data.get("tags", []),
            category=record.get("category"),
            area=record.get("area"),
            ingredients=[i for i in record["ingredients"] if i.get("name")],
        )

    async def search_recipes(
        self,
        name: str | None = None,
        category: str | None = None,
        area: str | None = None,
        ingredient: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[RecipeWithIngredients]:
        """Search recipes with various filters."""
        conditions = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if name:
            conditions.append("toLower(r.name) CONTAINS toLower($name)")
            params["name"] = name

        if category:
            conditions.append("(r)-[:IN_CATEGORY]->(:Category {name: $category})")
            params["category"] = category

        if area:
            conditions.append("(r)-[:FROM_AREA]->(:Area {name: $area})")
            params["area"] = area

        if ingredient:
            conditions.append(
                "(r)-[:CONTAINS]->(:Ingredient {normalized_name: toLower($ingredient)})"
            )
            params["ingredient"] = ingredient

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
        MATCH (r:Recipe)
        {where_clause}
        OPTIONAL MATCH (r)-[:IN_CATEGORY]->(c:Category)
        OPTIONAL MATCH (r)-[:FROM_AREA]->(a:Area)
        OPTIONAL MATCH (r)-[rel:CONTAINS]->(i:Ingredient)
        WITH r, c, a, collect({{
            name: i.name,
            normalized_name: i.normalized_name,
            quantity: rel.quantity,
            measure: rel.measure
        }}) as ingredients
        RETURN r, c.name as category, a.name as area, ingredients
        ORDER BY r.name
        SKIP $offset LIMIT $limit
        """

        results = await self.db.execute_query(query, params)

        recipes = []
        for record in results:
            recipe_data = record["r"]
            recipes.append(
                RecipeWithIngredients(
                    id=recipe_data["id"],
                    name=recipe_data["name"],
                    instructions=recipe_data.get("instructions", ""),
                    thumbnail=recipe_data.get("thumbnail"),
                    source_url=recipe_data.get("source_url"),
                    youtube_url=recipe_data.get("youtube_url"),
                    tags=recipe_data.get("tags", []),
                    category=record.get("category"),
                    area=record.get("area"),
                    ingredients=[i for i in record["ingredients"] if i.get("name")],
                )
            )

        return recipes

    async def delete_recipe(self, recipe_id: str) -> bool:
        """Delete a recipe and its relationships."""
        query = """
        MATCH (r:Recipe {id: $recipe_id})
        DETACH DELETE r
        RETURN count(r) as deleted
        """
        results = await self.db.execute_query(query, {"recipe_id": recipe_id})
        return results[0]["deleted"] > 0 if results else False

    # =========================================================================
    # Ingredient Operations
    # =========================================================================

    async def create_ingredient(self, ingredient: IngredientNode) -> dict[str, Any]:
        """Create or update an ingredient node."""
        query = """
        MERGE (i:Ingredient {name: $name})
        SET i += $props
        RETURN i
        """
        return await self.db.execute_write(
            query,
            {
                "name": ingredient.name,
                "props": ingredient.to_neo4j_properties(),
            },
        )

    async def get_ingredient(self, name: str) -> IngredientNode | None:
        """Get an ingredient by name."""
        query = """
        MATCH (i:Ingredient {normalized_name: toLower($name)})
        RETURN i
        """
        results = await self.db.execute_query(query, {"name": name})
        if not results:
            return None

        data = results[0]["i"]
        return IngredientNode(
            name=data["name"],
            normalized_name=data.get("normalized_name", ""),
            description=data.get("description"),
            image_url=data.get("image_url"),
        )

    async def get_all_ingredients(self, limit: int = 1000) -> list[IngredientNode]:
        """Get all ingredients."""
        query = """
        MATCH (i:Ingredient)
        RETURN i
        ORDER BY i.name
        LIMIT $limit
        """
        results = await self.db.execute_query(query, {"limit": limit})

        return [
            IngredientNode(
                name=r["i"]["name"],
                normalized_name=r["i"].get("normalized_name", ""),
                description=r["i"].get("description"),
                image_url=r["i"].get("image_url"),
            )
            for r in results
        ]

    # =========================================================================
    # Product Operations
    # =========================================================================

    async def upsert_product(self, product: ProductNode, store_id: str) -> dict[str, Any]:
        """Create or update a product and link to store."""
        query = """
        MERGE (p:Product {id: $product_id})
        SET p += $props
        WITH p
        MERGE (s:Store {id: $store_id})
        MERGE (p)-[:IN_STORE]->(s)
        RETURN p
        """
        return await self.db.execute_write(
            query,
            {
                "product_id": product.id,
                "props": product.to_neo4j_properties(),
                "store_id": store_id,
            },
        )

    async def bulk_upsert_products(self, products: list[tuple[ProductNode, str]]) -> dict[str, Any]:
        """Bulk upsert products with their store relationships."""
        query = """
        UNWIND $products AS prod
        MERGE (p:Product {id: prod.id})
        SET p += prod.props
        WITH p, prod
        MERGE (s:Store {id: prod.store_id})
        MERGE (p)-[:IN_STORE]->(s)
        RETURN count(p) as count
        """
        return await self.db.execute_write(
            query,
            {
                "products": [
                    {
                        "id": p.id,
                        "props": p.to_neo4j_properties(),
                        "store_id": store_id,
                    }
                    for p, store_id in products
                ]
            },
        )

    # =========================================================================
    # Store Operations
    # =========================================================================

    async def upsert_store(self, store: StoreNode) -> dict[str, Any]:
        """Create or update a store."""
        query = """
        MERGE (s:Store {id: $store_id})
        SET s += $props
        RETURN s
        """
        return await self.db.execute_write(
            query,
            {
                "store_id": store.id,
                "props": store.to_neo4j_properties(),
            },
        )

    # =========================================================================
    # Category and Area Operations
    # =========================================================================

    async def create_category(self, category: CategoryNode) -> dict[str, Any]:
        """Create or update a category."""
        query = """
        MERGE (c:Category {name: $name})
        SET c += $props
        RETURN c
        """
        return await self.db.execute_write(
            query,
            {
                "name": category.name,
                "props": category.to_neo4j_properties(),
            },
        )

    async def create_area(self, area: AreaNode) -> dict[str, Any]:
        """Create or update an area."""
        query = """
        MERGE (a:Area {name: $name})
        RETURN a
        """
        return await self.db.execute_write(query, {"name": area.name})

    async def get_all_categories(self) -> list[CategoryNode]:
        """Get all categories."""
        query = "MATCH (c:Category) RETURN c ORDER BY c.name"
        results = await self.db.execute_query(query)
        return [
            CategoryNode(
                name=r["c"]["name"],
                description=r["c"].get("description"),
                thumbnail=r["c"].get("thumbnail"),
            )
            for r in results
        ]

    async def get_all_areas(self) -> list[AreaNode]:
        """Get all areas/cuisines."""
        query = "MATCH (a:Area) RETURN a ORDER BY a.name"
        results = await self.db.execute_query(query)
        return [AreaNode(name=r["a"]["name"]) for r in results]

    # =========================================================================
    # Matching Operations
    # =========================================================================

    async def create_ingredient_product_match(
        self,
        ingredient_name: str,
        product_id: str,
        match: MatchesRelationship,
    ) -> dict[str, Any]:
        """Create a MATCHES relationship between ingredient and product."""
        query = """
        MATCH (i:Ingredient {normalized_name: toLower($ingredient_name)})
        MATCH (p:Product {id: $product_id})
        MERGE (i)-[m:MATCHES]->(p)
        SET m += $props
        RETURN i, p, m
        """
        return await self.db.execute_write(
            query,
            {
                "ingredient_name": ingredient_name,
                "product_id": product_id,
                "props": match.to_neo4j_properties(),
            },
        )

    async def get_products_for_ingredient(
        self,
        ingredient_name: str,
        min_confidence: float = 0.5,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get matched products for an ingredient."""
        query = """
        MATCH (i:Ingredient {normalized_name: toLower($ingredient_name)})
              -[m:MATCHES]->(p:Product)
        WHERE m.confidence_score >= $min_confidence
        OPTIONAL MATCH (p)-[:IN_STORE]->(s:Store)
        RETURN p, m.confidence_score as confidence, m.match_type as match_type,
               s.name as store_name, s.id as store_id
        ORDER BY m.confidence_score DESC, p.price ASC
        LIMIT $limit
        """
        return await self.db.execute_query(
            query,
            {
                "ingredient_name": ingredient_name,
                "min_confidence": min_confidence,
                "limit": limit,
            },
        )

    async def get_unmatched_ingredients(self, limit: int = 100) -> list[str]:
        """Get ingredients without any product matches."""
        query = """
        MATCH (i:Ingredient)
        WHERE NOT (i)-[:MATCHES]->(:Product)
        RETURN i.name as name
        LIMIT $limit
        """
        results = await self.db.execute_query(query, {"limit": limit})
        return [r["name"] for r in results]

    # =========================================================================
    # Discount-Aware Queries
    # =========================================================================

    async def find_recipes_by_discounted_ingredients(
        self,
        min_discounted: int = 1,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find recipes that use currently discounted products."""
        query = """
        MATCH (r:Recipe)-[:CONTAINS]->(i:Ingredient)
              -[m:MATCHES]->(p:Product)
        WHERE p.has_active_discount = true
          AND m.confidence_score >= 0.7
        WITH r, count(DISTINCT i) as discounted_count,
             collect(DISTINCT {
                 ingredient: i.name,
                 product: p.name,
                 price: p.price,
                 discount_price: p.discount_price
             }) as discounted_items
        WHERE discounted_count >= $min_discounted
        OPTIONAL MATCH (r)-[:IN_CATEGORY]->(c:Category)
        OPTIONAL MATCH (r)-[:FROM_AREA]->(a:Area)
        RETURN r, c.name as category, a.name as area,
               discounted_count, discounted_items
        ORDER BY discounted_count DESC
        LIMIT $limit
        """
        return await self.db.execute_query(
            query,
            {"min_discounted": min_discounted, "limit": limit},
        )

    async def get_recipe_cost_estimate(
        self,
        recipe_id: str,
        prefer_discounts: bool = True,
    ) -> dict[str, Any]:
        """Estimate the cost of a recipe based on matched products."""
        query = """
        MATCH (r:Recipe {id: $recipe_id})-[:CONTAINS]->(i:Ingredient)
        OPTIONAL MATCH (i)-[m:MATCHES]->(p:Product)
        WHERE m.confidence_score >= 0.6
        WITH r, i, p, m
        ORDER BY
            CASE WHEN $prefer_discounts AND p.has_active_discount THEN 0 ELSE 1 END,
            m.confidence_score DESC,
            COALESCE(p.discount_price, p.price) ASC
        WITH r, i, collect(p)[0] as best_product
        RETURN r.id as recipe_id, r.name as recipe_name,
               collect({
                   ingredient: i.name,
                   product_name: best_product.name,
                   price: best_product.price,
                   discount_price: best_product.discount_price,
                   has_discount: best_product.has_active_discount
               }) as items,
               sum(COALESCE(best_product.discount_price, best_product.price, 0)) as total_cost,
               sum(CASE WHEN best_product.has_active_discount
                   THEN best_product.price - best_product.discount_price
                   ELSE 0 END) as total_savings
        """
        results = await self.db.execute_query(
            query,
            {"recipe_id": recipe_id, "prefer_discounts": prefer_discounts},
        )
        return results[0] if results else {}

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self) -> dict[str, int]:
        """Get graph database statistics."""
        query = """
        MATCH (r:Recipe) WITH count(r) as recipes
        MATCH (i:Ingredient) WITH recipes, count(i) as ingredients
        MATCH (p:Product) WITH recipes, ingredients, count(p) as products
        MATCH (c:Category) WITH recipes, ingredients, products, count(c) as categories
        MATCH (a:Area) WITH recipes, ingredients, products, categories, count(a) as areas
        MATCH (s:Store)
        WITH recipes, ingredients, products, categories, areas, count(s) as stores
        OPTIONAL MATCH ()-[m:MATCHES]->()
        WITH recipes, ingredients, products, categories, areas, stores, count(m) as matches
        RETURN recipes, ingredients, products, categories, areas, stores, matches
        """
        results = await self.db.execute_query(query)
        return results[0] if results else {}
