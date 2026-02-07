"""Celery application configuration for background task processing."""

import os

from celery import Celery
from celery.schedules import crontab

# Redis broker URL from environment or default
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Database URL for result backend (use sync driver)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/foodplanner")
# Convert async URL to sync for Celery result backend
RESULT_BACKEND_URL = DATABASE_URL.replace("+asyncpg", "").replace(
    "postgresql://", "db+postgresql://"
)

# Create Celery application
celery_app = Celery(
    "foodplanner",
    broker=REDIS_URL,
    backend=RESULT_BACKEND_URL,
    include=[
        "foodplanner.tasks.ingestion",
        "foodplanner.tasks.graph_ingestion",
        "foodplanner.tasks.scraping",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Copenhagen",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes (for reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    worker_prefetch_multiplier=1,  # One task at a time per worker
    # Result settings
    result_expires=86400 * 7,  # Results expire after 7 days
    # Retry settings (default for all tasks)
    task_default_retry_delay=60,  # 1 minute default retry delay
    task_max_retries=3,
    # Beat scheduler settings
    beat_schedule={
        "daily-ingestion": {
            "task": "foodplanner.tasks.ingestion.run_daily_ingestion_task",
            "schedule": crontab(hour=2, minute=0),  # Run at 2:00 AM daily
            "options": {"queue": "ingestion"},
        },
        "sync-products-to-graph": {
            "task": "foodplanner.tasks.graph_ingestion.sync_products_to_graph_task",
            "schedule": crontab(hour=3, minute=0),  # Run at 3:00 AM daily (after ingestion)
            "options": {"queue": "graph"},
        },
        "weekly-mealdb-refresh": {
            "task": "foodplanner.tasks.graph_ingestion.ingest_mealdb_recipes_task",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Run at 4:00 AM every Sunday
            "options": {"queue": "graph"},
        },
    },
    # Queue routing
    task_routes={
        "foodplanner.tasks.ingestion.*": {"queue": "ingestion"},
        "foodplanner.tasks.graph_ingestion.*": {"queue": "graph"},
        "foodplanner.tasks.scraping.*": {"queue": "scraping"},
    },
    # Logging
    worker_hijack_root_logger=False,  # Don't hijack root logger
)

# Optional: Configure for Windows compatibility (if needed)
if os.name == "nt":
    celery_app.conf.update(
        worker_pool="solo",  # Use solo pool on Windows
    )
