# Store Integrations

## Web Scraping Architecture

The foodplanner application uses web scraping to collect product data from Danish grocery stores.
The scraping system is designed to be scalable and extensible for multiple stores.

### Supported Stores

| Store | Status | Implementation |
|-------|--------|----------------|
| REMA 1000 | ✅ Active | `Rema1000Scraper` |
| Netto | 🚧 Planned | - |
| Føtex | 🚧 Planned | - |
| Bilka | 🚧 Planned | - |

### Architecture Overview

```
foodplanner/ingest/scrapers/
├── __init__.py      # Registry and factory functions
├── base.py          # BaseScraper abstract class
└── rema1000.py      # REMA 1000 implementation
```

### Base Scraper Features

All scrapers inherit from `BaseScraper` which provides:

- **Rate Limiting**: Configurable delay between requests
- **Retry Logic**: Automatic retries with exponential backoff
- **Error Handling**: Standardized error types
- **HTTP Client Management**: Shared async HTTP client
- **Headers**: Browser-like headers to avoid blocking

### Adding a New Scraper

1. Create a new file in `foodplanner/ingest/scrapers/`:

```python
from foodplanner.ingest.scrapers.base import BaseScraper

class NewStoreScraper(BaseScraper):
    BASE_URL = "https://newstore.dk"
    STORE_NAME = "New Store"
    STORE_BRAND = "newstore"

    async def scrape_products(self, category=None, limit=None):
        # Implementation
        pass

    async def scrape_categories(self):
        # Implementation
        pass
```

2. Register in `__init__.py`:

```python
from foodplanner.ingest.scrapers.newstore import NewStoreScraper

SCRAPER_REGISTRY["newstore"] = NewStoreScraper
```

3. Add tests in `tests/test_scrapers.py`

## REMA 1000

### Website

- **URL**: https://shop.rema1000.dk/
- **Type**: Online grocery shop with API backend
- **Data Format**: JSON API responses

### API Endpoints

The REMA 1000 web shop exposes a REST API:

#### Products

```http
GET /api/v2/catalog/store/1/products
```

**Parameters**:
- `page`: Page number (1-indexed)
- `pageSize`: Items per page (max 100)
- `category`: Category ID filter

**Response**:
```json
{
  "products": [...],
  "pagination": {
    "page": 1,
    "pageSize": 100,
    "totalPages": 50,
    "totalItems": 5000
  }
}
```

#### Categories

```http
GET /api/v2/catalog/store/1/categories
```

Returns hierarchical category structure with subcategories.

#### Product Search

```http
GET /api/v2/catalog/store/1/search?query=kylling
```

### Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Product identifier |
| `name` | string | Product name |
| `price` | float | Current price in DKK |
| `ean` | string | Barcode (EAN-13) |
| `categories` | array | Category hierarchy |
| `images` | array | Product image URLs |
| `brand` | string | Brand name |
| `description` | string | Product description |
| `ingredients` | string | Ingredient list |
| `nutritionInfo` | object | Nutritional values |

### Rate Limiting

- Default: 1 second between requests
- No known hard rate limits
- Configurable via `SCRAPING_RATE_LIMIT` env var

### Compliance

#### Robots.txt

Always respect the site's robots.txt:

```
# Check https://shop.rema1000.dk/robots.txt
User-agent: *
Disallow: /checkout/
Allow: /
```

#### Terms of Service

- Scraping for personal use
- Do not overload servers
- Cache data locally
- Add appropriate delays

#### Best Practices

1. **Identify your scraper**: Use descriptive User-Agent
2. **Limit frequency**: Don't make concurrent requests
3. **Cache responses**: Store scraped data locally
4. **Handle errors gracefully**: Don't retry aggressively
5. **Run during off-peak**: Schedule scraping at night

## Configuration

### Environment Variables

```bash
# Scraping configuration
SCRAPING_RATE_LIMIT=1.0      # Seconds between requests
SCRAPING_TIMEOUT=30.0        # Request timeout in seconds
SCRAPING_MAX_RETRIES=3       # Retry attempts for failed requests
```

### Scraper Settings

```python
from foodplanner.ingest.scrapers import Rema1000Scraper

# Custom configuration
scraper = Rema1000Scraper(
    timeout=60.0,        # Longer timeout
    rate_limit=2.0,      # Slower requests
    max_retries=5,       # More retries
)
```

## Testing

### Unit Tests

```bash
# Run scraper tests
uv run pytest tests/test_scrapers.py -v
```

### Integration Tests

```bash
# Run with network access (makes real requests)
uv run pytest tests/integration/ -v -m integration
```

### Mocking Responses

For unit tests, mock the HTTP responses:

```python
@pytest.mark.asyncio
async def test_scrape_products():
    scraper = Rema1000Scraper()

    mock_response = {"products": [...]}

    with patch.object(scraper, "get_json", AsyncMock(return_value=mock_response)):
        products = await scraper.scrape_products()
        assert len(products) > 0
```

## Future Integrations

### Planned Scrapers

- **Netto**: Has online shop, similar structure to REMA 1000
- **Føtex**: Has online shop
- **Coop**: Different platform, may need HTML parsing
- **Lidl**: Has online shop in Denmark

### Alternative Data Sources

- **Open Food Facts**: Open database of food products
- **Recipe APIs**: Spoonacular, Edamam for recipes
- **Barcode APIs**: For product lookup by EAN

## Monitoring

### Metrics to Track

- Scrape success rate
- Products scraped per run
- Request latency
- Error rates by type

### Logging

All scrapers log to the standard logging system:

```python
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Scraped 500 products from REMA 1000")
```

### Health Checks

```python
scraper = Rema1000Scraper()
is_healthy = await scraper.health_check()
```

## Usage Examples

### Basic Product Scraping

```python
import asyncio
from foodplanner.ingest.scrapers import Rema1000Scraper

async def scrape_all_products():
    async with Rema1000Scraper() as scraper:
        # Scrape all products (may take a while)
        products = await scraper.scrape_products()
        print(f"Scraped {len(products)} products")
        return products

# Run the scraper
products = asyncio.run(scrape_all_products())
```

### Scraping with Limits

```python
async def scrape_sample():
    async with Rema1000Scraper() as scraper:
        # Scrape only 100 products
        products = await scraper.scrape_products(limit=100)

        # Scrape products from a specific category
        meat_products = await scraper.scrape_products(category="koed", limit=50)

        return products, meat_products
```

### Searching for Products

```python
async def search_products():
    async with Rema1000Scraper() as scraper:
        # Search for chicken products
        results = await scraper.search_products("kylling", limit=20)

        for product in results:
            print(f"{product['name']}: {product['price']} DKK")
```

### Getting Categories

```python
async def get_category_tree():
    async with Rema1000Scraper() as scraper:
        categories = await scraper.scrape_categories()

        # Print top-level categories
        for cat in categories:
            if cat.get('parent_id') is None:
                print(f"- {cat['name']}")
```

### Using the Factory Function

```python
from foodplanner.ingest.scrapers import get_scraper_for_store

async def scrape_store(store_id: str):
    scraper = get_scraper_for_store(store_id)
    if scraper is None:
        raise ValueError(f"No scraper available for {store_id}")

    async with scraper:
        return await scraper.scrape_products()

# Works with different store IDs
products = asyncio.run(scrape_store("rema1000"))
products = asyncio.run(scrape_store("rema1000-main"))
```

### Running the Daily Ingestion

```python
from foodplanner.ingest.batch_ingest import run_daily_ingestion

async def run_ingestion():
    result = await run_daily_ingestion(
        store_ids=["rema1000-main"],
        trigger_type="manual",
        force=True,  # Force even if already run today
    )
    print(f"Status: {result['status']}")
    print(f"Products updated: {result.get('products_updated', 0)}")

asyncio.run(run_ingestion())
```

## Data Flow

```
┌─────────────────┐
│  Grocery Store  │
│    Website      │
└────────┬────────┘
         │ HTTP GET (rate limited)
         ▼
┌─────────────────┐
│   Web Scraper   │
│ (Rema1000, etc) │
└────────┬────────┘
         │ ScrapedProduct objects
         ▼
┌─────────────────┐
│  Batch Ingest   │
│   Pipeline      │
└────────┬────────┘
         │ SQL INSERT/UPDATE
         ▼
┌─────────────────┐
│   PostgreSQL    │
│   (Products)    │
└────────┬────────┘
         │ Sync task
         ▼
┌─────────────────┐
│     Neo4j       │
│ (Knowledge Graph)│
└─────────────────┘
```

## Troubleshooting

### Common Issues

**Connection refused / Timeout**
- Check if the target website is accessible
- Increase timeout: `Rema1000Scraper(timeout=60.0)`
- Check for VPN/firewall issues

**Rate limited (429)**
- Increase delay: `Rema1000Scraper(rate_limit=2.0)`
- Reduce concurrent requests
- Schedule scraping during off-peak hours

**Empty results**
- Check if website structure has changed
- Verify category IDs are still valid
- Check scraper logs for parsing errors

**Invalid product data**
- Some fields may be missing from the API response
- Product schema validation logs warnings for skipped items
- Check `_parse_product()` method for edge cases

### Debug Mode

Enable detailed logging:

```python
import logging
logging.getLogger("foodplanner.ingest.scrapers").setLevel(logging.DEBUG)
```

### Checking Scraper Health

```python
async def check_all_scrapers():
    from foodplanner.ingest.scrapers import get_available_scrapers, get_scraper_for_store

    for brand in get_available_scrapers():
        scraper = get_scraper_for_store(brand)
        if scraper:
            async with scraper:
                is_healthy = await scraper.health_check()
                print(f"{brand}: {'OK' if is_healthy else 'FAILED'}")
```
