"""Base connector interface for store integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class ConnectorResponse:
    """Standardized response from connector API calls."""

    data: Any
    status_code: int
    headers: dict[str, str]
    raw_response: dict[str, Any] | list[Any] | None = None

    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return 200 <= self.status_code < 300

    @property
    def is_rate_limited(self) -> bool:
        """Check if response indicates rate limiting."""
        return self.status_code == 429

    @property
    def retry_after(self) -> int | None:
        """Get retry-after seconds from headers, if present."""
        retry_after = self.headers.get("retry-after") or self.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                return None
        return None


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ConnectorError(Exception):
    """Base exception for connector errors."""

    def __init__(self, message: str, status_code: int | None = None, response: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class StoreConnector(ABC):
    """Abstract base class for store API connectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return connector name for logging and identification."""
        pass

    @abstractmethod
    async def get_stores(
        self,
        zip_code: str | None = None,
        brand: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Fetch available stores, optionally filtered.

        Args:
            zip_code: Filter by zip code/postal code.
            brand: Filter by store brand.
            limit: Maximum number of stores to return.

        Returns:
            List of store dictionaries.
        """
        pass

    @abstractmethod
    async def get_discounts(
        self, store_id: str, start_date: date, end_date: date
    ) -> ConnectorResponse:
        """
        Fetch discount offers for a date range.

        Args:
            store_id: The store identifier.
            start_date: Start of date range.
            end_date: End of date range.

        Returns:
            ConnectorResponse with offer data.
        """
        pass

    @abstractmethod
    async def search_products(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Search for products by name or category.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of product dictionaries.
        """
        pass

    @abstractmethod
    async def get_product_details(self, product_id: str) -> dict[str, Any]:
        """
        Get detailed information for a specific product.

        Args:
            product_id: The product identifier.

        Returns:
            Product details dictionary.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the connector can reach its API.

        Returns:
            True if healthy, False otherwise.
        """
        pass
