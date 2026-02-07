"""Celery tasks for graph database ingestion and sync."""

import asyncio
from datetime import date
from typing import Any

from celery import shared_task

from foodplanner.celery_app import celery_app
from foodplanner.logging_config import LoggingContext, configure_logging, get_logger

# Configure logging for Celery workers
configure_logging()
logger = get_logger(__name__)


def run_async(coro: Any) -> Any:
    """Run an async coroutine in a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _ingest_mealdb_recipes() -> dict[str, Any]:
    """
    Async implementation of MealDB recipe ingestion.

    Fetches all recipes from TheMealDB and imports them into Neo4j.
    """
    from foodplanner.graph.database import GraphDatabase
    from foodplanner.graph.service import GraphService
    from foodplanner.ingest.connectors.mealdb import MealDBConnector

    results = {
        "status": "pending",
        "categories_imported": 0,
        "areas_imported": 0,
        "recipes_imported": 0,
        "recipes_failed": 0,
        "ingredients_created": 0,
        "errors": [],
    }

    db = GraphDatabase()

    try:
        await db.connect()
        service = GraphService(db)
        await service.setup()

        async with MealDBConnector() as connector:
            # First, import categories
            logger.info("Importing categories from MealDB")
            try:
                categories = await connector.get_categories()
                for cat in categories:
                    await service.import_category(
                        name=cat.get("strCategory", "Unknown"),
                        description=cat.get("strCategoryDescription"),
                        thumbnail=cat.get("strCategoryThumb"),
                    )
                    results["categories_imported"] += 1
                logger.info(f"Imported {results['categories_imported']} categories")
            except Exception as e:
                logger.error(f"Failed to import categories: {e}")
                results["errors"].append(f"Categories: {str(e)}")

            # Import areas/cuisines
            logger.info("Importing areas/cuisines from MealDB")
            try:
                areas = await connector.get_areas()
                for area_name in areas:
                    await service.import_area(area_name)
                    results["areas_imported"] += 1
                logger.info(f"Imported {results['areas_imported']} areas")
            except Exception as e:
                logger.error(f"Failed to import areas: {e}")
                results["errors"].append(f"Areas: {str(e)}")

            # Import all recipes (A-Z)
            logger.info("Fetching all recipes from MealDB (A-Z)")
            try:
                meals = await connector.get_all_meals()
                logger.info(f"Found {len(meals)} meals to import")

                import_result = await service.import_meals_batch(meals, batch_size=25)
                results["recipes_imported"] = import_result["total_imported"]
                results["recipes_failed"] = import_result["total_failed"]

                if import_result["failed_meals"]:
                    results["errors"].extend(
                        [f"Recipe: {m}" for m in import_result["failed_meals"][:10]]
                    )

                logger.info(
                    f"Recipe import complete: {results['recipes_imported']} imported, "
                    f"{results['recipes_failed']} failed"
                )
            except Exception as e:
                logger.error(f"Failed to import recipes: {e}")
                results["errors"].append(f"Recipes: {str(e)}")

            # Get final statistics
            try:
                stats = await service.get_stats()
                results["final_stats"] = stats
                results["ingredients_created"] = stats.get("ingredients", 0)
            except Exception as e:
                logger.warning(f"Failed to get final stats: {e}")

        results["status"] = "completed" if not results["errors"] else "partial"

    except Exception as e:
        logger.exception(f"MealDB ingestion failed: {e}")
        results["status"] = "failed"
        results["errors"].append(str(e))

    finally:
        await db.close()

    return results


async def _sync_products_to_graph() -> dict[str, Any]:
    """
    Async implementation of PostgreSQL to Neo4j product sync.

    Syncs stores and products from PostgreSQL to the Neo4j graph.
    """
    from sqlalchemy import select

    from foodplanner.database import AsyncSessionLocal
    from foodplanner.graph.database import GraphDatabase
    from foodplanner.graph.service import GraphService
    from foodplanner.models import Discount, Product, Store

    results = {
        "status": "pending",
        "stores_synced": 0,
        "products_synced": 0,
        "products_with_discounts": 0,
        "errors": [],
    }

    db = GraphDatabase()

    try:
        await db.connect()
        service = GraphService(db)

        async with AsyncSessionLocal() as session:
            # Sync stores
            logger.info("Syncing stores from PostgreSQL to Neo4j")
            stores_query = select(Store).where(Store.is_active == True)
            stores_result = await session.execute(stores_query)
            stores = stores_result.scalars().all()

            for store in stores:
                try:
                    await service.sync_store(
                        store_id=store.id,
                        name=store.name,
                        brand=store.brand,
                        city=store.city,
                        zip_code=store.zip_code,
                    )
                    results["stores_synced"] += 1
                except Exception as e:
                    logger.error(f"Failed to sync store {store.id}: {e}")
                    results["errors"].append(f"Store {store.id}: {str(e)}")

            logger.info(f"Synced {results['stores_synced']} stores")

            # Get current discounts
            today = date.today()
            discounts_query = select(Discount).where(
                Discount.valid_from <= today,
                Discount.valid_to >= today,
            )
            discounts_result = await session.execute(discounts_query)
            discounts = discounts_result.scalars().all()

            # Build discount lookup by product_id
            discount_lookup: dict[str, Discount] = {}
            for discount in discounts:
                if discount.product_id not in discount_lookup:
                    discount_lookup[discount.product_id] = discount
                elif discount.discount_price < discount_lookup[discount.product_id].discount_price:
                    # Keep the best discount
                    discount_lookup[discount.product_id] = discount

            logger.info(f"Found {len(discount_lookup)} active discounts")

            # Sync products in batches
            logger.info("Syncing products from PostgreSQL to Neo4j")
            products_query = select(Product)
            products_result = await session.execute(products_query)
            products = products_result.scalars().all()

            batch: list[dict[str, Any]] = []
            batch_size = 100

            for product in products:
                discount = discount_lookup.get(product.id)
                discount_price = None
                discount_percentage = None

                if discount:
                    discount_price = discount.discount_price
                    if product.price > 0:
                        discount_percentage = (
                            (product.price - discount.discount_price) / product.price * 100
                        )
                    results["products_with_discounts"] += 1

                batch.append(
                    {
                        "id": product.id,
                        "name": product.name,
                        "brand": product.brand,
                        "category": product.category,
                        "price": product.price,
                        "unit": product.unit,
                        "ean": product.ean,
                        "store_id": product.store_id,
                        "discount_price": discount_price,
                        "discount_percentage": discount_percentage,
                    }
                )

                if len(batch) >= batch_size:
                    try:
                        await service.sync_products_batch(batch)
                        results["products_synced"] += len(batch)
                        logger.debug(f"Synced batch of {len(batch)} products")
                    except Exception as e:
                        logger.error(f"Failed to sync product batch: {e}")
                        results["errors"].append(f"Batch sync: {str(e)}")
                    batch = []

            # Sync remaining products
            if batch:
                try:
                    await service.sync_products_batch(batch)
                    results["products_synced"] += len(batch)
                except Exception as e:
                    logger.error(f"Failed to sync final product batch: {e}")
                    results["errors"].append(f"Final batch: {str(e)}")

            logger.info(
                f"Product sync complete: {results['products_synced']} products, "
                f"{results['products_with_discounts']} with discounts"
            )

        results["status"] = "completed" if not results["errors"] else "partial"

    except Exception as e:
        logger.exception(f"Product sync failed: {e}")
        results["status"] = "failed"
        results["errors"].append(str(e))

    finally:
        await db.close()

    return results


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.graph_ingestion.ingest_mealdb_recipes_task",
    max_retries=2,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=1800,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=3600,  # 1 hour max
    soft_time_limit=3300,  # 55 minutes soft limit
)
def ingest_mealdb_recipes_task(self) -> dict[str, Any]:
    """
    Celery task to ingest all recipes from TheMealDB into Neo4j.

    This task fetches all recipes (A-Z), categories, and areas from TheMealDB
    and imports them into the Neo4j knowledge graph.

    Should be run once initially, then periodically (e.g., weekly) to catch
    any new recipes added to TheMealDB.

    Returns:
        dict with ingestion results summary.
    """
    task_id = self.request.id

    with LoggingContext(task_id=task_id):
        logger.info(f"Starting MealDB recipe ingestion task {task_id}")

        try:
            result = run_async(_ingest_mealdb_recipes())

            status = result.get("status", "unknown")
            logger.info(
                f"MealDB ingestion task {task_id} finished with status: {status}, "
                f"recipes: {result.get('recipes_imported', 0)}"
            )

            return result

        except Exception as e:
            logger.exception(f"MealDB ingestion task {task_id} failed: {e}")
            raise


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.graph_ingestion.sync_products_to_graph_task",
    max_retries=3,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=1800,  # 30 minutes max
    soft_time_limit=1500,  # 25 minutes soft limit
)
def sync_products_to_graph_task(self) -> dict[str, Any]:
    """
    Celery task to sync products from PostgreSQL to Neo4j.

    Syncs all stores and products from the PostgreSQL database to the
    Neo4j knowledge graph, including current discount information.

    Should be run after each data ingestion to keep the graph
    in sync with the latest product and discount data.

    Returns:
        dict with sync results summary.
    """
    task_id = self.request.id

    with LoggingContext(task_id=task_id):
        logger.info(f"Starting product sync task {task_id}")

        try:
            result = run_async(_sync_products_to_graph())

            status = result.get("status", "unknown")
            logger.info(
                f"Product sync task {task_id} finished with status: {status}, "
                f"products: {result.get('products_synced', 0)}"
            )

            return result

        except Exception as e:
            logger.exception(f"Product sync task {task_id} failed: {e}")
            raise


@shared_task(
    name="foodplanner.tasks.graph_ingestion.graph_health_check_task",
)
def graph_health_check_task() -> dict[str, Any]:
    """
    Check the health of the graph database and related services.

    Returns:
        dict with health status of graph components.
    """
    logger.info("Running graph health check")

    results: dict[str, Any] = {
        "neo4j": False,
        "mealdb_api": False,
    }

    # Check Neo4j connection
    try:

        async def check_neo4j() -> bool:
            from foodplanner.graph.database import GraphDatabase

            db = GraphDatabase()
            try:
                return await db.health_check()
            finally:
                await db.close()

        results["neo4j"] = run_async(check_neo4j())
    except Exception as e:
        logger.warning(f"Neo4j health check failed: {e}")
        results["neo4j_error"] = str(e)

    # Check MealDB API
    try:

        async def check_mealdb() -> bool:
            from foodplanner.ingest.connectors.mealdb import MealDBConnector

            connector = MealDBConnector()
            async with connector:
                return await connector.health_check()

        results["mealdb_api"] = run_async(check_mealdb())
    except Exception as e:
        logger.warning(f"MealDB API health check failed: {e}")
        results["mealdb_api_error"] = str(e)

    # Get graph statistics if Neo4j is healthy
    if results["neo4j"]:
        try:

            async def get_stats() -> dict[str, int]:
                from foodplanner.graph.database import GraphDatabase
                from foodplanner.graph.service import GraphService

                db = GraphDatabase()
                try:
                    await db.connect()
                    service = GraphService(db)
                    return await service.get_stats()
                finally:
                    await db.close()

            results["graph_stats"] = run_async(get_stats())
        except Exception as e:
            logger.warning(f"Failed to get graph stats: {e}")
            results["graph_stats_error"] = str(e)

    results["healthy"] = results.get("neo4j", False) and results.get("mealdb_api", False)

    logger.info(f"Graph health check completed: healthy={results['healthy']}")
    return results


async def _compute_ingredient_matches(
    min_confidence: float = 0.6,
    top_k: int = 3,
) -> dict[str, Any]:
    """
    Async implementation of ingredient-to-product matching.
    """
    from foodplanner.graph.database import GraphDatabase
    from foodplanner.graph.matching import IngredientMatcher

    db = GraphDatabase()
    try:
        await db.connect()
        matcher = IngredientMatcher(db)
        return await matcher.compute_all_matches(
            min_confidence=min_confidence,
            top_k=top_k,
        )
    finally:
        await db.close()


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.graph_ingestion.compute_ingredient_matches_task",
    max_retries=2,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True,
    acks_late=True,
    time_limit=3600,  # 1 hour max
)
def compute_ingredient_matches_task(
    self,
    min_confidence: float = 0.6,
    top_k: int = 3,
) -> dict[str, Any]:
    """
    Celery task to compute ingredient-to-product matches.

    Finds matching products for all unmatched ingredients in the graph
    using fuzzy string matching and synonym lookup.

    Args:
        min_confidence: Minimum confidence score to store (0.0-1.0).
        top_k: Maximum number of product matches per ingredient.

    Returns:
        dict with matching results summary.
    """
    task_id = self.request.id

    with LoggingContext(task_id=task_id):
        logger.info(
            f"Starting ingredient matching task {task_id} "
            f"(min_confidence={min_confidence}, top_k={top_k})"
        )

        try:
            result = run_async(_compute_ingredient_matches(min_confidence, top_k))

            logger.info(
                f"Ingredient matching task {task_id} completed: "
                f"{result.get('ingredients_matched', 0)} matched, "
                f"{result.get('total_matches_created', 0)} total matches"
            )

            return result

        except Exception as e:
            logger.exception(f"Ingredient matching task {task_id} failed: {e}")
            raise


@celery_app.task(
    bind=True,
    name="foodplanner.tasks.graph_ingestion.full_graph_refresh_task",
    max_retries=1,
    acks_late=True,
    time_limit=7200,  # 2 hours max
)
def full_graph_refresh_task(self) -> dict[str, Any]:
    """
    Full refresh of the knowledge graph.

    This chains the MealDB ingestion and product sync tasks together.
    Useful for initial setup or periodic full refresh.

    Returns:
        dict with combined results from both tasks.
    """
    task_id = self.request.id

    with LoggingContext(task_id=task_id):
        logger.info(f"Starting full graph refresh task {task_id}")

        results = {
            "mealdb_ingestion": None,
            "product_sync": None,
            "ingredient_matching": None,
            "status": "pending",
        }

        try:
            # Step 1: Ingest MealDB recipes
            logger.info("Step 1: Ingesting MealDB recipes")
            results["mealdb_ingestion"] = run_async(_ingest_mealdb_recipes())

            # Step 2: Sync products from PostgreSQL
            logger.info("Step 2: Syncing products to graph")
            results["product_sync"] = run_async(_sync_products_to_graph())

            # Step 3: Compute ingredient matches
            logger.info("Step 3: Computing ingredient matches")
            results["ingredient_matching"] = run_async(_compute_ingredient_matches())

            # Determine overall status
            mealdb_status = results["mealdb_ingestion"].get("status", "failed")
            sync_status = results["product_sync"].get("status", "failed")
            match_errors = (
                results["ingredient_matching"].get("errors", 0)
                if results["ingredient_matching"]
                else 0
            )

            if mealdb_status == "completed" and sync_status == "completed" and match_errors == 0:
                results["status"] = "completed"
            elif mealdb_status == "failed" and sync_status == "failed":
                results["status"] = "failed"
            else:
                results["status"] = "partial"

            logger.info(f"Full graph refresh completed with status: {results['status']}")

            return results

        except Exception as e:
            logger.exception(f"Full graph refresh task {task_id} failed: {e}")
            results["status"] = "failed"
            results["error"] = str(e)
            raise
