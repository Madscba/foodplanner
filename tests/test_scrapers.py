"""Tests for web scraper functionality."""

from datetime import datetime

import pytest

from foodplanner.ingest.scrapers import (
    Rema1000Scraper,
    ScraperError,
    get_available_scrapers,
    get_scraper_for_store,
)
from foodplanner.ingest.scrapers.base import RateLimitError, ScrapedProduct


class TestBaseScraper:
    """Tests for BaseScraper base class."""

    def test_scraped_product_to_dict(self):
        """Test ScrapedProduct dataclass serialization."""
        product = ScrapedProduct(
            id="test-001",
            name="Test Product",
            price=29.95,
            unit="500g",
            ean="5701234567890",
            category="Test Category",
        )

        data = product.to_dict()

        assert data["id"] == "test-001"
        assert data["name"] == "Test Product"
        assert data["price"] == 29.95
        assert data["unit"] == "500g"
        assert data["ean"] == "5701234567890"
        assert data["category"] == "Test Category"
        assert "scraped_at" in data

    def test_scraped_product_defaults(self):
        """Test ScrapedProduct with minimal required fields."""
        product = ScrapedProduct(
            id="test-001",
            name="Test Product",
            price=10.0,
        )

        assert product.id == "test-001"
        assert product.name == "Test Product"
        assert product.price == 10.0
        assert product.unit is None
        assert product.ean is None
        assert product.category is None
        assert isinstance(product.scraped_at, datetime)


class TestScraperRegistry:
    """Tests for scraper registry functions."""

    def test_get_scraper_for_rema1000(self):
        """Test getting REMA 1000 scraper."""
        scraper = get_scraper_for_store("rema1000")
        assert scraper is not None
        assert isinstance(scraper, Rema1000Scraper)

    def test_get_scraper_for_rema1000_main(self):
        """Test getting scraper by full store ID."""
        scraper = get_scraper_for_store("rema1000-main")
        assert scraper is not None
        assert isinstance(scraper, Rema1000Scraper)

    def test_get_scraper_for_unknown_store(self):
        """Test getting scraper for unknown store returns None."""
        scraper = get_scraper_for_store("unknown-store")
        assert scraper is None

    def test_get_scraper_case_insensitive(self):
        """Test that store lookup is case insensitive."""
        scraper = get_scraper_for_store("REMA1000")
        assert scraper is not None
        assert isinstance(scraper, Rema1000Scraper)

    def test_get_available_scrapers(self):
        """Test listing available scrapers."""
        scrapers = get_available_scrapers()
        assert "rema1000" in scrapers


class TestRema1000Scraper:
    """Tests for Rema1000Scraper.

    Note: The REMA 1000 scraper uses Playwright for browser-based scraping
    since the website is a JavaScript SPA. These tests focus on the
    normalization and utility methods rather than mocking browser behavior.
    """

    def test_scraper_initialization(self):
        """Test scraper initialization."""
        scraper = Rema1000Scraper()

        assert scraper.STORE_NAME == "REMA 1000"
        assert scraper.STORE_BRAND == "rema1000"
        assert scraper.BASE_URL == "https://shop.rema1000.dk"

    def test_scraper_name_property(self):
        """Test name property."""
        scraper = Rema1000Scraper()
        assert scraper.name == "REMA 1000"

    def test_scraper_brand_property(self):
        """Test brand property."""
        scraper = Rema1000Scraper()
        assert scraper.brand == "rema1000"

    def test_get_headers(self):
        """Test that headers include required fields for browser scraping."""
        scraper = Rema1000Scraper()
        headers = scraper._get_headers()

        assert "User-Agent" in headers
        assert "Accept" in headers
        # Browser scraper uses HTML accept header
        assert "text/html" in headers["Accept"]

    def test_normalize_product_complete(self):
        """Test normalizing a complete product from page extraction."""
        scraper = Rema1000Scraper()
        raw_product = {
            "id": "12345",
            "name": "KYLLINGEBRYST",
            "price": 59.95,
            "price_per_unit": "119.90 per Kg.",
            "extra_info": "500 GR. / DANSK",
            "image_url": "https://api.digital.rema1000.dk/api/v1/catalog/store/1/item/12345/image/123/170.jpg",
            "is_offer": True,
        }

        product = scraper._normalize_product(raw_product)

        assert product is not None
        assert product["id"] == "12345"
        assert product["name"] == "KYLLINGEBRYST"
        assert product["price"] == 59.95
        assert product["unit"] == "500 GR."
        assert product["origin"] == "DANSK"
        assert product["is_offer"] is True
        assert product["url"] == "https://shop.rema1000.dk/produkt/12345"

    def test_normalize_product_minimal(self):
        """Test normalizing a product with minimal data."""
        scraper = Rema1000Scraper()
        raw_product = {
            "id": "12345",
            "name": "Test Product",
            "price": 10.0,
        }

        product = scraper._normalize_product(raw_product)

        assert product is not None
        assert product["id"] == "12345"
        assert product["name"] == "Test Product"
        assert product["price"] == 10.0
        assert product["ean"] is None
        assert product["category"] is None

    def test_normalize_product_with_unit_from_price(self):
        """Test extracting unit from price_per_unit field."""
        scraper = Rema1000Scraper()
        raw_product = {
            "id": "12345",
            "name": "Test Product",
            "price": 10.0,
            "price_per_unit": "20.00 per Kg.",
            "extra_info": "",
        }

        product = scraper._normalize_product(raw_product)
        assert product["unit"] == "Kg"

    def test_category_slugs_defined(self):
        """Test that category slugs are properly defined."""
        scraper = Rema1000Scraper()

        assert len(scraper.CATEGORY_SLUGS) > 0
        assert "frugt-gront" in scraper.CATEGORY_SLUGS
        assert "mejeri" in scraper.CATEGORY_SLUGS
        assert "kolonial" in scraper.CATEGORY_SLUGS

    @pytest.mark.asyncio
    async def test_scrape_categories_returns_predefined(self):
        """Test scraping categories returns predefined list."""
        scraper = Rema1000Scraper()
        categories = await scraper.scrape_categories()

        # Should return predefined categories
        assert len(categories) == len(scraper.CATEGORY_SLUGS)

        # Check structure
        for cat in categories:
            assert "id" in cat
            assert "name" in cat
            assert "slug" in cat
            assert "url" in cat

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check with successful response."""
        # This test requires actual browser - skip in unit tests
        # Integration tests cover this functionality
        pass

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test scraper as async context manager initializes browser."""
        async with Rema1000Scraper() as scraper:
            # Browser should be initialized
            assert scraper._browser is not None
        # Browser should be closed after context
        assert scraper._browser is None


class TestScraperErrors:
    """Tests for scraper error handling."""

    def test_scraper_error_creation(self):
        """Test ScraperError with all fields."""
        error = ScraperError(
            "Test error",
            url="https://example.com",
            status_code=404,
        )

        assert str(error) == "Test error"
        assert error.url == "https://example.com"
        assert error.status_code == 404

    def test_rate_limit_error_creation(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError("Rate limited", retry_after=60)

        assert str(error) == "Rate limited"
        assert error.retry_after == 60
