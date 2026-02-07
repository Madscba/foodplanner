"""FastAPI application entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from foodplanner.database import Base, async_engine
from foodplanner.graph.database import close_graph_db, get_graph_db
from foodplanner.logging_config import configure_logging, get_logger
from foodplanner.routers import (
    ingestion_router,
    meal_plans_router,
    recipes_router,
    scraping_router,
    stores_router,
)

# Configure logging on module load
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler for startup and shutdown events."""
    # Startup
    logger.info("Starting Foodplanner API")

    # Create database tables if they don't exist
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")

    # Initialize Neo4j connection
    try:
        graph_db = await get_graph_db()
        await graph_db.setup_constraints()
        logger.info("Neo4j graph database initialized")
    except Exception as e:
        logger.warning(f"Neo4j initialization failed (may not be available): {e}")

    yield

    # Shutdown
    logger.info("Shutting down Foodplanner API")

    # Close Neo4j connection
    try:
        await close_graph_db()
        logger.info("Neo4j connection closed")
    except Exception as e:
        logger.warning(f"Error closing Neo4j connection: {e}")

    await async_engine.dispose()


app = FastAPI(
    title="Foodplanner API",
    description="Meal planning with local grocery discounts",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8000").split(
    ","
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(stores_router)
app.include_router(ingestion_router)
app.include_router(recipes_router)
app.include_router(scraping_router)
app.include_router(meal_plans_router)


@app.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok", "service": "foodplanner-api"}


@app.get("/")
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": "Foodplanner API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
