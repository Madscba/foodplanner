"""API routers for the foodplanner application."""

from foodplanner.routers.ingestion import router as ingestion_router
from foodplanner.routers.meal_plans import router as meal_plans_router
from foodplanner.routers.recipes import router as recipes_router
from foodplanner.routers.scraping import router as scraping_router
from foodplanner.routers.stores import router as stores_router

__all__ = [
    "ingestion_router",
    "meal_plans_router",
    "recipes_router",
    "scraping_router",
    "stores_router",
]
