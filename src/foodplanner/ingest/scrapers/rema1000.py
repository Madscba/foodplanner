"""REMA 1000 web scraper for product data.

Scrapes product information from https://shop.rema1000.dk/
Uses Playwright to render the JavaScript-based SPA.
"""

import asyncio
import random
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from foodplanner.ingest.scrapers.base import BaseScraper, ScraperError
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)

# User agents for rotation (realistic Chrome/Firefox on Windows/Mac)
# fmt: off
USER_AGENTS = [
    # Chrome on Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ),
    # Chrome on Mac
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
    # Edge on Windows
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0"
    ),
]
# fmt: on

# Viewport sizes for variation (common desktop resolutions)
VIEWPORT_SIZES = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1280, "height": 720},
]


@dataclass
class ScrapeProgress:
    """Track progress of a full scrape operation."""

    categories_total: int = 0
    categories_completed: int = 0
    current_category: str = ""
    products_scraped: int = 0
    products_with_details: int = 0
    errors: list[str] = field(default_factory=list)
    is_cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "categories_total": self.categories_total,
            "categories_completed": self.categories_completed,
            "current_category": self.current_category,
            "products_scraped": self.products_scraped,
            "products_with_details": self.products_with_details,
            "errors": self.errors[:10],  # Limit errors in output
        }


class Rema1000Scraper(BaseScraper):
    """Scraper for REMA 1000 online shop.

    REMA 1000 uses a Vue.js SPA, so we need Playwright to render
    the JavaScript and extract product data from the DOM.

    Includes anti-blocking measures:
    - User-Agent rotation
    - Randomized delays between requests
    - Viewport size variation
    - Human-like scrolling behavior
    - Session persistence
    """

    BASE_URL = "https://shop.rema1000.dk"
    STORE_NAME = "REMA 1000"
    STORE_BRAND = "rema1000"

    # Category URL slugs for different sections
    # Based on actual REMA 1000 website navigation
    CATEGORY_SLUGS = {
        "avisvarer": "Avisvarer",
        "brod-bavinchi": "Brød & Bavinchi",
        "frugt-gront": "Frugt & Grønt",
        "nemt-hurtigt": "Nemt & Hurtigt",
        "kod-fisk-fjerkrae": "Kød, Fisk & Fjerkræ",
        "kol": "Køl",
        "ost-mv": "Ost m.v.",
        "frost": "Frost",
        "mejeri": "Mejeri",
        "kolonial": "Kolonial",
        "drikkevarer": "Drikkevarer",
        "husholdning": "Husholdning",
        "baby-og-smaborn": "Baby og Småbørn",
        "personlig-pleje": "Personlig Pleje",
        "slik": "Slik",
        "kiosk": "Kiosk",
    }

    def __init__(
        self,
        timeout: float | None = None,
        rate_limit: float | None = None,
        max_retries: int | None = None,
        headless: bool = True,
        # Anti-blocking settings
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        category_delay: float = 30.0,
        detail_min_delay: float = 1.0,
        detail_max_delay: float = 3.0,
        max_consecutive_errors: int = 5,
        backoff_factor: float = 2.0,
    ):
        """Initialize the scraper.

        Args:
            timeout: Request timeout in seconds.
            rate_limit: Minimum seconds between requests.
            max_retries: Maximum retry attempts for failed requests.
            headless: Whether to run browser in headless mode.
            min_delay: Minimum delay between page loads (seconds).
            max_delay: Maximum delay between page loads (seconds).
            category_delay: Delay between category scrapes (seconds).
            detail_min_delay: Minimum delay between product detail fetches.
            detail_max_delay: Maximum delay between product detail fetches.
            max_consecutive_errors: Max errors before circuit breaker trips.
            backoff_factor: Multiplier for exponential backoff.
        """
        super().__init__(timeout, rate_limit, max_retries)
        self.headless = headless
        self._browser: Browser | None = None
        self._playwright = None
        self._persistent_context: BrowserContext | None = None

        # Anti-blocking configuration
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.category_delay = category_delay
        self.detail_min_delay = detail_min_delay
        self.detail_max_delay = detail_max_delay
        self.max_consecutive_errors = max_consecutive_errors
        self.backoff_factor = backoff_factor

        # State tracking
        self._consecutive_errors = 0
        self._current_backoff = min_delay
        self._current_user_agent = random.choice(USER_AGENTS)
        self._current_viewport = random.choice(VIEWPORT_SIZES)

    def _get_headers(self) -> dict[str, str]:
        """Get headers for REMA 1000 requests with current user agent."""
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
            "User-Agent": self._current_user_agent,
        }

    def _rotate_identity(self) -> None:
        """Rotate user agent and viewport for anti-blocking."""
        self._current_user_agent = random.choice(USER_AGENTS)
        self._current_viewport = random.choice(VIEWPORT_SIZES)
        vp = self._current_viewport
        logger.debug(f"Rotated identity: viewport={vp['width']}x{vp['height']}")

    async def _random_delay(
        self,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
    ) -> None:
        """Wait for a random duration to mimic human behavior.

        Args:
            min_seconds: Minimum delay (defaults to self.min_delay).
            max_seconds: Maximum delay (defaults to self.max_delay).
        """
        min_s = min_seconds if min_seconds is not None else self.min_delay
        max_s = max_seconds if max_seconds is not None else self.max_delay
        delay = random.uniform(min_s, max_s)
        logger.debug(f"Waiting {delay:.2f}s")
        await asyncio.sleep(delay)

    async def _backoff_delay(self) -> None:
        """Apply exponential backoff delay after errors."""
        logger.warning(f"Applying backoff delay: {self._current_backoff:.2f}s")
        await asyncio.sleep(self._current_backoff)
        # Increase backoff for next time, cap at 5 minutes
        self._current_backoff = min(self._current_backoff * self.backoff_factor, 300)

    def _reset_backoff(self) -> None:
        """Reset backoff after successful operation."""
        self._current_backoff = self.min_delay
        self._consecutive_errors = 0

    def _record_error(self, error: str) -> bool:
        """Record an error and check if circuit breaker should trip.

        Args:
            error: Error description.

        Returns:
            True if should continue, False if circuit breaker tripped.
        """
        self._consecutive_errors += 1
        count = self._consecutive_errors
        max_err = self.max_consecutive_errors
        logger.warning(f"Error recorded ({count}/{max_err}): {error}")
        return self._consecutive_errors < self.max_consecutive_errors

    async def _get_browser(self) -> Browser:
        """Get or create Playwright browser instance."""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
        return self._browser

    async def close(self) -> None:
        """Close the browser and Playwright instance."""
        if self._persistent_context:
            await self._persistent_context.close()
            self._persistent_context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        await super().close()

    async def _get_persistent_context(self) -> BrowserContext:
        """Get or create a persistent browser context for session continuity."""
        if self._persistent_context is None:
            browser = await self._get_browser()
            self._persistent_context = await browser.new_context(
                locale="da-DK",
                user_agent=self._current_user_agent,
                viewport=self._current_viewport,
                # Accept cookies and enable JavaScript
                java_script_enabled=True,
                # Ignore HTTPS errors for development
                ignore_https_errors=True,
            )
            # Set extra headers
            await self._persistent_context.set_extra_http_headers(
                {
                    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
                }
            )
        return self._persistent_context

    async def _create_page(self, use_persistent: bool = False) -> Page:
        """Create a new browser page with appropriate settings.

        Args:
            use_persistent: If True, use persistent context for session continuity.

        Returns:
            New Playwright page.
        """
        if use_persistent:
            context = await self._get_persistent_context()
            return await context.new_page()

        browser = await self._get_browser()
        context = await browser.new_context(
            locale="da-DK",
            user_agent=self._current_user_agent,
            viewport=self._current_viewport,
        )
        return await context.new_page()

    async def _load_page_and_wait(self, page: Page, url: str) -> None:
        """Load a page and wait for products to render.

        Args:
            page: Playwright page instance.
            url: URL to load.
        """
        logger.debug(f"Loading {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Wait for product elements to appear
        try:
            await page.wait_for_selector(".product", timeout=15000)
            # Additional wait for dynamic content
            await asyncio.sleep(2)
        except Exception:
            logger.warning(f"No products found on page: {url}")

    async def _scroll_page(self, page: Page, scroll_pause: float = 0.5) -> None:
        """Scroll down the page to trigger lazy loading and appear human-like.

        Args:
            page: Playwright page instance.
            scroll_pause: Pause between scroll actions.
        """
        # Get page height
        scroll_height = await page.evaluate("document.body.scrollHeight")
        viewport_height = self._current_viewport["height"]

        current_position = 0
        while current_position < scroll_height:
            # Scroll by a random amount (60-90% of viewport)
            scroll_amount = int(viewport_height * random.uniform(0.6, 0.9))
            current_position += scroll_amount

            await page.evaluate(f"window.scrollTo(0, {current_position})")
            await asyncio.sleep(scroll_pause + random.uniform(0, 0.3))

            # Update scroll height in case lazy loading added content
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height > scroll_height:
                scroll_height = new_height

        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.3)

    async def _handle_cookie_consent(self, page: Page) -> None:
        """Handle cookie consent dialogs if present.

        Args:
            page: Playwright page instance.
        """
        try:
            # Common cookie consent button selectors
            consent_selectors = [
                "button[id*='accept']",
                "button[class*='accept']",
                "button[class*='cookie']",
                "[data-testid='cookie-accept']",
                ".cookie-consent button",
                "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            ]

            for selector in consent_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button and await button.is_visible():
                        await button.click()
                        logger.debug(f"Clicked cookie consent button: {selector}")
                        await asyncio.sleep(1)
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"No cookie consent dialog found or error: {e}")

    async def _load_all_products_in_category(self, page: Page) -> int:
        """Scroll and load all products in a category page.

        REMA 1000 uses infinite scroll or "load more" patterns.

        Args:
            page: Playwright page with category loaded.

        Returns:
            Total number of products loaded.
        """
        previous_count = 0
        stable_count = 0
        max_stable_iterations = 3

        while stable_count < max_stable_iterations:
            # Count current products
            current_count = await page.evaluate("document.querySelectorAll('.product').length")

            if current_count == previous_count:
                stable_count += 1
            else:
                stable_count = 0
                previous_count = current_count

            # Scroll to bottom to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5 + random.uniform(0, 0.5))

            # Check for "load more" button
            load_more = await page.query_selector(
                "button[class*='load-more'], button[class*='show-more'], .load-more"
            )
            if load_more and await load_more.is_visible():
                try:
                    await load_more.click()
                    await asyncio.sleep(2)
                    stable_count = 0  # Reset since we loaded more
                except Exception:
                    pass

        logger.info(f"Loaded {previous_count} products in category")
        return previous_count

    async def _extract_products_from_page(self, page: Page) -> list[dict[str, Any]]:
        """Extract product data from the current page.

        Args:
            page: Playwright page with loaded content.

        Returns:
            List of product dictionaries.
        """
        products = await page.evaluate("""
            () => {
                const products = [];
                const productElements = document.querySelectorAll('.product');

                for (const el of productElements) {
                    try {
                        // Extract image URL and product ID
                        const img = el.querySelector('img');
                        const imgSrc = img ? img.src : '';

                        // Extract product ID from image URL
                        // Format: .../item/{ID}/image/...
                        const idMatch = imgSrc.match(/\\/item\\/(\\d+)\\//);
                        const productId = idMatch ? idMatch[1] : '';

                        // Extract price (format: "1500" meaning 15.00 kr)
                        const priceEl = el.querySelector('.price-normal');
                        let priceText = priceEl ? priceEl.textContent : '';
                        // Remove any non-numeric characters and convert from øre to kroner
                        const priceMatch = priceText.replace(/[^0-9]/g, '');
                        const price = priceMatch ? parseInt(priceMatch, 10) / 100 : 0;

                        // Extract price per unit
                        const pricePerUnitEl = el.querySelector('.price-per-unit');
                        const pricePerUnit = pricePerUnitEl
                            ? pricePerUnitEl.textContent.trim() : '';

                        // Extract title
                        const titleEl = el.querySelector('.title');
                        const title = titleEl ? titleEl.textContent.trim() : '';

                        // Extract extra info (unit, origin)
                        const extraEl = el.querySelector('.extra');
                        const extra = extraEl ? extraEl.textContent.trim() : '';

                        // Check if it's a discount/offer item
                        const isOffer = el.querySelector('.avisvare') !== null;

                        if (productId && title) {
                            products.push({
                                id: productId,
                                name: title,
                                price: price,
                                price_per_unit: pricePerUnit,
                                extra_info: extra,
                                image_url: imgSrc,
                                is_offer: isOffer,
                            });
                        }
                    } catch (e) {
                        console.error('Error parsing product:', e);
                    }
                }

                return products;
            }
        """)

        return [self._normalize_product(p) for p in products if p]

    def _normalize_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize raw product data to standard format.

        Args:
            raw: Raw product data from page extraction.

        Returns:
            Normalized product dictionary.
        """
        # Parse unit from extra_info (format: "750 GR. / GILLELEJE HAVN")
        extra_info = raw.get("extra_info", "")
        unit = ""
        origin = ""

        if "/" in extra_info:
            parts = extra_info.split("/")
            unit = parts[0].strip()
            origin = parts[1].strip() if len(parts) > 1 else ""
        else:
            unit = extra_info

        # Parse unit from price_per_unit if not found (format: "20.00 per Kg.")
        price_per_unit = raw.get("price_per_unit", "")
        unit_from_price = ""
        if "per" in price_per_unit.lower():
            unit_match = re.search(r"per\s+(\w+)", price_per_unit, re.IGNORECASE)
            if unit_match:
                unit_from_price = unit_match.group(1)

        return {
            "id": raw.get("id", ""),
            "name": raw.get("name", ""),
            "price": raw.get("price", 0.0),
            "unit": unit or unit_from_price,
            "ean": None,  # Not available in HTML
            "category": None,  # Set by caller based on page
            "subcategory": None,
            "brand": None,  # Not directly available in listing
            "image_url": raw.get("image_url"),
            "description": extra_info,
            "ingredients": None,
            "nutrition_info": None,
            "origin": origin if origin else None,
            "url": f"{self.BASE_URL}/produkt/{raw.get('id', '')}",
            "is_offer": raw.get("is_offer", False),
        }

    async def scrape_categories(self) -> list[dict[str, Any]]:
        """Scrape product categories from REMA 1000.

        Returns:
            List of category dictionaries.
        """
        categories = []
        for slug, name in self.CATEGORY_SLUGS.items():
            categories.append(
                {
                    "id": slug,
                    "name": name,
                    "slug": slug,
                    "parent_id": None,
                    "url": f"{self.BASE_URL}/{slug}",
                }
            )

        logger.info(f"Returning {len(categories)} predefined categories")
        return categories

    async def scrape_products(
        self,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Scrape products from REMA 1000.

        Args:
            category: Optional category slug to filter (e.g., "frugt-og-gront").
            limit: Maximum number of products to scrape (None = all on page).

        Returns:
            List of product dictionaries.
        """
        page = None
        try:
            page = await self._create_page()

            # Determine URL based on category
            if category:
                url = f"{self.BASE_URL}/{category}"
                category_name = self.CATEGORY_SLUGS.get(category, category)
            else:
                url = self.BASE_URL
                category_name = None

            logger.info(f"Scraping products from {url} (limit={limit})")

            await self._load_page_and_wait(page, url)

            products = await self._extract_products_from_page(page)

            # Set category on products
            for product in products:
                product["category"] = category_name

            # Apply limit
            if limit and len(products) > limit:
                products = products[:limit]

            logger.info(f"Scraped {len(products)} products from REMA 1000")
            return products

        except Exception as e:
            logger.error(f"Failed to scrape products: {e}")
            raise ScraperError(f"Failed to scrape products: {e}") from e

        finally:
            if page:
                await page.context.close()

    async def scrape_product_details(
        self,
        product_id: str,
        page: Page | None = None,
    ) -> dict[str, Any] | None:
        """Scrape detailed information for a specific product.

        Navigates to the product detail page to extract additional info
        like description, ingredients, and nutrition facts.

        Args:
            product_id: The REMA 1000 product ID.
            page: Optional existing page to reuse.

        Returns:
            Product details dictionary or None if not found.
        """
        own_page = page is None
        try:
            if own_page:
                page = await self._create_page(use_persistent=True)

            url = f"{self.BASE_URL}/produkt/{product_id}"
            logger.debug(f"Fetching product details: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for product content
            try:
                await page.wait_for_selector(".product-detail, .product-page", timeout=10000)
            except Exception:
                logger.warning(f"Product detail page not found for {product_id}")
                return None

            # Extract detailed product information
            # fmt: off
            details = await page.evaluate("""
                () => {
                    const result = {
                        description: '',
                        ingredients: '',
                        nutrition_info: {},
                        brand: '',
                        ean: '',
                    };
                    const descSel = '.product-description, .description, [class*="description"]';
                    const descEl = document.querySelector(descSel);
                    if (descEl) {
                        result.description = descEl.textContent.trim();
                    }
                    const ingredientsSel = '.ingredients, [class*="ingredients"]';
                    const ingredientsEl = document.querySelector(ingredientsSel);
                    if (ingredientsEl) {
                        result.ingredients = ingredientsEl.textContent.trim();
                    }
                    const nutritionSel = '.nutrition, .nutrition-table, [class*="nutrition"]';
                    const nutritionEl = document.querySelector(nutritionSel);
                    if (nutritionEl) {
                        const rows = nutritionEl.querySelectorAll('tr, .nutrition-row');
                        rows.forEach(row => {
                            const cells = row.querySelectorAll('td, span');
                            if (cells.length >= 2) {
                                const key = cells[0].textContent.trim().toLowerCase();
                                const value = cells[1].textContent.trim();
                                if (key && value) {
                                    result.nutrition_info[key] = value;
                                }
                            }
                        });
                    }
                    const brandEl = document.querySelector('.brand, [class*="brand"]');
                    if (brandEl) {
                        result.brand = brandEl.textContent.trim();
                    }
                    const eanEl = document.querySelector('[class*="ean"], [class*="barcode"]');
                    if (eanEl) {
                        const eanMatch = eanEl.textContent.match(/\\d{8,13}/);
                        if (eanMatch) {
                            result.ean = eanMatch[0];
                        }
                    }
                    return result;
                }
            """)
            # fmt: on

            self._reset_backoff()
            return details

        except Exception as e:
            logger.warning(f"Failed to scrape product details for {product_id}: {e}")
            if not self._record_error(str(e)):
                max_err = self.max_consecutive_errors
                raise ScraperError(f"Circuit breaker tripped after {max_err} errors") from e
            return None

        finally:
            if own_page and page:
                await page.context.close()

    async def search_products(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search for products by name.

        Note: REMA 1000 doesn't have a public search API, so this searches
        by scraping products and filtering locally.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching product dictionaries.
        """
        page = None
        try:
            page = await self._create_page()

            # Load homepage with all products
            await self._load_page_and_wait(page, self.BASE_URL)

            all_products = await self._extract_products_from_page(page)

            # Filter by query (case-insensitive)
            query_lower = query.lower()
            matching = [
                p
                for p in all_products
                if query_lower in p.get("name", "").lower()
                or query_lower in p.get("description", "").lower()
            ]

            logger.info(f"Search for '{query}' found {len(matching)} matches")
            return matching[:limit]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise ScraperError(f"Search failed: {e}") from e

        finally:
            if page:
                await page.context.close()

    async def scrape_category_products_full(
        self,
        category_slug: str,
        include_details: bool = True,
        progress: ScrapeProgress | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Scrape all products in a category with pagination and optional details.

        This method handles infinite scroll/pagination to get ALL products
        in a category, not just the first page.

        Args:
            category_slug: Category URL slug (e.g., "frugt-gront").
            include_details: If True, fetch full details for each product.
            progress: Optional progress tracker to update.

        Yields:
            Product dictionaries with full data.
        """
        page = None
        try:
            page = await self._create_page(use_persistent=True)
            url = f"{self.BASE_URL}/{category_slug}"
            category_name = self.CATEGORY_SLUGS.get(category_slug, category_slug)

            logger.info(f"Starting full scrape of category: {category_name}")

            # Load category page
            await self._load_page_and_wait(page, url)

            # Handle cookie consent on first visit
            await self._handle_cookie_consent(page)

            # Load all products via infinite scroll
            await self._load_all_products_in_category(page)

            # Extract all products from the fully loaded page
            products = await self._extract_products_from_page(page)
            logger.info(f"Found {len(products)} products in {category_name}")

            # Set category on all products
            for product in products:
                product["category"] = category_name

            if progress:
                progress.products_scraped += len(products)

            # Fetch details for each product if requested
            if include_details:
                for i, product in enumerate(products):
                    if progress and progress.is_cancelled:
                        logger.info("Scrape cancelled by user")
                        return

                    try:
                        # Random delay before fetching details
                        await self._random_delay(self.detail_min_delay, self.detail_max_delay)

                        details = await self.scrape_product_details(product["id"], page)
                        if details:
                            # Merge details into product
                            desc = details.get("description") or product.get("description")
                            product.update(
                                {
                                    "description": desc,
                                    "ingredients": details.get("ingredients"),
                                    "nutrition_info": details.get("nutrition_info"),
                                    "brand": details.get("brand") or product.get("brand"),
                                    "ean": details.get("ean") or product.get("ean"),
                                }
                            )
                            if progress:
                                progress.products_with_details += 1

                        self._reset_backoff()

                    except ScraperError:
                        # Circuit breaker tripped
                        raise
                    except Exception as e:
                        error_msg = f"Failed to get details for {product['id']}: {e}"
                        logger.warning(error_msg)
                        if progress:
                            progress.errors.append(error_msg)
                        # Continue with other products

                    yield product

                    # Log progress periodically
                    if (i + 1) % 50 == 0:
                        total = len(products)
                        logger.info(f"Processed {i + 1}/{total} products in {category_name}")
            else:
                # Yield all products without details
                for product in products:
                    yield product

        except Exception as e:
            error_msg = f"Failed to scrape category {category_slug}: {e}"
            logger.error(error_msg)
            if progress:
                progress.errors.append(error_msg)
            if not self._record_error(str(e)):
                raise ScraperError(f"Circuit breaker tripped: {e}") from e

        finally:
            # Don't close page if using persistent context
            pass

    async def scrape_all_products(
        self,
        include_details: bool = True,
        categories: list[str] | None = None,
        progress_callback: Callable[[ScrapeProgress], None] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Scrape all products from all categories with full details.

        This is the main entry point for a full store scrape. It iterates
        through all categories, handles pagination, and optionally fetches
        detailed product information.

        Anti-blocking measures are applied:
        - Random delays between requests
        - Longer delays between categories
        - User-Agent rotation between categories
        - Human-like scrolling behavior
        - Circuit breaker on consecutive errors

        Args:
            include_details: If True, fetch full details for each product.
            categories: Optional list of category slugs to scrape.
                        If None, scrapes all categories.
            progress_callback: Optional callback for progress updates.

        Yields:
            Product dictionaries with full data.

        Raises:
            ScraperError: If circuit breaker trips due to too many errors.
        """
        progress = ScrapeProgress()
        category_slugs = categories or list(self.CATEGORY_SLUGS.keys())
        progress.categories_total = len(category_slugs)

        logger.info(f"Starting full scrape of {len(category_slugs)} categories")

        try:
            for i, category_slug in enumerate(category_slugs):
                if progress.is_cancelled:
                    logger.info("Full scrape cancelled")
                    return

                progress.current_category = category_slug

                # Rotate identity between categories for anti-blocking
                if i > 0:
                    self._rotate_identity()
                    # Close and recreate persistent context with new identity
                    if self._persistent_context:
                        await self._persistent_context.close()
                        self._persistent_context = None

                logger.info(f"Scraping category {i + 1}/{len(category_slugs)}: {category_slug}")

                # Scrape this category
                async for product in self.scrape_category_products_full(
                    category_slug=category_slug,
                    include_details=include_details,
                    progress=progress,
                ):
                    yield product

                progress.categories_completed += 1

                # Report progress
                if progress_callback:
                    progress_callback(progress)

                # Long delay between categories
                if i < len(category_slugs) - 1:
                    delay = self.category_delay + random.uniform(0, 10)
                    logger.info(f"Waiting {delay:.1f}s before next category")
                    await asyncio.sleep(delay)

            logger.info(
                f"Full scrape completed: {progress.categories_completed} categories, "
                f"{progress.products_scraped} products, "
                f"{progress.products_with_details} with details, "
                f"{len(progress.errors)} errors"
            )

        finally:
            # Final progress report
            if progress_callback:
                progress_callback(progress)

    def cancel_scrape(self, progress: ScrapeProgress) -> None:
        """Cancel an ongoing scrape operation.

        Args:
            progress: The progress object for the scrape to cancel.
        """
        progress.is_cancelled = True
        logger.info("Scrape cancellation requested")

    async def health_check(self) -> bool:
        """Check if the scraper can reach the REMA 1000 website.

        Returns:
            True if healthy, False otherwise.
        """
        page = None
        try:
            page = await self._create_page()
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=15000)
            title = await page.title()
            return "REMA" in title.upper()
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
        finally:
            if page:
                await page.context.close()

    async def __aenter__(self) -> "Rema1000Scraper":
        """Async context manager entry."""
        await self._get_browser()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
