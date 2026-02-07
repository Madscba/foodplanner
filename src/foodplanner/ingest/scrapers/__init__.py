"""Web scrapers for grocery store product data.

This module provides a scalable architecture for scraping product data
from various grocery store websites.
"""

from foodplanner.ingest.scrapers.base import BaseScraper, ScraperError
from foodplanner.ingest.scrapers.rema1000 import Rema1000Scraper, ScrapeProgress

__all__ = [
    "BaseScraper",
    "ScraperError",
    "Rema1000Scraper",
    "ScrapeProgress",
    "get_scraper_for_store",
    "get_available_scrapers",
]

# Registry of available scrapers by store brand/id
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    "rema1000": Rema1000Scraper,
    "rema1000-main": Rema1000Scraper,
}


def get_scraper_for_store(store_id: str) -> BaseScraper | None:
    """
    Get the appropriate scraper for a store.

    Args:
        store_id: The store identifier or brand name.

    Returns:
        A scraper instance or None if no scraper is available.
    """
    # Try direct match first
    scraper_class = SCRAPER_REGISTRY.get(store_id.lower())

    # Try extracting brand from store_id
    if not scraper_class:
        for brand, cls in SCRAPER_REGISTRY.items():
            if brand in store_id.lower():
                scraper_class = cls
                break

    if scraper_class:
        return scraper_class()

    return None


def get_available_scrapers() -> list[str]:
    """Get list of available scraper brands."""
    return list(set(SCRAPER_REGISTRY.keys()))
