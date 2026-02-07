"""Tests for TheMealDB API connector."""

from unittest.mock import AsyncMock, patch

import pytest

from foodplanner.ingest.connectors.base import ConnectorError
from foodplanner.ingest.connectors.mealdb import (
    MealDBConnector,
    MealIngredient,
    ParsedMeal,
)


class TestParsedMeal:
    """Tests for ParsedMeal parsing from API responses."""

    def test_parse_meal_basic(self, mock_mealdb_meal_response):
        """Test parsing a basic meal response."""
        meal_data = mock_mealdb_meal_response["meals"][0]
        meal = ParsedMeal.from_api_response(meal_data)

        assert meal.id == "52772"
        assert meal.name == "Teriyaki Chicken Casserole"
        assert meal.category == "Chicken"
        assert meal.area == "Japanese"
        assert "Preheat oven" in meal.instructions
        assert meal.thumbnail == "https://www.themealdb.com/images/media/meals/wvpsxx1468256321.jpg"
        assert meal.tags == ["Meat", "Casserole"]
        assert meal.youtube_url == "https://www.youtube.com/watch?v=4aZr5hZXP_s"
        assert meal.source_url == "https://example.com/recipe"

    def test_parse_meal_ingredients(self, mock_mealdb_meal_response):
        """Test parsing ingredients from meal response."""
        meal_data = mock_mealdb_meal_response["meals"][0]
        meal = ParsedMeal.from_api_response(meal_data)

        # Should have 9 ingredients (empty ones filtered out)
        assert len(meal.ingredients) == 9

        # Check first ingredient
        assert meal.ingredients[0].name == "soy sauce"
        assert meal.ingredients[0].measure == "3/4 cup"

        # Check normalized name
        assert meal.ingredients[0].normalized_name == "soy sauce"

    def test_parse_meal_empty_ingredients(self):
        """Test parsing meal with no ingredients."""
        meal_data = {
            "idMeal": "12345",
            "strMeal": "Empty Meal",
            "strCategory": "Test",
            "strArea": "Test",
            "strInstructions": "No instructions",
            **{f"strIngredient{i}": "" for i in range(1, 21)},
            **{f"strMeasure{i}": "" for i in range(1, 21)},
        }
        meal = ParsedMeal.from_api_response(meal_data)

        assert meal.id == "12345"
        assert meal.name == "Empty Meal"
        assert meal.ingredients == []

    def test_parse_meal_whitespace_ingredients(self):
        """Test that whitespace-only ingredients are filtered."""
        meal_data = {
            "idMeal": "12345",
            "strMeal": "Whitespace Meal",
            "strCategory": "Test",
            "strArea": "Test",
            "strInstructions": "...",
            "strIngredient1": "chicken",
            "strIngredient2": "  ",  # Whitespace only
            "strIngredient3": "\t",  # Tab only
            "strIngredient4": "rice",
            **{f"strIngredient{i}": "" for i in range(5, 21)},
            **{f"strMeasure{i}": "" for i in range(1, 21)},
        }
        meal = ParsedMeal.from_api_response(meal_data)

        assert len(meal.ingredients) == 2
        assert meal.ingredients[0].name == "chicken"
        assert meal.ingredients[1].name == "rice"

    def test_parse_meal_missing_optional_fields(self):
        """Test parsing meal with missing optional fields."""
        meal_data = {
            "idMeal": "12345",
            "strMeal": "Minimal Meal",
            "strCategory": None,
            "strArea": None,
            "strInstructions": "",
            "strMealThumb": None,
            "strTags": None,
            "strYoutube": None,
            "strSource": None,
            **{f"strIngredient{i}": "" for i in range(1, 21)},
            **{f"strMeasure{i}": "" for i in range(1, 21)},
        }
        meal = ParsedMeal.from_api_response(meal_data)

        assert meal.id == "12345"
        assert meal.name == "Minimal Meal"
        assert meal.category is None
        assert meal.area is None
        assert meal.thumbnail is None
        assert meal.tags == []


class TestMealIngredient:
    """Tests for MealIngredient data class."""

    def test_normalized_name(self):
        """Test ingredient name normalization."""
        ing = MealIngredient(name="  Fresh Garlic  ", measure="2 cloves")
        assert ing.normalized_name == "fresh garlic"

    def test_measure_preserved(self):
        """Test that measure is preserved as-is."""
        ing = MealIngredient(name="Salt", measure="To taste")
        assert ing.measure == "To taste"


class TestMealDBConnector:
    """Tests for MealDBConnector API calls."""

    @pytest.fixture
    def connector(self):
        """Create a connector instance."""
        return MealDBConnector(api_key="1", base_url="https://www.themealdb.com/api/json/v1")

    @pytest.mark.asyncio
    async def test_get_categories(self, connector, mock_mealdb_categories_response):
        """Test fetching categories."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_mealdb_categories_response,
                status_code=200,
                headers={},
            )

            categories = await connector.get_categories()

            assert len(categories) == 3
            assert categories[0]["strCategory"] == "Beef"
            mock_request.assert_called_once_with("categories.php")

    @pytest.mark.asyncio
    async def test_get_areas(self, connector, mock_mealdb_areas_response):
        """Test fetching areas/cuisines."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_mealdb_areas_response,
                status_code=200,
                headers={},
            )

            areas = await connector.get_areas()

            assert len(areas) == 7
            assert "Italian" in areas
            assert "Japanese" in areas
            mock_request.assert_called_once_with("list.php", params={"a": "list"})

    @pytest.mark.asyncio
    async def test_get_ingredients_list(self, connector, mock_mealdb_ingredients_response):
        """Test fetching ingredients list."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_mealdb_ingredients_response,
                status_code=200,
                headers={},
            )

            ingredients = await connector.get_ingredients_list()

            assert len(ingredients) == 5
            assert ingredients[0]["name"] == "Chicken"
            mock_request.assert_called_once_with("list.php", params={"i": "list"})

    @pytest.mark.asyncio
    async def test_search_meals_by_name(self, connector, mock_mealdb_search_response):
        """Test searching meals by name."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_mealdb_search_response,
                status_code=200,
                headers={},
            )

            meals = await connector.search_meals_by_name("Teriyaki")

            assert len(meals) == 2
            assert isinstance(meals[0], ParsedMeal)
            assert meals[0].name == "Teriyaki Chicken Casserole"
            mock_request.assert_called_once_with("search.php", params={"s": "Teriyaki"})

    @pytest.mark.asyncio
    async def test_search_meals_by_letter(self, connector, mock_mealdb_search_response):
        """Test searching meals by first letter."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_mealdb_search_response,
                status_code=200,
                headers={},
            )

            meals = await connector.search_meals_by_letter("T")

            assert len(meals) == 2
            mock_request.assert_called_once_with("search.php", params={"f": "t"})

    @pytest.mark.asyncio
    async def test_get_meal_by_id(self, connector, mock_mealdb_meal_response):
        """Test getting a single meal by ID."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_mealdb_meal_response,
                status_code=200,
                headers={},
            )

            meal = await connector.get_meal_by_id("52772")

            assert meal is not None
            assert meal.id == "52772"
            assert meal.name == "Teriyaki Chicken Casserole"
            mock_request.assert_called_once_with("lookup.php", params={"i": "52772"})

    @pytest.mark.asyncio
    async def test_get_meal_by_id_not_found(self, connector):
        """Test getting a non-existent meal."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data={"meals": None},
                status_code=200,
                headers={},
            )

            meal = await connector.get_meal_by_id("99999")

            assert meal is None

    @pytest.mark.asyncio
    async def test_filter_by_category(self, connector):
        """Test filtering meals by category."""
        mock_response = {
            "meals": [
                {"strMeal": "Beef and Mustard Pie", "strMealThumb": "...", "idMeal": "52874"},
                {"strMeal": "Beef and Oyster pie", "strMealThumb": "...", "idMeal": "52878"},
            ]
        }

        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data=mock_response,
                status_code=200,
                headers={},
            )

            meals = await connector.filter_by_category("Beef")

            assert len(meals) == 2
            mock_request.assert_called_once_with("filter.php", params={"c": "Beef"})

    @pytest.mark.asyncio
    async def test_health_check_success(self, connector):
        """Test successful health check."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            from foodplanner.ingest.connectors.base import ConnectorResponse

            mock_request.return_value = ConnectorResponse(
                data={"categories": []},
                status_code=200,
                headers={},
            )

            result = await connector.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, connector):
        """Test failed health check."""
        with patch.object(connector, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ConnectorError("Connection failed")

            result = await connector.health_check()

            assert result is False

    @pytest.mark.asyncio
    async def test_connector_context_manager(self, connector):
        """Test using connector as async context manager."""
        with patch.object(connector, "_get_client", new_callable=AsyncMock):
            with patch.object(connector, "close", new_callable=AsyncMock) as mock_close:
                async with connector as conn:
                    assert conn is connector
                mock_close.assert_called_once()
