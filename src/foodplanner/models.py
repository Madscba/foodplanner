"""SQLAlchemy database models."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from foodplanner.database import Base


class Store(Base):
    """Physical store location."""

    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str] = mapped_column(String, nullable=False)  # "netto", "rema1000"
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    products: Mapped[list["Product"]] = relationship("Product", back_populates="store")
    discounts: Mapped[list["Discount"]] = relationship("Discount", back_populates="store")
    user_preferences: Mapped[list["UserStorePreference"]] = relationship(
        "UserStorePreference", back_populates="store"
    )
    ingestion_statuses: Mapped[list["StoreIngestionStatus"]] = relationship(
        "StoreIngestionStatus", back_populates="store"
    )

    __table_args__ = (
        Index("idx_stores_zip_code", "zip_code"),
        Index("idx_stores_brand", "brand"),
        Index("idx_stores_is_active", "is_active"),
    )


class Product(Base):
    """Product available at a store."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    ean: Mapped[str | None] = mapped_column(String, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str | None] = mapped_column(String, nullable=True)
    nutrition: Mapped[dict] = mapped_column(JSON, default=dict)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    store: Mapped["Store"] = relationship("Store", back_populates="products")
    discounts: Mapped[list["Discount"]] = relationship("Discount", back_populates="product")


class Discount(Base):
    """Temporary discount on a product."""

    __tablename__ = "discounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("products.id"))
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"))
    discount_price: Mapped[float] = mapped_column(Float, nullable=False)
    discount_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship("Product", back_populates="discounts")
    store: Mapped["Store"] = relationship("Store", back_populates="discounts")


class User(Base):
    """User account."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    preferences: Mapped[list["UserPreference"]] = relationship(
        "UserPreference", back_populates="user"
    )
    meal_plans: Mapped[list["MealPlan"]] = relationship("MealPlan", back_populates="user")
    store_preferences: Mapped[list["UserStorePreference"]] = relationship(
        "UserStorePreference", back_populates="user"
    )


class UserPreference(Base):
    """User dietary preferences and constraints."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # allergy, preference, restriction
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="preferences")


class Recipe(Base):
    """Recipe with ingredients and instructions."""

    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    servings: Mapped[int] = mapped_column(Integer, nullable=False)
    ingredients: Mapped[list] = mapped_column(JSON, default=list)
    instructions: Mapped[list] = mapped_column(JSON, default=list)
    nutrition_per_serving: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meal_plan_recipes: Mapped[list["MealPlanRecipe"]] = relationship(
        "MealPlanRecipe", back_populates="recipe"
    )


class MealPlan(Base):
    """Generated meal plan for a user."""

    __tablename__ = "meal_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    plan_metadata: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # Renamed from 'metadata' (reserved)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="meal_plans")
    recipes: Mapped[list["MealPlanRecipe"]] = relationship("MealPlanRecipe", back_populates="plan")


class MealPlanRecipe(Base):
    """Join table for meal plans and recipes."""

    __tablename__ = "meal_plan_recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_plan_id: Mapped[str] = mapped_column(String, ForeignKey("meal_plans.id"))
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"))
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String, nullable=False)  # breakfast, lunch, dinner

    plan: Mapped["MealPlan"] = relationship("MealPlan", back_populates="recipes")
    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="meal_plan_recipes")


class IngestionRun(Base):
    """Track daily API ingestion runs."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False
    )  # pending, running, completed, failed
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Celery task ID
    trigger_type: Mapped[str] = mapped_column(
        String(50), default="scheduled"
    )  # scheduled, manual, retry
    stores_total: Mapped[int] = mapped_column(Integer, default=0)
    stores_completed: Mapped[int] = mapped_column(Integer, default=0)
    stores_failed: Mapped[int] = mapped_column(Integer, default=0)
    products_updated: Mapped[int] = mapped_column(Integer, default=0)
    discounts_updated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    store_statuses: Mapped[list["StoreIngestionStatus"]] = relationship(
        "StoreIngestionStatus", back_populates="run"
    )

    __table_args__ = (
        Index("idx_ingestion_runs_run_date", "run_date"),
        Index("idx_ingestion_runs_status", "status"),
        Index("idx_ingestion_runs_task_id", "task_id"),
    )


class UserStorePreference(Base):
    """User's preferred stores for meal planning."""

    __tablename__ = "user_store_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = more preferred
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="store_preferences")
    store: Mapped["Store"] = relationship("Store", back_populates="user_preferences")

    __table_args__ = (
        UniqueConstraint("user_id", "store_id", name="uq_user_store_preference"),
        Index("idx_user_store_prefs_user_id", "user_id"),
        Index("idx_user_store_prefs_store_id", "store_id"),
    )


class StoreIngestionStatus(Base):
    """Track per-store status within an ingestion run."""

    __tablename__ = "store_ingestion_statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("ingestion_runs.id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String, ForeignKey("stores.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pending, running, completed, failed, skipped
    products_fetched: Mapped[int] = mapped_column(Integer, default=0)
    discounts_fetched: Mapped[int] = mapped_column(Integer, default=0)
    products_inserted: Mapped[int] = mapped_column(Integer, default=0)
    discounts_inserted: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["IngestionRun"] = relationship("IngestionRun", back_populates="store_statuses")
    store: Mapped["Store"] = relationship("Store", back_populates="ingestion_statuses")

    __table_args__ = (
        UniqueConstraint("run_id", "store_id", name="uq_run_store_status"),
        Index("idx_store_ingestion_run_id", "run_id"),
        Index("idx_store_ingestion_store_id", "store_id"),
        Index("idx_store_ingestion_status", "status"),
    )


class RawIngestionData(Base):
    """Archive of raw API responses for replayability."""

    __tablename__ = "raw_ingestion_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("ingestion_runs.id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)  # API endpoint called
    request_params: Mapped[dict] = mapped_column(JSON, default=dict)  # Query parameters
    response_data: Mapped[dict] = mapped_column(JSON, nullable=False)  # Raw JSON response
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)  # HTTP status code
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_raw_data_run_id", "run_id"),
        Index("idx_raw_data_store_id", "store_id"),
        Index("idx_raw_data_fetched_at", "fetched_at"),
    )
