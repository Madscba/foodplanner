"""Pydantic models for graph nodes and relationships."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BaseNode(BaseModel):
    """Base class for all graph nodes."""

    class Config:
        from_attributes = True


class RecipeNode(BaseNode):
    """Recipe node in the knowledge graph."""

    id: str
    name: str
    instructions: str = ""
    thumbnail: str | None = None
    source_url: str | None = None
    youtube_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "id": self.id,
            "name": self.name,
            "instructions": self.instructions,
            "thumbnail": self.thumbnail,
            "source_url": self.source_url,
            "youtube_url": self.youtube_url,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class IngredientNode(BaseNode):
    """Ingredient node in the knowledge graph."""

    name: str
    normalized_name: str = ""
    description: str | None = None
    image_url: str | None = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        if not self.normalized_name:
            self.normalized_name = self.name.lower().strip()

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "name": self.name,
            "normalized_name": self.normalized_name,
            "description": self.description,
            "image_url": self.image_url,
        }


class ProductNode(BaseNode):
    """Product node synced from PostgreSQL."""

    id: str
    name: str
    brand: str | None = None
    category: str | None = None
    price: float
    unit: str
    ean: str | None = None
    discount_price: float | None = None
    discount_percentage: float | None = None
    has_active_discount: bool = False

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "category": self.category,
            "price": self.price,
            "unit": self.unit,
            "ean": self.ean,
            "discount_price": self.discount_price,
            "discount_percentage": self.discount_percentage,
            "has_active_discount": self.has_active_discount,
        }


class CategoryNode(BaseNode):
    """Recipe category node."""

    name: str
    description: str | None = None
    thumbnail: str | None = None

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "name": self.name,
            "description": self.description,
            "thumbnail": self.thumbnail,
        }


class AreaNode(BaseNode):
    """Cuisine area/region node."""

    name: str

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {"name": self.name}


class StoreNode(BaseNode):
    """Store node synced from PostgreSQL."""

    id: str
    name: str
    brand: str
    city: str | None = None
    zip_code: str | None = None

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j node properties."""
        return {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "city": self.city,
            "zip_code": self.zip_code,
        }


# Relationship models


class ContainsRelationship(BaseModel):
    """CONTAINS relationship between Recipe and Ingredient."""

    quantity: str = ""
    measure: str = ""

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j relationship properties."""
        return {
            "quantity": self.quantity,
            "measure": self.measure,
        }


class MatchesRelationship(BaseModel):
    """MATCHES relationship between Ingredient and Product."""

    confidence_score: float = Field(ge=0.0, le=1.0)
    match_type: str = "fuzzy"  # exact, fuzzy, semantic
    matched_at: datetime = Field(default_factory=datetime.utcnow)

    def to_neo4j_properties(self) -> dict[str, Any]:
        """Convert to Neo4j relationship properties."""
        return {
            "confidence_score": self.confidence_score,
            "match_type": self.match_type,
            "matched_at": self.matched_at.isoformat(),
        }


# Response models for API


class RecipeWithIngredients(BaseModel):
    """Recipe with its ingredients for API responses."""

    id: str
    name: str
    instructions: str
    thumbnail: str | None
    source_url: str | None
    youtube_url: str | None
    tags: list[str]
    category: str | None = None
    area: str | None = None
    ingredients: list[dict[str, Any]] = Field(default_factory=list)


class IngredientWithProducts(BaseModel):
    """Ingredient with matched products for API responses."""

    name: str
    normalized_name: str
    products: list[dict[str, Any]] = Field(default_factory=list)


class RecipeSearchResult(BaseModel):
    """Recipe search result with relevance info."""

    recipe: RecipeWithIngredients
    matched_ingredients: int = 0
    discounted_ingredients: int = 0
    total_ingredients: int = 0
    estimated_cost: float | None = None
    estimated_savings: float | None = None
