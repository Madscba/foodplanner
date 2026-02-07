"""Unit tests for the MealPlanOptimizer."""

from unittest.mock import AsyncMock

import pytest

from foodplanner.graph.models import RecipeSearchResult, RecipeWithIngredients
from foodplanner.plan.optimizer import (
    DietaryPreference,
    MealPlanOptimizer,
    OptimizedRecipe,
    RecipeScore,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_graph_service():
    """Create a mock GraphService."""
    service = AsyncMock()
    return service


@pytest.fixture
def sample_recipes():
    """Sample RecipeWithIngredients for testing."""
    return [
        RecipeWithIngredients(
            id="recipe-1",
            name="Chicken Stir Fry",
            instructions="Cook chicken with vegetables",
            thumbnail="https://example.com/chicken.jpg",
            source_url=None,
            youtube_url=None,
            category="Chicken",
            area="Chinese",
            tags=["easy", "quick"],
            ingredients=[
                {"name": "chicken breast", "quantity": "500", "measure": "g"},
                {"name": "bell pepper", "quantity": "2", "measure": ""},
                {"name": "soy sauce", "quantity": "3", "measure": "tbsp"},
            ],
        ),
        RecipeWithIngredients(
            id="recipe-2",
            name="Beef Tacos",
            instructions="Cook beef with spices",
            thumbnail="https://example.com/tacos.jpg",
            source_url=None,
            youtube_url=None,
            category="Beef",
            area="Mexican",
            tags=["spicy"],
            ingredients=[
                {"name": "ground beef", "quantity": "400", "measure": "g"},
                {"name": "taco shells", "quantity": "8", "measure": ""},
                {"name": "cheese", "quantity": "100", "measure": "g"},
            ],
        ),
        RecipeWithIngredients(
            id="recipe-3",
            name="Vegetable Pasta",
            instructions="Cook pasta with vegetables",
            thumbnail="https://example.com/pasta.jpg",
            source_url=None,
            youtube_url=None,
            category="Vegetarian",
            area="Italian",
            tags=["vegetarian"],
            ingredients=[
                {"name": "pasta", "quantity": "300", "measure": "g"},
                {"name": "tomato sauce", "quantity": "200", "measure": "ml"},
                {"name": "bell pepper", "quantity": "1", "measure": ""},
            ],
        ),
        RecipeWithIngredients(
            id="recipe-4",
            name="Salmon Teriyaki",
            instructions="Glaze salmon with teriyaki",
            thumbnail="https://example.com/salmon.jpg",
            source_url=None,
            youtube_url=None,
            category="Seafood",
            area="Japanese",
            tags=["healthy"],
            ingredients=[
                {"name": "salmon fillet", "quantity": "400", "measure": "g"},
                {"name": "soy sauce", "quantity": "4", "measure": "tbsp"},
                {"name": "honey", "quantity": "2", "measure": "tbsp"},
            ],
        ),
    ]


@pytest.fixture
def sample_discount_results(sample_recipes):
    """Sample RecipeSearchResult with discount info."""
    return [
        RecipeSearchResult(
            recipe=sample_recipes[0],
            discounted_ingredients=3,
            estimated_cost=85.0,
            estimated_savings=15.0,
        ),
        RecipeSearchResult(
            recipe=sample_recipes[1],
            discounted_ingredients=2,
            estimated_cost=95.0,
            estimated_savings=10.0,
        ),
        RecipeSearchResult(
            recipe=sample_recipes[3],
            discounted_ingredients=1,
            estimated_cost=120.0,
            estimated_savings=5.0,
        ),
    ]


# =============================================================================
# RecipeScore Tests
# =============================================================================


class TestRecipeScore:
    """Tests for RecipeScore dataclass."""

    def test_recipe_score_defaults(self, sample_recipes):
        """Test RecipeScore has correct defaults."""
        score = RecipeScore(recipe=sample_recipes[0])

        assert score.discount_count == 0
        assert score.discounted_ingredients == []
        assert score.estimated_cost == 0.0
        assert score.estimated_savings == 0.0
        assert score.ingredient_overlap_score == 0.0
        assert score.total_score == 0.0
        assert score.suggestion_reason == ""

    def test_recipe_score_with_values(self, sample_recipes):
        """Test RecipeScore with custom values."""
        score = RecipeScore(
            recipe=sample_recipes[0],
            discount_count=3,
            discounted_ingredients=["chicken", "soy sauce"],
            estimated_cost=85.0,
            estimated_savings=15.0,
            total_score=9.5,
            suggestion_reason="Uses 3 discounted ingredients",
        )

        assert score.discount_count == 3
        assert score.estimated_savings == 15.0
        assert "chicken" in score.discounted_ingredients


# =============================================================================
# DietaryPreference Tests
# =============================================================================


class TestDietaryPreference:
    """Tests for DietaryPreference dataclass."""

    def test_dietary_preference_creation(self):
        """Test creating dietary preferences."""
        pref = DietaryPreference(name="vegetarian", type="preference")
        assert pref.name == "vegetarian"
        assert pref.type == "preference"

    def test_dietary_preference_allergy(self):
        """Test creating allergy preference."""
        pref = DietaryPreference(name="peanut", type="allergy")
        assert pref.name == "peanut"
        assert pref.type == "allergy"


# =============================================================================
# MealPlanOptimizer Tests
# =============================================================================


class TestMealPlanOptimizer:
    """Tests for MealPlanOptimizer class."""

    @pytest.mark.asyncio
    async def test_optimizer_initialization(self, mock_graph_service):
        """Test optimizer initializes correctly."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        assert optimizer.graph_service == mock_graph_service
        assert optimizer.DISCOUNT_WEIGHT == 3.0
        assert optimizer.COST_WEIGHT == -0.1

    @pytest.mark.asyncio
    async def test_optimize_returns_recipes(
        self, mock_graph_service, sample_recipes, sample_discount_results
    ):
        """Test optimize returns optimized recipes."""
        # Setup mocks
        mock_graph_service.find_recipes_with_discounts.return_value = sample_discount_results
        mock_graph_service.get_recipe.side_effect = lambda rid: next(
            (r for r in sample_recipes if r.id == rid), None
        )
        mock_graph_service.estimate_recipe_cost.return_value = {
            "total_cost": 85.0,
            "total_savings": 15.0,
            "items": [
                {"ingredient": "chicken", "has_discount": True},
            ],
        }
        mock_graph_service.search_recipes.return_value = sample_recipes

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.optimize(
            days=3,
            people_count=2,
        )

        assert len(result) <= 3
        assert all(isinstance(r, OptimizedRecipe) for r in result)

    @pytest.mark.asyncio
    async def test_optimize_respects_days_limit(
        self, mock_graph_service, sample_recipes, sample_discount_results
    ):
        """Test optimizer returns at most 'days' recipes."""
        mock_graph_service.find_recipes_with_discounts.return_value = sample_discount_results
        mock_graph_service.get_recipe.side_effect = lambda rid: next(
            (r for r in sample_recipes if r.id == rid), None
        )
        mock_graph_service.estimate_recipe_cost.return_value = {
            "total_cost": 50.0,
            "total_savings": 5.0,
            "items": [],
        }
        mock_graph_service.search_recipes.return_value = sample_recipes

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.optimize(days=2, people_count=1)

        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_optimize_with_budget_constraint(
        self, mock_graph_service, sample_recipes, sample_discount_results
    ):
        """Test optimizer respects budget constraints."""
        mock_graph_service.find_recipes_with_discounts.return_value = sample_discount_results
        mock_graph_service.get_recipe.side_effect = lambda rid: next(
            (r for r in sample_recipes if r.id == rid), None
        )
        mock_graph_service.estimate_recipe_cost.return_value = {
            "total_cost": 100.0,  # High cost
            "total_savings": 0.0,
            "items": [],
        }
        mock_graph_service.search_recipes.return_value = sample_recipes

        optimizer = MealPlanOptimizer(mock_graph_service)

        # With very low budget, should get fewer recipes
        result = await optimizer.optimize(
            days=5,
            people_count=2,
            budget_max=100.0,  # Low budget
        )

        # Total cost should be within budget
        total_cost = sum(r.estimated_cost for r in result)
        assert total_cost <= 100.0 or len(result) == 0

    @pytest.mark.asyncio
    async def test_optimize_empty_when_no_recipes(self, mock_graph_service):
        """Test optimizer returns empty list when no recipes available."""
        mock_graph_service.find_recipes_with_discounts.return_value = []
        mock_graph_service.search_recipes.return_value = []

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.optimize(days=3, people_count=2)

        assert result == []


# =============================================================================
# Dietary Filtering Tests
# =============================================================================


class TestDietaryFiltering:
    """Tests for dietary preference filtering."""

    @pytest.mark.asyncio
    async def test_vegetarian_filter(
        self, mock_graph_service, sample_recipes, sample_discount_results
    ):
        """Test vegetarian filter excludes meat recipes."""
        mock_graph_service.find_recipes_with_discounts.return_value = sample_discount_results
        mock_graph_service.get_recipe.side_effect = lambda rid: next(
            (r for r in sample_recipes if r.id == rid), None
        )
        mock_graph_service.estimate_recipe_cost.return_value = {
            "total_cost": 50.0,
            "total_savings": 5.0,
            "items": [],
        }
        mock_graph_service.search_recipes.return_value = [
            r for r in sample_recipes if r.category == "Vegetarian"
        ]

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.optimize(
            days=3,
            people_count=2,
            dietary_preferences=[DietaryPreference(name="vegetarian", type="preference")],
        )

        # Should not include recipes with meat ingredients
        for recipe in result:
            assert "chicken" not in recipe.recipe_name.lower()
            assert "beef" not in recipe.recipe_name.lower()

    def test_matches_dietary_vegetarian(self, mock_graph_service, sample_recipes):
        """Test _matches_dietary for vegetarian preference."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        vegetarian_pref = [DietaryPreference(name="vegetarian", type="preference")]

        # Vegetable pasta should match
        assert optimizer._matches_dietary(sample_recipes[2], vegetarian_pref)

        # Chicken stir fry should not match
        assert not optimizer._matches_dietary(sample_recipes[0], vegetarian_pref)

    def test_matches_dietary_vegan(self, mock_graph_service, sample_recipes):
        """Test _matches_dietary for vegan preference."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        vegan_pref = [DietaryPreference(name="vegan", type="preference")]

        # Beef tacos has cheese, should not match
        assert not optimizer._matches_dietary(sample_recipes[1], vegan_pref)

    def test_matches_dietary_gluten_free(self, mock_graph_service, sample_recipes):
        """Test _matches_dietary for gluten-free preference."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        gf_pref = [DietaryPreference(name="gluten-free", type="preference")]

        # Vegetable pasta has pasta (contains gluten), should not match
        assert not optimizer._matches_dietary(sample_recipes[2], gf_pref)


# =============================================================================
# Scoring Tests
# =============================================================================


class TestScoring:
    """Tests for recipe scoring logic."""

    def test_generate_reason_with_discounts(self, mock_graph_service, sample_recipes):
        """Test reason generation with discounts."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        scored = RecipeScore(
            recipe=sample_recipes[0],
            discount_count=3,
            estimated_savings=15.0,
        )

        reason = optimizer._generate_reason(scored)

        assert "3 discounted" in reason
        assert "15 kr" in reason

    def test_generate_reason_budget_friendly(self, mock_graph_service, sample_recipes):
        """Test reason generation for budget-friendly recipe."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        scored = RecipeScore(
            recipe=sample_recipes[0],
            discount_count=0,
            estimated_cost=30.0,  # Under 50 is budget-friendly
        )

        reason = optimizer._generate_reason(scored)

        assert "Budget-friendly" in reason

    def test_generate_reason_default(self, mock_graph_service, sample_recipes):
        """Test default reason when no special conditions."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        scored = RecipeScore(
            recipe=sample_recipes[0],
            discount_count=0,
            estimated_cost=100.0,
            estimated_savings=0.0,
        )

        reason = optimizer._generate_reason(scored)

        assert "variety" in reason.lower()


# =============================================================================
# Replacement Tests
# =============================================================================


class TestFindReplacement:
    """Tests for find_replacement functionality."""

    @pytest.mark.asyncio
    async def test_find_replacement_cheaper(self, mock_graph_service, sample_recipes):
        """Test finding cheaper replacement recipes."""
        mock_graph_service.get_recipe.return_value = sample_recipes[0]
        mock_graph_service.estimate_recipe_cost.side_effect = [
            {"total_cost": 100.0},  # Original
            {"total_cost": 50.0},  # Cheaper alternative
            {"total_cost": 150.0},  # More expensive
            {"total_cost": 60.0},  # Another cheaper
        ]
        mock_graph_service.search_recipes.return_value = sample_recipes[1:]

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.find_replacement(
            recipe_id="recipe-1",
            criteria="cheaper",
            limit=3,
        )

        # Should only return recipes cheaper than original
        for recipe in result:
            assert recipe.estimated_cost < 100.0

    @pytest.mark.asyncio
    async def test_find_replacement_different(self, mock_graph_service, sample_recipes):
        """Test finding different category replacement."""
        mock_graph_service.get_recipe.return_value = sample_recipes[0]
        mock_graph_service.estimate_recipe_cost.return_value = {
            "total_cost": 50.0,
            "total_savings": 0.0,
        }
        mock_graph_service.search_recipes.return_value = sample_recipes

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.find_replacement(
            recipe_id="recipe-1",
            criteria="different",
            limit=5,
        )

        # Should not include recipes from same category (Chicken)
        for recipe in result:
            # The original is Chicken, so alternatives should be different
            assert recipe.category != "Chicken" or recipe.recipe_id == "recipe-1"

    @pytest.mark.asyncio
    async def test_find_replacement_excludes_original(self, mock_graph_service, sample_recipes):
        """Test that original recipe is excluded from replacements."""
        mock_graph_service.get_recipe.return_value = sample_recipes[0]
        mock_graph_service.estimate_recipe_cost.return_value = {
            "total_cost": 50.0,
            "total_savings": 0.0,
        }
        mock_graph_service.search_recipes.return_value = sample_recipes

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.find_replacement(
            recipe_id="recipe-1",
            criteria="cheaper",
            limit=10,
        )

        # Original recipe should not be in results
        assert all(r.recipe_id != "recipe-1" for r in result)

    @pytest.mark.asyncio
    async def test_find_replacement_empty_when_no_recipe(self, mock_graph_service):
        """Test replacement returns empty when original not found."""
        mock_graph_service.get_recipe.return_value = None

        optimizer = MealPlanOptimizer(mock_graph_service)

        result = await optimizer.find_replacement(
            recipe_id="nonexistent",
            criteria="cheaper",
        )

        assert result == []


# =============================================================================
# Greedy Selection Tests
# =============================================================================


class TestGreedySelection:
    """Tests for the greedy selection algorithm."""

    def test_greedy_select_category_variety(self, mock_graph_service, sample_recipes):
        """Test that greedy selection ensures category variety."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        # Create scored recipes all from same category
        scored = [
            RecipeScore(
                recipe=RecipeWithIngredients(
                    id=f"r{i}",
                    name=f"Recipe {i}",
                    instructions="...",
                    thumbnail=None,
                    source_url=None,
                    youtube_url=None,
                    tags=[],
                    category="Chicken",
                    area="American",
                    ingredients=[{"name": "chicken"}],
                ),
                total_score=10.0 - i,
                estimated_cost=50.0,
            )
            for i in range(5)
        ]

        selected = optimizer._greedy_select(
            scored,
            days=5,
            budget_max=None,
            people_count=2,
        )

        # Should select at most 2 from same category
        chicken_count = sum(1 for r in selected if r.category == "Chicken")
        assert chicken_count <= 2

    def test_greedy_select_respects_budget(self, mock_graph_service, sample_recipes):
        """Test that greedy selection respects budget."""
        optimizer = MealPlanOptimizer(mock_graph_service)

        scored = [
            RecipeScore(
                recipe=sample_recipes[i],
                total_score=10.0,
                estimated_cost=100.0,  # 100 per recipe, 200 per person for 2
            )
            for i in range(4)
        ]

        selected = optimizer._greedy_select(
            scored,
            days=4,
            budget_max=200.0,  # Only allows 1 recipe for 2 people
            people_count=2,
        )

        total_cost = sum(r.estimated_cost for r in selected)
        assert total_cost <= 200.0
