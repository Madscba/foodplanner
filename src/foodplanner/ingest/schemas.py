"""Pydantic schemas for validating scraped product data."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ScrapedProduct(BaseModel):
    """Product information scraped from grocery store website."""

    id: str | None = None
    name: str = Field(default="Unknown Product")
    price: float = Field(ge=0, default=0.0)
    unit: str | None = None
    ean: str | None = None
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    image_url: str | None = None
    description: str | None = None
    ingredients: str | None = None
    nutrition_info: dict[str, Any] | None = None
    origin: str | None = None
    store_id: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def default_name(cls, v: Any) -> str:
        """Ensure name is never None or empty."""
        if not v:
            return "Unknown Product"
        return str(v).strip()

    @field_validator("price", mode="before")
    @classmethod
    def coerce_price(cls, v: Any) -> float:
        """Handle price conversions."""
        if v is None:
            return 0.0
        if isinstance(v, str):
            # Handle Danish number format (comma as decimal)
            v = v.replace(",", ".").replace("kr", "").replace(",-", "").strip()
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("ean", mode="before")
    @classmethod
    def coerce_ean(cls, v: Any) -> str | None:
        """Convert EAN to string and handle missing values."""
        if v is None or v == "":
            return None
        return str(v).strip()

    @property
    def product_id(self) -> str:
        """Get the best available product identifier."""
        return self.id or self.ean or f"product-{hash(self.name)}"


class ScrapedDiscount(BaseModel):
    """Discount/offer information scraped from grocery store website."""

    product_id: str
    store_id: str
    original_price: float = Field(ge=0)
    discount_price: float = Field(ge=0)
    discount_percentage: float | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    description: str | None = None

    @field_validator("original_price", "discount_price", mode="before")
    @classmethod
    def coerce_price(cls, v: Any) -> float:
        """Handle price conversions."""
        if v is None:
            return 0.0
        if isinstance(v, str):
            v = v.replace(",", ".").replace("kr", "").replace(",-", "").strip()
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    @property
    def calculated_discount_percentage(self) -> float:
        """Calculate discount percentage if not provided."""
        if self.discount_percentage is not None:
            return self.discount_percentage
        if self.original_price <= 0:
            return 0.0
        return ((self.original_price - self.discount_price) / self.original_price) * 100


class StoreInfo(BaseModel):
    """Store information."""

    id: str
    name: str
    brand: str
    address: str | None = None
    city: str | None = None
    zip_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("brand", mode="before")
    @classmethod
    def normalize_brand(cls, v: Any) -> str:
        """Normalize brand names."""
        if not v:
            return "unknown"
        brand = str(v).lower().strip()
        # Map common variations
        brand_map = {
            "rema": "rema1000",
            "rema1000": "rema1000",
            "rema 1000": "rema1000",
            "netto": "netto",
            "føtex": "foetex",
            "fotex": "foetex",
            "foetex": "foetex",
            "bilka": "bilka",
            "coop": "coop",
            "irma": "irma",
            "fakta": "fakta",
            "lidl": "lidl",
            "aldi": "aldi",
        }
        return brand_map.get(brand, brand)


# Request schemas for internal use
class IngestionRequest(BaseModel):
    """Request to trigger ingestion."""

    store_ids: list[str] | None = None
    force: bool = False  # Force re-ingestion even if already run today


class StoreDiscoveryRequest(BaseModel):
    """Request to discover stores."""

    zip_code: str | None = None
    city: str | None = None
    brand: str | None = None
    radius_km: float = Field(default=10.0, ge=1.0, le=100.0)
    limit: int = Field(default=50, ge=1, le=200)


# Response schemas for API
class IngestionRunSummary(BaseModel):
    """Summary of an ingestion run."""

    id: int
    run_date: date
    status: str
    trigger_type: str
    stores_total: int
    stores_completed: int
    stores_failed: int
    products_updated: int
    discounts_updated: int
    started_at: datetime
    completed_at: datetime | None

    class Config:
        from_attributes = True


class StoreIngestionStatusSummary(BaseModel):
    """Summary of a single store's ingestion status."""

    id: int
    store_id: str
    status: str
    products_fetched: int
    discounts_fetched: int
    error_message: str | None
    retry_count: int
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


class IngestionRunDetail(IngestionRunSummary):
    """Detailed view of an ingestion run including per-store status."""

    store_statuses: list[StoreIngestionStatusSummary] = Field(default_factory=list)
