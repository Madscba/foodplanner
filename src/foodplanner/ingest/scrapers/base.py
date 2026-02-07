"""Base scraper interface for grocery store websites."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from foodplanner.config import get_settings
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


class ScraperError(Exception):
    """Base exception for scraper errors."""

    def __init__(self, message: str, url: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class RateLimitError(ScraperError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class ScrapedProduct:
    """Product data scraped from a grocery store website."""

    id: str
    name: str
    price: float
    unit: str | None = None
    ean: str | None = None
    category: str | None = None
    subcategory: str | None = None
    brand: str | None = None
    image_url: str | None = None
    description: str | None = None
    ingredients: str | None = None
    nutrition_info: dict[str, Any] | None = None
    origin: str | None = None
    url: str | None = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "unit": self.unit,
            "ean": self.ean,
            "category": self.category,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "image_url": self.image_url,
            "description": self.description,
            "ingredients": self.ingredients,
            "nutrition_info": self.nutrition_info,
            "origin": self.origin,
            "url": self.url,
            "scraped_at": self.scraped_at.isoformat(),
        }


class BaseScraper(ABC):
    """Abstract base class for grocery store scrapers.

    Provides common functionality for HTTP requests, rate limiting,
    retry logic, and error handling.
    """

    # Override in subclasses
    BASE_URL: str = ""
    STORE_NAME: str = "Unknown"
    STORE_BRAND: str = "unknown"

    # Configuration
    DEFAULT_TIMEOUT: float = 30.0
    MAX_RETRIES: int = 3
    RATE_LIMIT_DELAY: float = 1.0  # seconds between requests

    def __init__(
        self,
        timeout: float | None = None,
        rate_limit: float | None = None,
        max_retries: int | None = None,
    ):
        """
        Initialize the scraper.

        Args:
            timeout: Request timeout in seconds.
            rate_limit: Minimum seconds between requests.
            max_retries: Maximum retry attempts for failed requests.
        """
        self.timeout = timeout or settings.scraping_timeout or self.DEFAULT_TIMEOUT
        self.rate_limit = rate_limit or settings.scraping_rate_limit or self.RATE_LIMIT_DELAY
        self.max_retries = max_retries or settings.scraping_max_retries or self.MAX_RETRIES
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0

    @property
    def name(self) -> str:
        """Return scraper/store name."""
        return self.STORE_NAME

    @property
    def brand(self) -> str:
        """Return store brand identifier."""
        return self.STORE_BRAND

    def _get_headers(self) -> dict[str, str]:
        """Get default request headers.

        Override in subclasses if custom headers are needed.
        """
        return {
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers=self._get_headers(),
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _rate_limit_wait(self) -> None:
        """Wait to respect rate limiting."""
        import time

        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit:
            await asyncio.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an HTTP request with rate limiting and retry logic.

        Args:
            method: HTTP method.
            url: Full URL to request.
            params: Query parameters.
            headers: Additional headers to merge with defaults.
            **kwargs: Additional arguments for httpx.

        Returns:
            httpx.Response object.

        Raises:
            ScraperError: If request fails after retries.
        """
        await self._rate_limit_wait()

        client = await self._get_client()
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)

        @retry(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, max=30),
            reraise=True,
        )
        async def _do_request() -> httpx.Response:
            return await client.request(
                method, url, params=params, headers=request_headers, **kwargs
            )

        try:
            response = await _do_request()
        except RetryError as e:
            logger.error(f"Request failed after {self.max_retries} retries: {url}")
            raise ScraperError(
                f"Request failed after {self.max_retries} retries",
                url=url,
            ) from e

        # Handle rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after else 60
            raise RateLimitError(
                f"Rate limit exceeded for {url}",
                retry_after=wait_seconds,
            )

        # Handle errors
        if response.status_code >= 400:
            error_detail = response.text[:500] if response.text else "No details"
            logger.error(f"Request error {response.status_code} for {url}: {error_detail}")
            raise ScraperError(
                f"Request failed with status {response.status_code}",
                url=url,
                status_code=response.status_code,
            )

        return response

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a GET request."""
        return await self._request("GET", url, params=params, **kwargs)

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request and parse JSON response."""
        response = await self.get(url, params=params, **kwargs)
        return response.json()

    @abstractmethod
    async def scrape_products(
        self,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Scrape product data from the store website.

        Args:
            category: Optional category to filter products.
            limit: Maximum number of products to scrape.

        Returns:
            List of product dictionaries.
        """
        pass

    @abstractmethod
    async def scrape_categories(self) -> list[dict[str, Any]]:
        """
        Scrape available product categories.

        Returns:
            List of category dictionaries with id, name, and optional parent.
        """
        pass

    async def scrape_product_details(self, product_id: str) -> dict[str, Any] | None:
        """
        Scrape detailed information for a specific product.

        Args:
            product_id: The product identifier.

        Returns:
            Product details dictionary or None if not found.
        """
        # Default implementation - subclasses can override
        return None

    async def health_check(self) -> bool:
        """
        Check if the scraper can reach the target website.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = await self.get(self.BASE_URL)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for {self.STORE_NAME}: {e}")
            return False

    async def __aenter__(self) -> "BaseScraper":
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
