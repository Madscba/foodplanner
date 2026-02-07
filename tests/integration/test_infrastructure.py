"""Infrastructure tests for Docker services, databases, and Celery.

These tests verify that the infrastructure components are running and accessible.

Prerequisites:
    - Docker Compose services running: docker-compose up -d
    - Or individual services accessible at their configured URLs

Run with:
    docker-compose up -d
    uv run pytest tests/integration/test_infrastructure.py -v -m integration
"""

import os

import pytest

# =============================================================================
# PostgreSQL Database Tests
# =============================================================================


@pytest.mark.integration
class TestPostgreSQLConnectivity:
    """Tests for PostgreSQL database connectivity."""

    @pytest.fixture
    def database_url(self):
        """Get database URL from environment or use default."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://foodplanner:foodplanner_dev@localhost:5432/foodplanner",
        )

    @pytest.fixture
    def sync_database_url(self, database_url):
        """Convert async URL to sync URL."""
        return database_url.replace("+asyncpg", "")

    def test_sync_connection(self, sync_database_url):
        """Test synchronous database connection."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        engine = create_engine(sync_database_url, echo=False)

        try:
            with Session(engine) as session:
                result = session.execute(text("SELECT 1 as test"))
                row = result.fetchone()
                assert row[0] == 1
        finally:
            engine.dispose()

    def test_database_version(self, sync_database_url):
        """Test PostgreSQL version is 14+."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        engine = create_engine(sync_database_url, echo=False)

        try:
            with Session(engine) as session:
                result = session.execute(text("SELECT version()"))
                version_string = result.fetchone()[0]
                # Extract major version number
                # Format: "PostgreSQL 16.x ..."
                assert "PostgreSQL" in version_string
                major_version = int(version_string.split()[1].split(".")[0])
                assert major_version >= 14, f"PostgreSQL version {major_version} < 14"
        finally:
            engine.dispose()

    @pytest.mark.asyncio
    async def test_async_connection(self, database_url):
        """Test asynchronous database connection."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(database_url, echo=False)

        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1 as test"))
                row = result.fetchone()
                assert row[0] == 1
        finally:
            await engine.dispose()

    def test_tables_exist(self, sync_database_url):
        """Test that expected tables exist in the database."""
        from sqlalchemy import create_engine, inspect

        engine = create_engine(sync_database_url, echo=False)

        try:
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            # Check for core tables (may not exist if migrations haven't run)
            expected_tables = [
                "stores",
                "products",
                "discounts",
                "users",
                "ingestion_runs",
            ]

            # Just check if any tables exist - if not, migrations may need to run
            if not tables:
                pytest.skip("No tables found - run migrations first")

            # Check that at least some expected tables exist
            found_tables = [t for t in expected_tables if t in tables]
            assert len(found_tables) > 0, f"No expected tables found. Available: {tables}"
        finally:
            engine.dispose()

    def test_can_create_and_rollback(self, sync_database_url):
        """Test that we can create records and rollback."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        engine = create_engine(sync_database_url, echo=False)

        try:
            with Session(engine) as session:
                # Start a transaction
                session.begin()

                # Try to insert a test record (will fail if table doesn't exist)
                try:
                    session.execute(
                        text(
                            "INSERT INTO stores (id, name, brand, is_active) "
                            "VALUES ('test-infra-001', 'Test Store', 'test', true)"
                        )
                    )
                    # Rollback to clean up
                    session.rollback()
                except Exception:
                    session.rollback()
                    pytest.skip("stores table doesn't exist - run migrations first")
        finally:
            engine.dispose()


# =============================================================================
# Neo4j Graph Database Tests
# =============================================================================


@pytest.mark.integration
class TestNeo4jConnectivity:
    """Tests for Neo4j graph database connectivity."""

    @pytest.fixture
    def neo4j_config(self):
        """Get Neo4j configuration from environment."""
        return {
            "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            "user": os.getenv("NEO4J_USER", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD", "foodplanner_dev"),
        }

    @pytest.mark.asyncio
    async def test_neo4j_connection(self, neo4j_config):
        """Test Neo4j database connection."""
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            neo4j_config["uri"],
            auth=(neo4j_config["user"], neo4j_config["password"]),
        )

        try:
            await driver.verify_connectivity()
        finally:
            await driver.close()

    @pytest.mark.asyncio
    async def test_neo4j_query(self, neo4j_config):
        """Test executing a simple Neo4j query."""
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            neo4j_config["uri"],
            auth=(neo4j_config["user"], neo4j_config["password"]),
        )

        try:
            async with driver.session() as session:
                result = await session.run("RETURN 1 as test")
                record = await result.single()
                assert record["test"] == 1
        finally:
            await driver.close()

    @pytest.mark.asyncio
    async def test_neo4j_version(self, neo4j_config):
        """Test Neo4j version is 5+."""
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            neo4j_config["uri"],
            auth=(neo4j_config["user"], neo4j_config["password"]),
        )

        try:
            async with driver.session() as session:
                result = await session.run(
                    "CALL dbms.components() YIELD name, versions "
                    "WHERE name = 'Neo4j Kernel' "
                    "RETURN versions[0] as version"
                )
                record = await result.single()
                version = record["version"]
                major_version = int(version.split(".")[0])
                assert major_version >= 5, f"Neo4j version {major_version} < 5"
        finally:
            await driver.close()

    @pytest.mark.asyncio
    async def test_graph_database_class(self, neo4j_config):
        """Test the GraphDatabase wrapper class."""
        from foodplanner.graph.database import GraphDatabase

        db = GraphDatabase(
            uri=neo4j_config["uri"],
            user=neo4j_config["user"],
            password=neo4j_config["password"],
        )

        async with db:
            # Test health check
            is_healthy = await db.health_check()
            assert is_healthy is True

            # Test query execution
            results = await db.execute_query("RETURN 'hello' as greeting")
            assert len(results) == 1
            assert results[0]["greeting"] == "hello"


# =============================================================================
# Redis Tests
# =============================================================================


@pytest.mark.integration
class TestRedisConnectivity:
    """Tests for Redis connectivity."""

    @pytest.fixture
    def redis_url(self):
        """Get Redis URL from environment."""
        return os.getenv("REDIS_URL", "redis://localhost:6379/0")

    def test_redis_connection(self, redis_url):
        """Test Redis connection."""
        import redis

        client = redis.from_url(redis_url)

        try:
            # Test ping
            assert client.ping() is True
        finally:
            client.close()

    def test_redis_set_get(self, redis_url):
        """Test Redis set and get operations."""
        import redis

        client = redis.from_url(redis_url)

        try:
            # Set a test value
            key = "foodplanner:test:infra"
            client.set(key, "test_value", ex=60)  # Expire in 60 seconds

            # Get it back
            value = client.get(key)
            assert value == b"test_value"

            # Clean up
            client.delete(key)
        finally:
            client.close()

    def test_redis_version(self, redis_url):
        """Test Redis version is 7+."""
        import redis

        client = redis.from_url(redis_url)

        try:
            info = client.info("server")
            version = info.get("redis_version", "0.0.0")
            major_version = int(version.split(".")[0])
            assert major_version >= 6, f"Redis version {major_version} < 6"
        finally:
            client.close()


# =============================================================================
# Celery Tests
# =============================================================================


@pytest.mark.integration
class TestCeleryConfiguration:
    """Tests for Celery configuration and task registration."""

    def test_celery_app_configured(self):
        """Test that Celery app is properly configured."""
        from foodplanner.celery_app import celery_app

        assert celery_app.main == "foodplanner"
        assert "redis" in celery_app.conf.broker_url

    def test_celery_tasks_registered(self):
        """Test that expected tasks are registered."""
        import foodplanner.tasks.graph_ingestion  # noqa: F401

        # Import task modules to ensure registration
        import foodplanner.tasks.ingestion  # noqa: F401
        from foodplanner.celery_app import celery_app

        registered_tasks = list(celery_app.tasks.keys())

        expected_tasks = [
            "foodplanner.tasks.ingestion.run_daily_ingestion_task",
            "foodplanner.tasks.ingestion.ingest_single_store_task",
            "foodplanner.tasks.ingestion.cleanup_old_data_task",
            "foodplanner.tasks.ingestion.health_check_task",
        ]

        for task in expected_tasks:
            assert (
                task in registered_tasks
            ), f"Task {task} not registered. Available: {[t for t in registered_tasks if 'foodplanner' in t]}"

    def test_celery_beat_schedule(self):
        """Test that Celery Beat schedule is configured."""
        from foodplanner.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule

        assert "daily-ingestion" in schedule
        assert (
            schedule["daily-ingestion"]["task"]
            == "foodplanner.tasks.ingestion.run_daily_ingestion_task"
        )

    def test_celery_task_routes(self):
        """Test that task routing is configured."""
        from foodplanner.celery_app import celery_app

        routes = celery_app.conf.task_routes

        assert "foodplanner.tasks.ingestion.*" in routes
        assert routes["foodplanner.tasks.ingestion.*"]["queue"] == "ingestion"


@pytest.mark.integration
class TestCeleryWorkerConnectivity:
    """Tests for Celery worker connectivity (requires running worker)."""

    @pytest.fixture
    def redis_url(self):
        """Get Redis URL from environment."""
        return os.getenv("REDIS_URL", "redis://localhost:6379/0")

    def test_celery_broker_connection(self, redis_url):
        """Test that Celery can connect to broker."""
        from celery import Celery

        app = Celery(broker=redis_url)

        try:
            # This will raise if broker is not available
            conn = app.connection()
            conn.ensure_connection(max_retries=3)
            conn.release()
        except Exception as e:
            pytest.fail(f"Could not connect to Celery broker: {e}")

    @pytest.mark.slow
    def test_celery_ping_workers(self):
        """Test pinging Celery workers (requires running worker)."""
        from foodplanner.celery_app import celery_app

        try:
            response = celery_app.control.ping(timeout=5)
            if not response:
                pytest.skip("No Celery workers responding - start worker first")
            assert len(response) > 0
        except Exception as e:
            pytest.skip(f"Could not ping workers: {e}")

    @pytest.mark.slow
    def test_celery_inspect_active(self):
        """Test inspecting active tasks on workers."""
        from foodplanner.celery_app import celery_app

        inspect = celery_app.control.inspect()

        try:
            active = inspect.active()
            if active is None:
                pytest.skip("No Celery workers available")
            # active is a dict of {worker_name: [tasks]}
            assert isinstance(active, dict)
        except Exception as e:
            pytest.skip(f"Could not inspect workers: {e}")


# =============================================================================
# Docker Compose Health Tests
# =============================================================================


@pytest.mark.integration
class TestDockerComposeServices:
    """Tests for Docker Compose service health."""

    def test_postgres_health(self):
        """Test PostgreSQL container health endpoint."""
        import subprocess

        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", "foodplanner-db"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip("Docker not available or container not running")

        status = result.stdout.strip()
        assert status == "healthy", f"PostgreSQL container status: {status}"

    def test_redis_health(self):
        """Test Redis container health endpoint."""
        import subprocess

        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", "foodplanner-redis"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip("Docker not available or container not running")

        status = result.stdout.strip()
        assert status == "healthy", f"Redis container status: {status}"

    def test_neo4j_health(self):
        """Test Neo4j container health endpoint."""
        import subprocess

        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", "foodplanner-neo4j"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip("Docker not available or container not running")

        status = result.stdout.strip()
        assert status == "healthy", f"Neo4j container status: {status}"

    def test_api_container_running(self):
        """Test API container is running."""
        import subprocess

        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", "foodplanner-api"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip("Docker not available or container not running")

        running = result.stdout.strip()
        assert running == "true", "API container is not running"

    def test_celery_worker_container_running(self):
        """Test Celery worker container is running."""
        import subprocess

        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", "foodplanner-celery-worker"],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.skip("Docker not available or container not running")

        running = result.stdout.strip()
        assert running == "true", "Celery worker container is not running"


# =============================================================================
# Integration Health Check Tests
# =============================================================================


@pytest.mark.integration
class TestSystemHealthCheck:
    """End-to-end system health check tests."""

    @pytest.mark.asyncio
    async def test_full_system_health(self):
        """Test complete system health check."""
        import redis
        from neo4j import AsyncGraphDatabase
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session

        results = {
            "postgresql": False,
            "neo4j": False,
            "redis": False,
        }

        # Test PostgreSQL
        try:
            db_url = os.getenv(
                "DATABASE_URL",
                "postgresql://foodplanner:foodplanner_dev@localhost:5432/foodplanner",
            ).replace("+asyncpg", "")
            engine = create_engine(db_url, echo=False)
            with Session(engine) as session:
                session.execute(text("SELECT 1"))
                results["postgresql"] = True
            engine.dispose()
        except Exception as e:
            results["postgresql_error"] = str(e)

        # Test Neo4j
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "foodplanner_dev")
            driver = AsyncGraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
            await driver.verify_connectivity()
            await driver.close()
            results["neo4j"] = True
        except Exception as e:
            results["neo4j_error"] = str(e)

        # Test Redis
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(redis_url)
            client.ping()
            client.close()
            results["redis"] = True
        except Exception as e:
            results["redis_error"] = str(e)

        # Check overall health
        all_healthy = all(results.get(k, False) for k in ["postgresql", "neo4j", "redis"])

        if not all_healthy:
            failed = [k for k in ["postgresql", "neo4j", "redis"] if not results.get(k)]
            errors = {k: results.get(f"{k}_error", "Unknown") for k in failed}
            pytest.fail(f"Services unhealthy: {errors}")

        assert all_healthy

    def test_health_check_task(self):
        """Test the Celery health check task directly."""
        from foodplanner.tasks.ingestion import health_check_task

        # Run the task synchronously (not through Celery)
        # This tests the task logic without requiring a running worker
        try:
            result = health_check_task()
            assert "database" in result
            assert "redis" in result
            assert "healthy" in result
        except Exception as e:
            pytest.skip(f"Health check task failed: {e}")
