"""Celery tasks for background job processing."""

from foodplanner.tasks.graph_ingestion import (
    compute_ingredient_matches_task,
    full_graph_refresh_task,
    graph_health_check_task,
    ingest_mealdb_recipes_task,
    sync_products_to_graph_task,
)
from foodplanner.tasks.ingestion import run_daily_ingestion_task

__all__ = [
    "compute_ingredient_matches_task",
    "full_graph_refresh_task",
    "graph_health_check_task",
    "ingest_mealdb_recipes_task",
    "run_daily_ingestion_task",
    "sync_products_to_graph_task",
]
