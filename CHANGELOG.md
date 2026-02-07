# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Web Scraping Architecture** - New scalable system for scraping grocery store product data
  - `BaseScraper` abstract class with rate limiting, retry logic, and error handling
  - `Rema1000Scraper` implementation for https://shop.rema1000.dk/
  - Scraper registry with `get_scraper_for_store()` factory function
  - Support for scraping products, categories, and product search

- **New Dependencies**
  - `beautifulsoup4>=4.12.0` for HTML parsing
  - `lxml>=5.0.0` for fast HTML/XML parsing

- **Configuration Options**
  - `SCRAPING_RATE_LIMIT` - Seconds between requests (default: 1.0)
  - `SCRAPING_TIMEOUT` - Request timeout in seconds (default: 30.0)
  - `SCRAPING_MAX_RETRIES` - Retry attempts for failed requests (default: 3)

- **Test Coverage**
  - `tests/test_scrapers.py` with comprehensive tests for scraper functionality

### Changed

- **Data Ingestion Pipeline** - Refactored from API-based to scraping-based approach
  - `batch_ingest.py` now uses scrapers instead of API connectors
  - `ingest_store()` function updated to work with scraper interface
  - New `_upsert_scraped_products()` function for database operations

- **Schemas** - `src/foodplanner/ingest/schemas.py` completely rewritten
  - Replaced Salling-specific schemas with generic `ScrapedProduct`, `ScrapedDiscount`, `StoreInfo`
  - Added flexible price parsing (Danish number format support)
  - Added brand normalization for Danish stores

- **Health Checks** - Simplified to check database and Redis only
  - Removed external API health checks from ingestion health endpoint

- **Store Discovery API** - `/api/v1/stores/discover` now reads from database only
  - Stores are populated via the scraping pipeline

- **Documentation** - Updated all documentation to reflect new architecture
  - `docs/integrations.md` - Complete rewrite with scraping documentation
  - `docs/pipeline.md` - Updated data flow diagrams
  - `docs/graph-database.md` - Updated data source references
  - `docs/docker.md` - Removed API key requirements
  - `docs/testing.md` - Updated test documentation
  - `README.md` - Updated overview and roadmap
  - `CONTRIBUTING.md` - Added guide for creating new scrapers

### Removed

- **Salling Group API Integration** - Completely removed
  - Deleted `src/foodplanner/ingest/connectors/salling.py`
  - Deleted `tests/test_salling_connector.py`
  - Deleted `tests/test_salling_schemas.py`
  - Deleted `tests/integration/test_salling_integration.py`
  - Removed `SALLING_API_KEY` from configuration and docker-compose
  - Removed `salling_api_key` from `Settings` class

### Migration Guide

If you were using the Salling API integration:

1. **Remove API Key**: The `SALLING_API_KEY` environment variable is no longer needed
2. **Update Store IDs**: Stores are now identified by scraper brand (e.g., `rema1000`)
3. **Trigger Ingestion**: Run the scraping pipeline to populate product data:
   ```bash
   uv run python -m foodplanner.ingest.batch_ingest
   ```

### Technical Notes

- The scraping system is designed to be respectful of target websites:
  - Rate limiting prevents overwhelming servers
  - Browser-like User-Agent headers
  - Configurable delays between requests
- Future store scrapers should inherit from `BaseScraper` and implement:
  - `scrape_products(category, limit)` - Required
  - `scrape_categories()` - Required
  - `scrape_product_details(product_id)` - Optional

## [0.1.0] - 2026-02-04

### Added

- Initial project structure with FastAPI backend
- PostgreSQL database with SQLAlchemy models
- Neo4j knowledge graph for recipes
- MealDB connector for recipe data
- Product-to-ingredient matching with fuzzy search
- Celery task queue with Redis
- Docker Compose development environment
- Comprehensive test suite
