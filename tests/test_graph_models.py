"""Tests for graph database models."""

import pytest

from foodplanner.graph.models import (
    AreaNode,
    CategoryNode,
    ContainsRelationship,
    IngredientNode,
    MatchesRelationship,
    ProductNode,
    RecipeNode,
    RecipeSearchResult,
    RecipeWithIngredients,
    StoreNode,
)


class TestRecipeNode:
    """Tests for RecipeNode model."""

    def test_create_recipe_node(self):
        """Test creating a recipe node."""
        recipe = RecipeNode(
            id="52772",
            name="Teriyaki Chicken",
            instructions="Cook the chicken...",
            thumbnail="https://example.com/thumb.jpg",
            tags=["Meat", "Asian"],
        )

        assert recipe.id == "52772"
        assert recipe.name == "Teriyaki Chicken"
        assert recipe.tags == ["Meat", "Asian"]

    def test_recipe_node_to_neo4j(self):
        """Test converting recipe to Neo4j properties."""
        recipe = RecipeNode(
            id="52772",
            name="Teriyaki Chicken",
            instructions="Cook...",
            thumbnail=None,
            tags=["Meat"],
        )

        props = recipe.to_neo4j_properties()

        assert props["id"] == "52772"
        assert props["name"] == "Teriyaki Chicken"
        assert props["thumbnail"] is None
        assert props["tags"] == ["Meat"]
        assert "created_at" in props
        assert "updated_at" in props

    def test_recipe_node_defaults(self):
        """Test recipe node default values."""
        recipe = RecipeNode(id="123", name="Test")

        assert recipe.instructions == ""
        assert recipe.thumbnail is None
        assert recipe.source_url is None
        assert recipe.youtube_url is None
        assert recipe.tags == []


class TestIngredientNode:
    """Tests for IngredientNode model."""

    def test_create_ingredient_node(self):
        """Test creating an ingredient node."""
        ing = IngredientNode(name="Chicken Breast", description="Boneless chicken")

        assert ing.name == "Chicken Breast"
        assert ing.normalized_name == "chicken breast"
        assert ing.description == "Boneless chicken"

    def test_ingredient_normalization(self):
        """Test ingredient name normalization."""
        ing = IngredientNode(name="  GARLIC  ")
        assert ing.normalized_name == "garlic"

    def test_ingredient_to_neo4j(self):
        """Test converting ingredient to Neo4j properties."""
        ing = IngredientNode(name="Onion", description="Yellow onion")

        props = ing.to_neo4j_properties()

        assert props["name"] == "Onion"
        assert props["normalized_name"] == "onion"
        assert props["description"] == "Yellow onion"


class TestProductNode:
    """Tests for ProductNode model."""

    def test_create_product_node(self):
        """Test creating a product node."""
        product = ProductNode(
            id="p123",
            name="Chicken Breast 500g",
            brand="Farm Fresh",
            price=59.95,
            unit="500g",
            ean="1234567890123",
        )

        assert product.id == "p123"
        assert product.name == "Chicken Breast 500g"
        assert product.price == 59.95

    def test_product_with_discount(self):
        """Test product with active discount."""
        product = ProductNode(
            id="p123",
            name="Chicken Breast",
            price=59.95,
            unit="500g",
            discount_price=49.95,
            discount_percentage=16.7,
            has_active_discount=True,
        )

        assert product.has_active_discount is True
        assert product.discount_price == 49.95

    def test_product_to_neo4j(self):
        """Test converting product to Neo4j properties."""
        product = ProductNode(
            id="p123",
            name="Rice",
            price=24.95,
            unit="1kg",
        )

        props = product.to_neo4j_properties()

        assert props["id"] == "p123"
        assert props["name"] == "Rice"
        assert props["price"] == 24.95
        assert props["has_active_discount"] is False


class TestCategoryAndAreaNodes:
    """Tests for CategoryNode and AreaNode models."""

    def test_category_node(self):
        """Test creating a category node."""
        cat = CategoryNode(
            name="Seafood",
            description="Fish and shellfish dishes",
            thumbnail="https://example.com/seafood.png",
        )

        assert cat.name == "Seafood"
        props = cat.to_neo4j_properties()
        assert props["description"] == "Fish and shellfish dishes"

    def test_area_node(self):
        """Test creating an area node."""
        area = AreaNode(name="Japanese")

        assert area.name == "Japanese"
        props = area.to_neo4j_properties()
        assert props["name"] == "Japanese"


class TestStoreNode:
    """Tests for StoreNode model."""

    def test_store_node(self):
        """Test creating a store node."""
        store = StoreNode(
            id="store-123",
            name="Netto Vesterbro",
            brand="netto",
            city="Copenhagen",
            zip_code="1620",
        )

        assert store.id == "store-123"
        assert store.brand == "netto"

        props = store.to_neo4j_properties()
        assert props["city"] == "Copenhagen"


class TestRelationships:
    """Tests for relationship models."""

    def test_contains_relationship(self):
        """Test CONTAINS relationship model."""
        rel = ContainsRelationship(quantity="2", measure="cups")

        props = rel.to_neo4j_properties()

        assert props["quantity"] == "2"
        assert props["measure"] == "cups"

    def test_contains_relationship_defaults(self):
        """Test CONTAINS relationship defaults."""
        rel = ContainsRelationship()

        assert rel.quantity == ""
        assert rel.measure == ""

    def test_matches_relationship(self):
        """Test MATCHES relationship model."""
        rel = MatchesRelationship(
            confidence_score=0.85,
            match_type="fuzzy",
        )

        assert rel.confidence_score == 0.85
        assert rel.match_type == "fuzzy"

        props = rel.to_neo4j_properties()
        assert props["confidence_score"] == 0.85
        assert "matched_at" in props

    def test_matches_relationship_validation(self):
        """Test that confidence score is validated."""
        with pytest.raises(ValueError):
            MatchesRelationship(confidence_score=1.5, match_type="fuzzy")

        with pytest.raises(ValueError):
            MatchesRelationship(confidence_score=-0.1, match_type="fuzzy")


class TestResponseModels:
    """Tests for API response models."""

    def test_recipe_with_ingredients(self):
        """Test RecipeWithIngredients response model."""
        recipe = RecipeWithIngredients(
            id="52772",
            name="Teriyaki Chicken",
            instructions="Cook...",
            thumbnail=None,
            source_url=None,
            youtube_url=None,
            tags=["Meat"],
            category="Chicken",
            area="Japanese",
            ingredients=[
                {"name": "chicken", "quantity": "500g"},
                {"name": "soy sauce", "quantity": "2 tbsp"},
            ],
        )

        assert recipe.id == "52772"
        assert recipe.category == "Chicken"
        assert len(recipe.ingredients) == 2

    def test_recipe_search_result(self):
        """Test RecipeSearchResult model."""
        recipe = RecipeWithIngredients(
            id="52772",
            name="Teriyaki Chicken",
            instructions="...",
            thumbnail=None,
            source_url=None,
            youtube_url=None,
            tags=[],
        )

        result = RecipeSearchResult(
            recipe=recipe,
            matched_ingredients=5,
            discounted_ingredients=2,
            total_ingredients=8,
            estimated_cost=89.95,
            estimated_savings=15.0,
        )

        assert result.matched_ingredients == 5
        assert result.discounted_ingredients == 2
        assert result.estimated_savings == 15.0
