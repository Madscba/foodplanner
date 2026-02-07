# Testing Strategy

This document describes the testing approach for the Foodplanner project, covering unit tests, integration tests, and end-to-end pipeline tests.

## Overview

The test suite is organized in three layers:

```
tests/
├── conftest.py                 # Shared fixtures and pytest configuration
├── test_scrapers.py            # Unit tests for web scrapers
├── test_mealdb_connector.py    # Unit tests for MealDB connector
├── test_ingredient_matching.py # Unit tests for ingredient matching
├── test_graph_models.py        # Unit tests for Neo4j graph models
├── test_health.py              # API health endpoint tests
└── integration/
    ├── __init__.py
    ├── test_ingestion_pipeline.py    # End-to-end pipeline tests
    ├── test_infrastructure.py        # Docker, database, Celery tests
    ├── test_rema1000_scraper.py      # REMA 1000 scraper integration tests
    └── test_product_ingestion.py     # Product DB ingestion tests
```

## Test Layers

### 1. Unit Tests (No External Dependencies)

Unit tests use mocked dependencies and can run without any API keys or database connections.

#### Web Scraper Tests (`test_scrapers.py`)

Tests the web scraper classes with mocked HTTP responses:

| Test Class | What's Tested |
|------------|---------------|
| `TestBaseScraper` | ScrapedProduct dataclass, serialization |
| `TestScraperRegistry` | Store-to-scraper mapping, case insensitivity |
| `TestRema1000Scraper` | Product parsing, price parsing, categories |
| `TestScraperErrors` | Error handling, rate limit errors |

#### Schema Validation Tests (`test_scrapers.py`)

Tests Pydantic schemas for scraped data:

| Test Class | What's Tested |
|------------|---------------|
| `TestScrapedProduct` | Price parsing, EAN normalization |
| `TestScrapedDiscount` | Discount percentage calculation |
| `TestStoreInfo` | Brand normalization |

### 2. Integration Tests (Network/Docker Required)

Integration tests make real network requests or require Docker services.

#### REMA 1000 Scraper Tests (`integration/test_rema1000_scraper.py`)

Tests the REMA 1000 scraper against the live website using Playwright:

| Test | What's Tested |
|------|---------------|
| `test_health_check` | Scraper can reach the website |
| `test_fetch_10_products` | Scrape and validate 10 products |
| `test_fetch_products_with_category` | Category-specific scraping |
| `test_fetch_categories` | Category listing |
| `test_search_products` | Product search functionality |
| `test_product_data_quality` | Data completeness validation |

```bash
# Run REMA 1000 scraper tests
uv run pytest tests/integration/test_rema1000_scraper.py -v -s
```

#### Product Ingestion Tests (`integration/test_product_ingestion.py`)

Tests the complete scrape-to-database pipeline using PostgreSQL:

| Test | What's Tested |
|------|---------------|
| `test_scrape_and_ingest_10_products` | End-to-end scrape and store |
| `test_upsert_updates_existing_products` | Upsert idempotency |
| `test_scrape_category_and_ingest` | Category-specific ingestion |
| `test_product_fields_stored_correctly` | All fields persisted |
| `test_ingest_multiple_categories` | Multi-category batch |
| `test_large_batch_ingestion` | 50 product batch |

```bash
# Run product ingestion tests
uv run pytest tests/integration/test_product_ingestion.py -v -s
```

#### Pipeline Tests (`integration/test_ingestion_pipeline.py`)

| Test Class | What's Tested |
|------------|---------------|
| `TestUpsertScrapedProducts` | Product creation, update idempotency |
| `TestIngestionResult` | Result tracking and serialization |
| `TestIngestStoreMocked` | Single store ingestion (mocked scraper) |
| `TestRunDailyIngestionMocked` | Full daily run, idempotency, force flag |
| `TestCleanupOldData` | Data retention and cleanup |

### 3. Infrastructure Tests (Require Docker)

Tests for Docker services, database connectivity, and Celery configuration.

#### Infrastructure Tests (`integration/test_infrastructure.py`)

| Test Class | What's Tested |
|------------|---------------|
| `TestPostgreSQLConnectivity` | Sync/async connections, version check, table existence |
| `TestNeo4jConnectivity` | Connection, queries, version check, GraphDatabase class |
| `TestRedisConnectivity` | Connection, set/get operations, version check |
| `TestCeleryConfiguration` | App config, task registration, beat schedule, task routes |
| `TestCeleryWorkerConnectivity` | Broker connection, worker ping, active task inspection |
| `TestDockerComposeServices` | Container health status for all services |
| `TestSystemHealthCheck` | Full system health check across all services |

## Running Tests

### Prerequisites

```bash
# Install dev dependencies
uv sync --extra dev

# Install Playwright browsers (required for REMA 1000 scraper tests)
uv run playwright install chromium
```

### Quick Commands

```bash
# Run all unit tests (no external dependencies needed)
uv run pytest -m "not integration"

# Run specific test file
uv run pytest tests/test_scrapers.py -v

# Run with coverage report
uv run pytest -m "not integration" --cov=foodplanner --cov-report=html

# Run tests matching a pattern
uv run pytest -k "test_parse_product" -v
```

### Integration Tests

Integration tests may require network access or Docker services:

```bash
# Run pipeline tests (uses mocked scrapers by default)
uv run pytest tests/integration/test_ingestion_pipeline.py -v -m integration

# Run with real scraping (makes network requests)
uv run pytest tests/integration/ -v -m "integration and not slow"
```

### Infrastructure Tests

Infrastructure tests require Docker Compose services to be running:

```bash
# Start all services
docker-compose up -d

# Run infrastructure tests
uv run pytest tests/integration/test_infrastructure.py -v -m integration

# Run specific test classes
uv run pytest tests/integration/test_infrastructure.py::TestPostgreSQLConnectivity -v
uv run pytest tests/integration/test_infrastructure.py::TestNeo4jConnectivity -v
uv run pytest tests/integration/test_infrastructure.py::TestRedisConnectivity -v
uv run pytest tests/integration/test_infrastructure.py::TestCeleryConfiguration -v

# Run Docker health checks only (requires Docker CLI)
uv run pytest tests/integration/test_infrastructure.py::TestDockerComposeServices -v
```

**Note:** Some Celery tests require a running worker:

```bash
# Start worker in another terminal
docker-compose up -d celery-worker

# Or run locally
uv run celery -A foodplanner.celery_app worker --loglevel=info
```

### Test Markers

The project uses pytest markers to categorize tests:

| Marker | Description |
|--------|-------------|
| `integration` | Tests that require network access or Docker |
| `slow` | Tests that take longer to run (e.g., multiple network calls) |

```bash
# Skip integration tests
uv run pytest -m "not integration"

# Skip slow tests
uv run pytest -m "not slow"

# Run only integration tests
uv run pytest -m integration

# Combine markers
uv run pytest -m "integration and not slow"
```

### Using Make

```bash
# Run all tests (unit only by default)
make test

# Run with verbose output
make test PYTEST_ARGS="-v"
```

## Test Fixtures

### Shared Fixtures (`conftest.py`)

#### Mock Response Fixtures

```python
# Scraped product mock data
mock_scraped_products       # Sample scraped products
mock_rema1000_store         # Sample REMA 1000 store

# MealDB API mock responses
mock_mealdb_categories_response   # Recipe categories
mock_mealdb_meal_response         # Single meal details
mock_mealdb_search_response       # Meal search results
```

#### Integration Test Fixtures

```python
# Database fixtures (for pipeline tests)
test_db_engine     # PostgreSQL test database
test_session       # Database session
sample_store       # Pre-created test store
sample_scraped_products # Sample scraped data
```

## Writing New Tests

### Unit Test Example

```python
import pytest
from unittest.mock import AsyncMock, patch

from foodplanner.ingest.scrapers import Rema1000Scraper


class TestMyFeature:
    @pytest.fixture
    def scraper(self):
        return Rema1000Scraper()

    @pytest.mark.asyncio
    async def test_my_feature(self, scraper):
        mock_response = {"products": [{"id": "1", "name": "Test", "price": 10.0}]}

        with patch.object(scraper, "get_json", AsyncMock(return_value=mock_response)):
            result = await scraper.scrape_products()

            assert len(result) > 0
```

### Integration Test Example

```python
import pytest

from foodplanner.ingest.scrapers import Rema1000Scraper


@pytest.mark.integration
@pytest.mark.slow
class TestMyIntegration:
    @pytest.mark.asyncio
    async def test_real_scraping(self):
        """Test with real network request."""
        scraper = Rema1000Scraper()

        async with scraper:
            result = await scraper.scrape_products(limit=5)

        assert isinstance(result, list)
        assert len(result) <= 5
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --extra dev
      - run: uv run pytest -m "not integration" --cov=foodplanner

  infrastructure-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: foodplanner
          POSTGRES_PASSWORD: foodplanner_dev
          POSTGRES_DB: foodplanner
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      neo4j:
        image: neo4j:5-community
        env:
          NEO4J_AUTH: neo4j/foodplanner_dev
        ports:
          - 7687:7687
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --extra dev
      - run: uv run pytest tests/integration/test_infrastructure.py -v -m integration
        env:
          DATABASE_URL: postgresql+asyncpg://foodplanner:foodplanner_dev@localhost:5432/foodplanner
          REDIS_URL: redis://localhost:6379/0
          NEO4J_URI: bolt://localhost:7687
          NEO4J_USER: neo4j
          NEO4J_PASSWORD: foodplanner_dev
```

## Test Coverage Goals

| Component | Target Coverage |
|-----------|----------------|
| Scrapers (`ingest/scrapers/`) | 90%+ |
| Schemas (`ingest/schemas.py`) | 95%+ |
| Batch ingestion (`ingest/batch_ingest.py`) | 80%+ |
| API routers (`routers/`) | 70%+ |

Generate coverage report:

```bash
uv run pytest --cov=foodplanner --cov-report=html
# Open htmlcov/index.html in browser
```

## Troubleshooting

### Common Issues

**Async test failures**
- Ensure `pytest-asyncio` is installed
- Check that `asyncio_mode = auto` is in `pytest.ini`

**Database connection errors in pipeline tests**
- Pipeline tests require PostgreSQL to be running
- Ensure Docker is running: `docker-compose up -d db`
- A separate test database (`foodplanner_test`) is used to avoid conflicts

**Network errors in scraper tests**
- Check internet connectivity
- Some tests may be rate-limited; wait and retry
- Consider using `@pytest.mark.slow` and running slow tests separately

**PostgreSQL connection refused**
- Ensure Docker is running: `docker-compose up -d postgres`
- Check the container is healthy: `docker-compose ps`
- Verify the port is not in use: `netstat -an | grep 5432`

**Neo4j connection failed**
- Neo4j takes longer to start (~30 seconds); wait for healthy status
- Check logs: `docker-compose logs neo4j`
- Verify bolt port is accessible: `docker-compose ps`

**Redis connection refused**
- Start Redis: `docker-compose up -d redis`
- Test with redis-cli: `docker exec -it foodplanner-redis redis-cli ping`

**Celery worker tests skipped**
- Start a worker: `docker-compose up -d celery-worker`
- Or run locally: `uv run celery -A foodplanner.celery_app worker --loglevel=info`

**Docker inspect tests fail**
- Ensure Docker CLI is available in PATH
- Container names must match: `foodplanner-db`, `foodplanner-redis`, etc.
- Run `docker ps` to verify containers are running
