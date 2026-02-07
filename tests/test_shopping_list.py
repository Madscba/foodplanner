"""Unit tests for shopping list generation and unit normalization."""

from unittest.mock import AsyncMock

import pytest

from foodplanner.normalize.units import (
    aggregate_ingredients,
    can_aggregate,
    extract_quantity_and_unit,
    normalize_ingredient_name,
    normalize_quantity,
    parse_quantity_string,
)
from foodplanner.plan.shopping_list import (
    ShoppingItem,
    ShoppingList,
    ShoppingListGenerator,
)

# =============================================================================
# Unit Normalization Tests
# =============================================================================


class TestParseQuantityString:
    """Tests for parse_quantity_string function."""

    def test_parse_integer(self):
        """Test parsing simple integers."""
        assert parse_quantity_string("2") == 2.0
        assert parse_quantity_string("10") == 10.0

    def test_parse_decimal(self):
        """Test parsing decimal numbers."""
        assert parse_quantity_string("1.5") == 1.5
        assert parse_quantity_string("0.25") == 0.25

    def test_parse_fraction(self):
        """Test parsing simple fractions."""
        assert parse_quantity_string("1/2") == 0.5
        assert parse_quantity_string("1/4") == 0.25
        assert parse_quantity_string("3/4") == 0.75

    def test_parse_mixed_fraction(self):
        """Test parsing mixed fractions like '1 1/2'."""
        assert parse_quantity_string("1 1/2") == 1.5
        assert parse_quantity_string("2 1/4") == 2.25

    def test_parse_range(self):
        """Test parsing ranges like '2-3'."""
        assert parse_quantity_string("2-3") == 2.5
        assert parse_quantity_string("1-2") == 1.5

    def test_parse_empty_or_special(self):
        """Test parsing empty or special values."""
        assert parse_quantity_string("") == 1.0
        assert parse_quantity_string("to taste") == 1.0
        assert parse_quantity_string("pinch") == 1.0


class TestNormalizeQuantity:
    """Tests for normalize_quantity function."""

    def test_volume_ml(self):
        """Test normalizing milliliters."""
        result = normalize_quantity("500", "ml")
        assert result.value == 500.0
        assert result.unit == "ml"
        assert result.unit_type == "volume"

    def test_volume_liters(self):
        """Test normalizing liters to ml."""
        result = normalize_quantity("1", "l")
        assert result.value == 1000.0
        assert result.unit == "ml"
        assert result.unit_type == "volume"

    def test_volume_cups(self):
        """Test normalizing cups to ml."""
        result = normalize_quantity("2", "cups")
        assert result.value == pytest.approx(473.176, rel=0.01)
        assert result.unit_type == "volume"

    def test_volume_tablespoons(self):
        """Test normalizing tablespoons to ml."""
        result = normalize_quantity("3", "tbsp")
        assert result.value == pytest.approx(44.36, rel=0.01)
        assert result.unit_type == "volume"

    def test_weight_grams(self):
        """Test normalizing grams."""
        result = normalize_quantity("250", "g")
        assert result.value == 250.0
        assert result.unit == "g"
        assert result.unit_type == "weight"

    def test_weight_kg(self):
        """Test normalizing kilograms to grams."""
        result = normalize_quantity("1.5", "kg")
        assert result.value == 1500.0
        assert result.unit == "g"
        assert result.unit_type == "weight"

    def test_weight_ounces(self):
        """Test normalizing ounces to grams."""
        result = normalize_quantity("8", "oz")
        assert result.value == pytest.approx(226.8, rel=0.01)
        assert result.unit_type == "weight"

    def test_count_pieces(self):
        """Test normalizing count-based units."""
        result = normalize_quantity("3", "pieces")
        assert result.value == 3.0
        assert result.unit_type == "count"

    def test_count_cloves(self):
        """Test normalizing cloves."""
        result = normalize_quantity("4", "cloves")
        assert result.value == 4.0
        assert result.unit_type == "count"

    def test_no_unit(self):
        """Test normalizing without a unit."""
        result = normalize_quantity("2", "")
        assert result.value == 2.0
        assert result.unit_type == "count"


class TestNormalizedQuantityArithmetic:
    """Tests for NormalizedQuantity arithmetic operations."""

    def test_add_same_unit_type(self):
        """Test adding quantities of same unit type."""
        qty1 = normalize_quantity("500", "ml")
        qty2 = normalize_quantity("250", "ml")
        result = qty1 + qty2
        assert result.value == 750.0
        assert result.unit_type == "volume"

    def test_add_different_volume_units(self):
        """Test adding different volume units (cups + ml)."""
        qty1 = normalize_quantity("1", "cup")  # ~237ml
        qty2 = normalize_quantity("263", "ml")  # 263ml
        result = qty1 + qty2
        assert result.value == pytest.approx(500.0, rel=0.01)

    def test_add_different_unit_types(self):
        """Test adding different unit types returns first."""
        qty1 = normalize_quantity("500", "ml")
        qty2 = normalize_quantity("250", "g")
        result = qty1 + qty2
        assert result.value == 500.0  # Returns first quantity unchanged


class TestNormalizedQuantityDisplay:
    """Tests for NormalizedQuantity display formatting."""

    def test_display_liters(self):
        """Test displaying large volumes as liters."""
        qty = normalize_quantity("1500", "ml")
        display_qty, display_unit = qty.to_display_string()
        assert display_qty == "1.5"
        assert display_unit == "L"

    def test_display_deciliters(self):
        """Test displaying medium volumes as deciliters."""
        qty = normalize_quantity("200", "ml")
        display_qty, display_unit = qty.to_display_string()
        assert display_qty == "2"
        assert display_unit == "dl"

    def test_display_milliliters(self):
        """Test displaying small volumes as milliliters."""
        qty = normalize_quantity("50", "ml")
        display_qty, display_unit = qty.to_display_string()
        assert display_qty == "50"
        assert display_unit == "ml"

    def test_display_kilograms(self):
        """Test displaying large weights as kilograms."""
        qty = normalize_quantity("1500", "g")
        display_qty, display_unit = qty.to_display_string()
        assert display_qty == "1.5"
        assert display_unit == "kg"

    def test_display_grams(self):
        """Test displaying small weights as grams."""
        qty = normalize_quantity("250", "g")
        display_qty, display_unit = qty.to_display_string()
        assert display_qty == "250"
        assert display_unit == "g"


class TestExtractQuantityAndUnit:
    """Tests for extract_quantity_and_unit function."""

    def test_extract_with_space(self):
        """Test extracting from '2 cups'."""
        qty, unit = extract_quantity_and_unit("2 cups")
        assert qty == "2"
        assert unit == "cups"

    def test_extract_without_space(self):
        """Test extracting from '500g'."""
        qty, unit = extract_quantity_and_unit("500g")
        assert qty == "500"
        assert unit == "g"

    def test_extract_fraction(self):
        """Test extracting from '1/2 tsp'."""
        qty, unit = extract_quantity_and_unit("1/2 tsp")
        assert qty == "1/2"
        assert unit == "tsp"

    def test_extract_empty(self):
        """Test extracting from empty string."""
        qty, unit = extract_quantity_and_unit("")
        assert qty == "1"
        assert unit == ""


class TestCanAggregate:
    """Tests for can_aggregate function."""

    def test_same_volume_units(self):
        """Test that volume units can aggregate."""
        assert can_aggregate("ml", "cups")
        assert can_aggregate("l", "tbsp")

    def test_same_weight_units(self):
        """Test that weight units can aggregate."""
        assert can_aggregate("g", "kg")
        assert can_aggregate("oz", "lb")

    def test_different_unit_types(self):
        """Test that different unit types cannot aggregate."""
        assert not can_aggregate("ml", "g")
        assert not can_aggregate("cups", "kg")


class TestNormalizeIngredientName:
    """Tests for normalize_ingredient_name function."""

    def test_lowercase(self):
        """Test lowercase conversion."""
        assert normalize_ingredient_name("Chicken Breast") == "chicken breast"

    def test_remove_descriptors(self):
        """Test removing preparation descriptors."""
        assert normalize_ingredient_name("fresh basil") == "basil"
        assert normalize_ingredient_name("dried oregano") == "oregano"
        assert normalize_ingredient_name("chopped onion") == "onion"

    def test_multiple_descriptors(self):
        """Test removing multiple descriptors."""
        assert normalize_ingredient_name("fresh chopped parsley") == "parsley"


class TestAggregateIngredients:
    """Tests for aggregate_ingredients function."""

    def test_aggregate_same_ingredient(self):
        """Test aggregating same ingredient."""
        ingredients = [
            {"name": "onion", "quantity": "1", "measure": ""},
            {"name": "onion", "quantity": "2", "measure": ""},
        ]
        result = aggregate_ingredients(ingredients, "recipe-1")

        assert "onion" in result
        assert result["onion"].total_quantity.value == 3.0

    def test_aggregate_with_units(self):
        """Test aggregating with unit conversion."""
        ingredients = [
            {"name": "milk", "quantity": "1", "measure": "cup"},
            {"name": "milk", "quantity": "250", "measure": "ml"},
        ]
        result = aggregate_ingredients(ingredients, "recipe-1")

        assert "milk" in result
        # 1 cup (~237ml) + 250ml = ~487ml
        assert result["milk"].total_quantity.value == pytest.approx(486.6, rel=0.01)

    def test_normalize_ingredient_names(self):
        """Test that ingredient names are normalized."""
        ingredients = [
            {"name": "Fresh Basil", "quantity": "1", "measure": "tbsp"},
            {"name": "basil", "quantity": "1", "measure": "tbsp"},
        ]
        result = aggregate_ingredients(ingredients, "recipe-1")

        # Both should be aggregated under "basil"
        assert "basil" in result
        assert len(result) == 1


# =============================================================================
# Shopping List Tests
# =============================================================================


class TestShoppingItem:
    """Tests for ShoppingItem dataclass."""

    def test_effective_price_discount(self):
        """Test effective_price returns discount price when available."""
        item = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            price=50.0,
            discount_price=40.0,
        )
        assert item.effective_price == 40.0

    def test_effective_price_regular(self):
        """Test effective_price returns regular price when no discount."""
        item = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            price=50.0,
        )
        assert item.effective_price == 50.0

    def test_savings(self):
        """Test savings calculation."""
        item = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            price=50.0,
            discount_price=40.0,
        )
        assert item.savings == 10.0

    def test_has_discount(self):
        """Test has_discount property."""
        item_with_discount = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            price=50.0,
            discount_price=40.0,
        )
        assert item_with_discount.has_discount is True

        item_without_discount = ShoppingItem(
            ingredient_name="beef",
            normalized_name="beef",
            quantity="500",
            unit="g",
            price=60.0,
        )
        assert item_without_discount.has_discount is False


class TestShoppingList:
    """Tests for ShoppingList dataclass."""

    def test_add_item_updates_totals(self):
        """Test that add_item updates computed totals."""
        shopping_list = ShoppingList(meal_plan_id="plan-1")

        item = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            price=50.0,
            discount_price=40.0,
            product_id="prod-1",
            category="Meat",
            store_name="REMA",
        )
        shopping_list.add_item(item)

        assert shopping_list.total_cost == 40.0
        assert shopping_list.total_savings == 10.0
        assert shopping_list.matched_items_count == 1
        assert len(shopping_list.items) == 1

    def test_add_item_groups_by_category(self):
        """Test that add_item groups items by category."""
        shopping_list = ShoppingList(meal_plan_id="plan-1")

        item1 = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            category="Meat",
        )
        item2 = ShoppingItem(
            ingredient_name="onion",
            normalized_name="onion",
            quantity="2",
            unit="",
            category="Vegetables",
        )
        item3 = ShoppingItem(
            ingredient_name="beef",
            normalized_name="beef",
            quantity="400",
            unit="g",
            category="Meat",
        )

        shopping_list.add_item(item1)
        shopping_list.add_item(item2)
        shopping_list.add_item(item3)

        assert len(shopping_list.items_by_category["Meat"]) == 2
        assert len(shopping_list.items_by_category["Vegetables"]) == 1

    def test_unmatched_items_count(self):
        """Test unmatched items count."""
        shopping_list = ShoppingList(meal_plan_id="plan-1")

        matched_item = ShoppingItem(
            ingredient_name="chicken",
            normalized_name="chicken",
            quantity="500",
            unit="g",
            product_id="prod-1",
        )
        unmatched_item = ShoppingItem(
            ingredient_name="exotic spice",
            normalized_name="exotic spice",
            quantity="1",
            unit="tsp",
        )

        shopping_list.add_item(matched_item)
        shopping_list.add_item(unmatched_item)

        assert shopping_list.matched_items_count == 1
        assert shopping_list.unmatched_items_count == 1


class TestShoppingListGenerator:
    """Tests for ShoppingListGenerator class."""

    @pytest.fixture
    def mock_graph_service(self):
        """Create a mock GraphService."""
        service = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_generate_basic(self, mock_graph_service):
        """Test basic shopping list generation."""
        mock_graph_service.get_products_for_ingredient.return_value = []

        generator = ShoppingListGenerator(mock_graph_service)

        recipes_ingredients = [
            ("recipe-1", [{"name": "chicken", "quantity": "500", "measure": "g"}]),
            ("recipe-2", [{"name": "onion", "quantity": "2", "measure": ""}]),
        ]

        result = await generator.generate(
            meal_plan_id="plan-1",
            recipes_ingredients=recipes_ingredients,
            people_count=2,
        )

        assert result.meal_plan_id == "plan-1"
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_generate_aggregates_same_ingredient(self, mock_graph_service):
        """Test that generator aggregates same ingredient from multiple recipes."""
        mock_graph_service.get_products_for_ingredient.return_value = []

        generator = ShoppingListGenerator(mock_graph_service)

        recipes_ingredients = [
            ("recipe-1", [{"name": "onion", "quantity": "1", "measure": ""}]),
            ("recipe-2", [{"name": "onion", "quantity": "2", "measure": ""}]),
        ]

        result = await generator.generate(
            meal_plan_id="plan-1",
            recipes_ingredients=recipes_ingredients,
            people_count=2,
        )

        # Should have only one onion entry with aggregated quantity
        assert len(result.items) == 1
        # Base 3 onions * 1.0 scale factor (people_count/2)
        assert result.items[0].quantity == "3"

    @pytest.mark.asyncio
    async def test_generate_scales_for_people(self, mock_graph_service):
        """Test that generator scales quantities for people count."""
        mock_graph_service.get_products_for_ingredient.return_value = []

        generator = ShoppingListGenerator(mock_graph_service)

        recipes_ingredients = [
            ("recipe-1", [{"name": "chicken", "quantity": "500", "measure": "g"}]),
        ]

        result = await generator.generate(
            meal_plan_id="plan-1",
            recipes_ingredients=recipes_ingredients,
            people_count=4,  # Double the default
        )

        # 500g * 2.0 scale = 1000g = 1kg
        assert result.items[0].quantity == "1"
        assert result.items[0].unit == "kg"

    @pytest.mark.asyncio
    async def test_generate_with_product_match(self, mock_graph_service):
        """Test that generator includes product matches."""
        mock_graph_service.get_products_for_ingredient.return_value = [
            {
                "p": {
                    "id": "prod-1",
                    "name": "Chicken Breast 500g",
                    "brand": "Brand",
                    "price": 50.0,
                    "discount_price": 40.0,
                    "has_active_discount": True,
                    "category": "Meat",
                },
                "confidence": 0.9,
                "store_id": "store-1",
                "store_name": "REMA",
            }
        ]

        generator = ShoppingListGenerator(mock_graph_service)

        recipes_ingredients = [
            ("recipe-1", [{"name": "chicken", "quantity": "500", "measure": "g"}]),
        ]

        result = await generator.generate(
            meal_plan_id="plan-1",
            recipes_ingredients=recipes_ingredients,
            people_count=2,
        )

        assert result.items[0].product_id == "prod-1"
        assert result.items[0].price == 50.0
        assert result.items[0].discount_price == 40.0
        assert result.matched_items_count == 1

    @pytest.mark.asyncio
    async def test_select_best_product_prefers_discount(self, mock_graph_service):
        """Test that _select_best_product prefers discounted items."""
        generator = ShoppingListGenerator(mock_graph_service)

        products = [
            {
                "p": {
                    "id": "prod-1",
                    "price": 40.0,
                    "has_active_discount": False,
                },
                "confidence": 0.9,
                "store_id": "store-1",
            },
            {
                "p": {
                    "id": "prod-2",
                    "price": 50.0,
                    "discount_price": 35.0,
                    "has_active_discount": True,
                },
                "confidence": 0.85,
                "store_id": "store-1",
            },
        ]

        best = generator._select_best_product(products, None)

        assert best["p"]["id"] == "prod-2"  # Discounted one

    @pytest.mark.asyncio
    async def test_select_best_product_prefers_store(self, mock_graph_service):
        """Test that _select_best_product prefers specified stores."""
        generator = ShoppingListGenerator(mock_graph_service)

        products = [
            {
                "p": {
                    "id": "prod-1",
                    "price": 40.0,
                    "has_active_discount": False,
                },
                "confidence": 0.9,
                "store_id": "store-1",
            },
            {
                "p": {
                    "id": "prod-2",
                    "price": 45.0,
                    "has_active_discount": False,
                },
                "confidence": 0.9,
                "store_id": "preferred-store",
            },
        ]

        best = generator._select_best_product(products, ["preferred-store"])

        assert best["p"]["id"] == "prod-2"  # From preferred store
