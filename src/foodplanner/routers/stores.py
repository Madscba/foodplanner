"""API routes for store discovery and user store preferences."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from foodplanner.database import get_db
from foodplanner.logging_config import get_logger
from foodplanner.models import Store, User, UserStorePreference

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/stores", tags=["stores"])


# Request/Response schemas
class StoreResponse(BaseModel):
    """Store information response."""

    id: str
    name: str
    brand: str
    address: str | None = None
    city: str | None = None
    zip_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_active: bool = True

    class Config:
        from_attributes = True


class StoreDiscoveryResponse(BaseModel):
    """Response from store discovery endpoint."""

    stores: list[StoreResponse]
    total: int
    source: str  # "api" or "database"


class UserStorePreferenceRequest(BaseModel):
    """Request to add a store preference."""

    store_id: str
    priority: int = Field(default=0, ge=0, le=100)


class UserStorePreferenceResponse(BaseModel):
    """User store preference response."""

    id: int
    store_id: str
    store_name: str | None = None
    store_brand: str | None = None
    priority: int
    is_active: bool

    class Config:
        from_attributes = True


class UserStorePreferencesResponse(BaseModel):
    """List of user store preferences."""

    preferences: list[UserStorePreferenceResponse]
    total: int


# Dependency to get current user (placeholder - implement proper auth later)
async def get_current_user_id() -> str:
    """Get current user ID - placeholder for auth implementation."""
    # TODO: Implement proper authentication
    return "default-user"


@router.get("/discover", response_model=StoreDiscoveryResponse)
async def discover_stores(
    zip_code: Annotated[str | None, Query(description="Filter by zip code")] = None,
    brand: Annotated[str | None, Query(description="Filter by brand (rema1000, etc.)")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum stores to return")] = 50,
    db: AsyncSession = Depends(get_db),
) -> StoreDiscoveryResponse:
    """
    Discover available stores from the database.

    This endpoint allows users to find stores by zip code or brand.
    Stores are populated via the web scraping pipeline.
    """
    logger.info(f"Store discovery: zip={zip_code}, brand={brand}, limit={limit}")

    query = select(Store).where(Store.is_active == True)  # noqa: E712

    if zip_code:
        query = query.where(Store.zip_code == zip_code)
    if brand:
        query = query.where(Store.brand == brand.lower())

    query = query.limit(limit)
    result = await db.execute(query)
    stores = result.scalars().all()

    logger.info(f"Found {len(stores)} stores")
    return StoreDiscoveryResponse(
        stores=[StoreResponse.model_validate(s) for s in stores],
        total=len(stores),
        source="database",
    )


@router.get("/{store_id}", response_model=StoreResponse)
async def get_store(
    store_id: str,
    db: AsyncSession = Depends(get_db),
) -> StoreResponse:
    """Get details for a specific store."""
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store {store_id} not found",
        )

    return StoreResponse.model_validate(store)


@router.get("/users/{user_id}/preferences", response_model=UserStorePreferencesResponse)
async def get_user_store_preferences(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
) -> UserStorePreferencesResponse:
    """Get a user's store preferences."""
    # TODO: Add proper authorization check
    if user_id != current_user and current_user != "default-user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access other user's preferences",
        )

    result = await db.execute(
        select(UserStorePreference)
        .options(selectinload(UserStorePreference.store))
        .where(UserStorePreference.user_id == user_id)
        .order_by(UserStorePreference.priority.desc())
    )
    preferences = result.scalars().all()

    return UserStorePreferencesResponse(
        preferences=[
            UserStorePreferenceResponse(
                id=p.id,
                store_id=p.store_id,
                store_name=p.store.name if p.store else None,
                store_brand=p.store.brand if p.store else None,
                priority=p.priority,
                is_active=p.is_active,
            )
            for p in preferences
        ],
        total=len(preferences),
    )


@router.post("/users/{user_id}/preferences", response_model=UserStorePreferenceResponse)
async def add_user_store_preference(
    user_id: str,
    request: UserStorePreferenceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
) -> UserStorePreferenceResponse:
    """Add a store to user's preferences."""
    # TODO: Add proper authorization check
    if user_id != current_user and current_user != "default-user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify other user's preferences",
        )

    # Verify store exists
    result = await db.execute(select(Store).where(Store.id == request.store_id))
    store = result.scalar_one_or_none()

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store {request.store_id} not found",
        )

    # Check if preference already exists
    existing = await db.execute(
        select(UserStorePreference).where(
            UserStorePreference.user_id == user_id,
            UserStorePreference.store_id == request.store_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Store already in user preferences",
        )

    # Ensure user exists (create placeholder if not)
    user_result = await db.execute(select(User).where(User.id == user_id))
    if not user_result.scalar_one_or_none():
        import secrets

        # Create placeholder user - in production, this would come from auth
        user = User(
            id=user_id,
            email=f"{user_id}@placeholder.local",
            hashed_password=secrets.token_hex(32),  # random unusable hash
        )
        db.add(user)

    preference = UserStorePreference(
        user_id=user_id,
        store_id=request.store_id,
        priority=request.priority,
        is_active=True,
    )
    db.add(preference)
    await db.commit()
    await db.refresh(preference)

    logger.info(f"Added store {request.store_id} to user {user_id} preferences")

    return UserStorePreferenceResponse(
        id=preference.id,
        store_id=preference.store_id,
        store_name=store.name,
        store_brand=store.brand,
        priority=preference.priority,
        is_active=preference.is_active,
    )


@router.delete("/users/{user_id}/preferences/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_store_preference(
    user_id: str,
    store_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
) -> None:
    """Remove a store from user's preferences."""
    # TODO: Add proper authorization check
    if user_id != current_user and current_user != "default-user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify other user's preferences",
        )

    result = await db.execute(
        select(UserStorePreference).where(
            UserStorePreference.user_id == user_id,
            UserStorePreference.store_id == store_id,
        )
    )
    preference = result.scalar_one_or_none()

    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store preference not found",
        )

    await db.delete(preference)
    await db.commit()

    logger.info(f"Removed store {store_id} from user {user_id} preferences")


@router.patch("/users/{user_id}/preferences/{store_id}", response_model=UserStorePreferenceResponse)
async def update_user_store_preference(
    user_id: str,
    store_id: str,
    priority: Annotated[int, Query(ge=0, le=100)],
    db: AsyncSession = Depends(get_db),
    current_user: str = Depends(get_current_user_id),
) -> UserStorePreferenceResponse:
    """Update priority of a store preference."""
    # TODO: Add proper authorization check
    if user_id != current_user and current_user != "default-user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify other user's preferences",
        )

    result = await db.execute(
        select(UserStorePreference)
        .options(selectinload(UserStorePreference.store))
        .where(
            UserStorePreference.user_id == user_id,
            UserStorePreference.store_id == store_id,
        )
    )
    preference = result.scalar_one_or_none()

    if not preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store preference not found",
        )

    preference.priority = priority
    await db.commit()
    await db.refresh(preference)

    return UserStorePreferenceResponse(
        id=preference.id,
        store_id=preference.store_id,
        store_name=preference.store.name if preference.store else None,
        store_brand=preference.store.brand if preference.store else None,
        priority=preference.priority,
        is_active=preference.is_active,
    )
