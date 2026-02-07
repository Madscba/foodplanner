"""Common data schemas for the pipeline."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DietaryPreference(BaseModel):
    """User dietary preference."""

    name: str
    type: Literal["allergy", "preference", "restriction"]


class MealPlanRequest(BaseModel):
    """Request to generate a meal plan."""

    user_id: str
    store_ids: list[str] = Field(description="Target store IDs")
    start_date: date
    end_date: date
    people_count: int = Field(ge=1, le=20)
    dietary_preferences: list[DietaryPreference] = Field(default_factory=list)
    budget_max: float | None = Field(None, description="Max budget in local currency")
    on_hand_ingredients: list[str] = Field(default_factory=list)
    preselected_recipe_ids: list[str] = Field(default_factory=list)


class Product(BaseModel):
    """Normalized product information."""

    id: str
    name: str
    brand: str | None = None
    price: float
    unit: str
    is_discounted: bool = False
    discount_price: float | None = None
    store_id: str
    nutrition: dict[str, float] = Field(default_factory=dict)


class Recipe(BaseModel):
    """Recipe with ingredients and instructions."""

    id: str
    name: str
    description: str | None = None
    servings: int
    ingredients: list[str]
    instructions: list[str]
    nutrition_per_serving: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class MealPlan(BaseModel):
    """Generated meal plan."""

    id: str
    user_id: str
    start_date: date
    end_date: date
    recipes: list[Recipe]
    shopping_list: list[Product]
    total_cost: float
    metadata: dict[str, any] = Field(default_factory=dict)
