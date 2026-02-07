"""Unit normalization and conversion utilities."""

import re
from dataclasses import dataclass
from typing import Any

from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Unit Conversion Tables
# =============================================================================

# Volume conversions (base unit: ml)
VOLUME_UNITS: dict[str, float] = {
    # Metric
    "ml": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
    "millilitre": 1.0,
    "millilitres": 1.0,
    "l": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
    "dl": 100.0,
    "deciliter": 100.0,
    "deciliters": 100.0,
    "cl": 10.0,
    "centiliter": 10.0,
    "centiliters": 10.0,
    # US customary
    "cup": 236.588,
    "cups": 236.588,
    "tbsp": 14.787,
    "tablespoon": 14.787,
    "tablespoons": 14.787,
    "tbs": 14.787,
    "tsp": 4.929,
    "teaspoon": 4.929,
    "teaspoons": 4.929,
    "fl oz": 29.574,
    "fluid ounce": 29.574,
    "fluid ounces": 29.574,
    "pint": 473.176,
    "pints": 473.176,
    "pt": 473.176,
    "quart": 946.353,
    "quarts": 946.353,
    "qt": 946.353,
    "gallon": 3785.41,
    "gallons": 3785.41,
    "gal": 3785.41,
}

# Weight conversions (base unit: g)
WEIGHT_UNITS: dict[str, float] = {
    # Metric
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
    # Imperial
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
}

# Count-based units (no conversion needed, base unit: count)
COUNT_UNITS: dict[str, float] = {
    "piece": 1.0,
    "pieces": 1.0,
    "pc": 1.0,
    "pcs": 1.0,
    "whole": 1.0,
    "slice": 1.0,
    "slices": 1.0,
    "clove": 1.0,
    "cloves": 1.0,
    "head": 1.0,
    "heads": 1.0,
    "bunch": 1.0,
    "bunches": 1.0,
    "sprig": 1.0,
    "sprigs": 1.0,
    "can": 1.0,
    "cans": 1.0,
    "jar": 1.0,
    "jars": 1.0,
    "package": 1.0,
    "packages": 1.0,
    "pkg": 1.0,
    "pack": 1.0,
    "packs": 1.0,
    "bottle": 1.0,
    "bottles": 1.0,
    "bag": 1.0,
    "bags": 1.0,
    "box": 1.0,
    "boxes": 1.0,
    "stick": 1.0,
    "sticks": 1.0,
    "fillet": 1.0,
    "fillets": 1.0,
    "breast": 1.0,
    "breasts": 1.0,
    "thigh": 1.0,
    "thighs": 1.0,
    "leg": 1.0,
    "legs": 1.0,
    "wing": 1.0,
    "wings": 1.0,
}

# Approximate size descriptors (convert to count)
SIZE_DESCRIPTORS: dict[str, float] = {
    "small": 0.75,
    "medium": 1.0,
    "large": 1.5,
    "extra large": 2.0,
    "xl": 2.0,
}


@dataclass
class NormalizedQuantity:
    """Represents a normalized quantity with unit type."""

    value: float
    unit: str
    unit_type: str  # "volume", "weight", "count", "unknown"
    original_quantity: str
    original_unit: str

    def __add__(self, other: "NormalizedQuantity") -> "NormalizedQuantity":
        """Add two normalized quantities if compatible."""
        if self.unit_type != other.unit_type:
            # Can't add different unit types, return self
            logger.warning(f"Cannot add {self.unit_type} and {other.unit_type}, keeping first")
            return self

        return NormalizedQuantity(
            value=self.value + other.value,
            unit=self.unit,
            unit_type=self.unit_type,
            original_quantity=f"{self.original_quantity} + {other.original_quantity}",
            original_unit=self.unit,
        )

    def to_display_string(self) -> tuple[str, str]:
        """Convert back to human-readable format."""
        if self.unit_type == "volume":
            return self._format_volume()
        elif self.unit_type == "weight":
            return self._format_weight()
        elif self.unit_type == "count":
            return self._format_count()
        else:
            return str(self.value), self.original_unit

    def _format_volume(self) -> tuple[str, str]:
        """Format volume for display."""
        if self.value >= 1000:
            return f"{self.value / 1000:.1f}".rstrip("0").rstrip("."), "L"
        elif self.value >= 100:
            return f"{self.value / 100:.1f}".rstrip("0").rstrip("."), "dl"
        else:
            return f"{self.value:.0f}", "ml"

    def _format_weight(self) -> tuple[str, str]:
        """Format weight for display."""
        if self.value >= 1000:
            return f"{self.value / 1000:.2f}".rstrip("0").rstrip("."), "kg"
        else:
            return f"{self.value:.0f}", "g"

    def _format_count(self) -> tuple[str, str]:
        """Format count for display."""
        if self.value == int(self.value):
            return str(int(self.value)), self.original_unit or ""
        else:
            return f"{self.value:.1f}", self.original_unit or ""


# =============================================================================
# Parsing Functions
# =============================================================================


def parse_quantity_string(quantity_str: str) -> float:
    """
    Parse a quantity string into a float.

    Handles formats like:
    - "2"
    - "1.5"
    - "1/2"
    - "1 1/2" (one and a half)
    - "2-3" (range, returns average)
    """
    if not quantity_str:
        return 1.0

    quantity_str = quantity_str.strip().lower()

    # Handle empty or "to taste" style
    if not quantity_str or quantity_str in ("to taste", "pinch", "dash", "some"):
        return 1.0

    # Handle ranges like "2-3" -> return average
    range_match = re.match(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", quantity_str)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        return (low + high) / 2

    # Handle mixed fractions like "1 1/2"
    mixed_match = re.match(r"(\d+)\s+(\d+)/(\d+)", quantity_str)
    if mixed_match:
        whole = int(mixed_match.group(1))
        num = int(mixed_match.group(2))
        denom = int(mixed_match.group(3))
        return whole + (num / denom)

    # Handle simple fractions like "1/2"
    frac_match = re.match(r"(\d+)/(\d+)", quantity_str)
    if frac_match:
        num = int(frac_match.group(1))
        denom = int(frac_match.group(2))
        return num / denom

    # Handle simple numbers
    num_match = re.match(r"(\d+(?:\.\d+)?)", quantity_str)
    if num_match:
        return float(num_match.group(1))

    return 1.0


def identify_unit_type(unit: str) -> tuple[str, float]:
    """
    Identify the unit type and conversion factor.

    Returns:
        Tuple of (unit_type, conversion_factor)
    """
    unit_lower = unit.lower().strip()

    if unit_lower in VOLUME_UNITS:
        return "volume", VOLUME_UNITS[unit_lower]

    if unit_lower in WEIGHT_UNITS:
        return "weight", WEIGHT_UNITS[unit_lower]

    if unit_lower in COUNT_UNITS:
        return "count", COUNT_UNITS[unit_lower]

    # Check for size descriptors
    for size, factor in SIZE_DESCRIPTORS.items():
        if size in unit_lower:
            return "count", factor

    return "unknown", 1.0


def normalize_quantity(
    quantity: str | float | None,
    unit: str | None,
) -> NormalizedQuantity:
    """
    Normalize a quantity and unit to base units.

    Args:
        quantity: The quantity value (string or float).
        unit: The unit string.

    Returns:
        NormalizedQuantity with value in base units.
    """
    # Parse quantity
    if quantity is None:
        qty_value = 1.0
    elif isinstance(quantity, (int, float)):
        qty_value = float(quantity)
    else:
        qty_value = parse_quantity_string(str(quantity))

    # Handle no unit
    if not unit:
        return NormalizedQuantity(
            value=qty_value,
            unit="",
            unit_type="count",
            original_quantity=str(quantity or "1"),
            original_unit="",
        )

    # Identify unit type and convert
    unit_type, factor = identify_unit_type(unit)

    # Calculate base value
    base_value = qty_value * factor

    # Determine base unit name
    if unit_type == "volume":
        base_unit = "ml"
    elif unit_type == "weight":
        base_unit = "g"
    elif unit_type == "count":
        base_unit = unit.lower().strip()
    else:
        base_unit = unit

    return NormalizedQuantity(
        value=base_value,
        unit=base_unit,
        unit_type=unit_type,
        original_quantity=str(quantity or "1"),
        original_unit=unit,
    )


def can_aggregate(unit1: str | None, unit2: str | None) -> bool:
    """
    Check if two units can be aggregated together.

    Returns True if both units are of the same type (volume, weight, or count).
    """
    type1, _ = identify_unit_type(unit1 or "")
    type2, _ = identify_unit_type(unit2 or "")

    # Unknown types can't be aggregated
    if type1 == "unknown" or type2 == "unknown":
        return type1 == type2

    return type1 == type2


def extract_quantity_and_unit(measure: str) -> tuple[str, str]:
    """
    Extract quantity and unit from a combined measure string.

    Examples:
        "2 cups" -> ("2", "cups")
        "500g" -> ("500", "g")
        "1/2 tsp" -> ("1/2", "tsp")
    """
    if not measure:
        return "1", ""

    measure = measure.strip()

    # Pattern: number(s) followed by unit
    match = re.match(
        r"^(\d+(?:\.\d+)?(?:\s*/\s*\d+)?(?:\s+\d+/\d+)?)\s*(.*)$",
        measure,
    )

    if match:
        qty = match.group(1).strip()
        unit = match.group(2).strip()
        return qty, unit

    # Check if it's just a unit (implied quantity of 1)
    if measure.lower() in VOLUME_UNITS or measure.lower() in WEIGHT_UNITS:
        return "1", measure

    # Check if it's just a number
    if re.match(r"^\d+(?:\.\d+)?$", measure):
        return measure, ""

    # Default: treat as unit with quantity 1
    return "1", measure


# =============================================================================
# Ingredient Aggregation
# =============================================================================


@dataclass
class AggregatedIngredient:
    """An ingredient with aggregated quantities from multiple recipes."""

    name: str
    normalized_name: str
    total_quantity: NormalizedQuantity
    recipe_sources: list[str]  # Recipe IDs that use this ingredient

    def display_quantity(self) -> str:
        """Get human-readable quantity string."""
        qty, unit = self.total_quantity.to_display_string()
        if unit:
            return f"{qty} {unit}"
        return qty


def normalize_ingredient_name(name: str) -> str:
    """
    Normalize an ingredient name for matching.

    - Lowercase
    - Remove extra whitespace
    - Remove common descriptors (fresh, dried, chopped, etc.)
    """
    if not name:
        return ""

    name = name.lower().strip()

    # Remove common preparation descriptors
    descriptors = [
        "fresh",
        "dried",
        "frozen",
        "canned",
        "chopped",
        "diced",
        "minced",
        "sliced",
        "grated",
        "shredded",
        "crushed",
        "ground",
        "whole",
        "halved",
        "quartered",
        "peeled",
        "seeded",
        "pitted",
        "boneless",
        "skinless",
        "cooked",
        "raw",
        "organic",
        "free-range",
        "free range",
    ]

    for desc in descriptors:
        name = re.sub(rf"\b{desc}\b", "", name)

    # Remove extra whitespace
    name = " ".join(name.split())

    return name


def aggregate_ingredients(
    ingredients: list[dict[str, Any]],
    recipe_id: str = "",
) -> dict[str, AggregatedIngredient]:
    """
    Aggregate a list of ingredients, combining same ingredients.

    Args:
        ingredients: List of ingredient dicts with 'name', 'quantity', 'measure'.
        recipe_id: Optional recipe ID for tracking sources.

    Returns:
        Dict mapping normalized names to AggregatedIngredient.
    """
    aggregated: dict[str, AggregatedIngredient] = {}

    for ing in ingredients:
        # Extract ingredient info
        if isinstance(ing, str):
            name = ing
            quantity = "1"
            measure = ""
        else:
            name = ing.get("name", "")
            quantity = ing.get("quantity", "1")
            measure = ing.get("measure", "")

        if not name:
            continue

        # Normalize name
        normalized = normalize_ingredient_name(name)

        # Extract quantity from measure if needed
        if measure and not quantity:
            quantity, measure = extract_quantity_and_unit(measure)

        # Normalize quantity
        norm_qty = normalize_quantity(quantity, measure)

        if normalized in aggregated:
            # Add to existing
            existing = aggregated[normalized]
            existing.total_quantity = existing.total_quantity + norm_qty
            if recipe_id and recipe_id not in existing.recipe_sources:
                existing.recipe_sources.append(recipe_id)
        else:
            # Create new
            aggregated[normalized] = AggregatedIngredient(
                name=name,
                normalized_name=normalized,
                total_quantity=norm_qty,
                recipe_sources=[recipe_id] if recipe_id else [],
            )

    return aggregated
