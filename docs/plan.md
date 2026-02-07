# Implementation Plan

This document tracks the implementation status and technical decisions for the Foodplanner project.

## Completed Features

### REMA 1000 Web Scraper ✅

**Status**: Implemented and tested

**Location**: `src/foodplanner/ingest/scrapers/rema1000.py`

**Technical Approach**:

The REMA 1000 website (https://shop.rema1000.dk/) is a Vue.js Single Page Application that renders content client-side via JavaScript. A traditional HTTP-based scraper receives only a loading spinner, so we use **Playwright** (headless Chromium) to render the page and extract product data from the DOM.

**Key Implementation Details**:

| Component | Details |
|-----------|---------|
| Browser | Playwright with headless Chromium |
| Wait Strategy | DOM content loaded + wait for `.product` elements |
| Product Extraction | JavaScript evaluation in page context |
| Data Fields | ID, name, price, unit, origin, image URL, category |

**Product Data Extraction**:

```
HTML Structure:
├── div.product
│   ├── img[src] → Product ID extracted from URL pattern /item/{ID}/
│   ├── span.price-normal → Price in øre (divided by 100)
│   ├── span.price-per-unit → Unit price (e.g., "20.00 per Kg.")
│   ├── div.title → Product name
│   └── div.extra → Unit and origin (e.g., "500 GR. / DANSK")
```

**Supported Categories**:

| Slug | Name |
|------|------|
| `avisvarer` | Weekly Offers |
| `frugt-gront` | Fruits & Vegetables |
| `mejeri` | Dairy |
| `kolonial` | Groceries |
| `kod-fisk-fjerkrae` | Meat, Fish & Poultry |
| `frost` | Frozen |
| `drikkevarer` | Beverages |
| `brod-bavinchi` | Bread |
| `kol` | Refrigerated |
| `ost-mv` | Cheese |
| `husholdning` | Household |
| `baby-og-smaborn` | Baby & Kids |
| `personlig-pleje` | Personal Care |
| `slik` | Candy |
| `kiosk` | Kiosk |

### Database Ingestion Pipeline ✅

**Status**: Implemented and tested

**Location**: `src/foodplanner/ingest/batch_ingest.py`

**Features**:
- Upsert (insert or update) scraped products
- Store tracking with `last_ingested_at` timestamps
- Ingestion run logging for auditability
- Raw data archival for replayability

**Product Model Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Primary key (from scraper) |
| `store_id` | String | Foreign key to stores |
| `name` | String | Product name |
| `price` | Float | Current price |
| `unit` | String | Size/quantity (e.g., "500g") |
| `category` | String | Product category |
| `brand` | String | Brand name |
| `image_url` | Text | Product image URL |
| `description` | Text | Additional info |
| `origin` | String | Country/source |
| `ean` | String | Barcode (if available) |
| `last_updated` | DateTime | Last scrape timestamp |

---

## In Progress

### Additional Store Scrapers

| Store | Status | Notes |
|-------|--------|-------|
| Netto | Planned | Similar SPA architecture expected |
| Føtex | Planned | Part of Salling Group |
| Bilka | Planned | Part of Salling Group |

### Recipe Matching

Matching scraped products to recipe ingredients using the Neo4j knowledge graph. See [graph-database.md](graph-database.md).

---

## Planned Features

### Meal Plan Optimization

Use discounted products to generate cost-effective meal plans:
- Linear programming for optimal recipe selection
- Budget constraints
- Nutritional balance

### User Authentication

- JWT-based authentication
- User preferences storage
- Saved meal plans

### Frontend

- React/Next.js web application
- Mobile-responsive design
- Shopping list export

---

## Architecture Decisions

### Why Playwright for REMA 1000?

**Decision**: Use Playwright instead of direct HTTP requests.

**Rationale**:
1. REMA 1000 is a JavaScript SPA - no product data in initial HTML
2. No public JSON API discovered
3. Playwright renders the full page like a real browser
4. Reliable extraction from rendered DOM elements

**Trade-offs**:
- Slower than HTTP requests (~8-10s per page vs ~1s)
- Requires Chromium binary (~170MB)
- Higher memory usage

**Mitigations**:
- Batch scraping during off-peak hours (2 AM daily)
- Rate limiting to avoid overload
- Caching scraped data in database

### Database Strategy

**Decision**: Use PostgreSQL for all environments (development, testing, production).

**Rationale**:
1. Consistent behavior across environments
2. Access to PostgreSQL-specific features (JSON operations, full-text search)
3. Tests use a separate `foodplanner_test` database to avoid conflicts
4. Docker Compose provides easy local PostgreSQL setup

**Usage**:
- Tests use `TEST_DATABASE_URL` env var (defaults to `foodplanner_test` database)
- Local development uses `DATABASE_URL` from `.env`
- Production uses `DATABASE_URL` environment variable

---

## Testing Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| REMA 1000 Scraper | 20 unit + 6 integration | High |
| Product Ingestion | 6 integration | High |
| Batch Pipeline | Existing tests | Medium |

See [testing.md](testing.md) for details.

---

## Development Scripts

### `scripts/scrape_to_db.py`

Utility script for local development and testing (requires PostgreSQL):

```bash
# Scrape products to PostgreSQL database
uv run python scripts/scrape_to_db.py --limit 50

# Scrape specific category
uv run python scripts/scrape_to_db.py --category frugt-gront --limit 30

# Query stored products
uv run python scripts/scrape_to_db.py --query

# Interactive SQL mode
uv run python scripts/scrape_to_db.py --interactive
```

---

## Dependencies Added

| Package | Version | Purpose |
|---------|---------|---------|
| `playwright` | 1.58.0+ | Browser automation for SPA scraping |

Install browsers after adding playwright:
```bash
uv run playwright install chromium
```
