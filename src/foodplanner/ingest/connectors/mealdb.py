"""TheMealDB API connector for recipe data."""

import asyncio
from dataclasses import dataclass
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
from foodplanner.ingest.connectors.base import ConnectorError, ConnectorResponse
from foodplanner.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MealIngredient:
    """Parsed ingredient from a meal."""

    name: str
    measure: str

    @property
    def normalized_name(self) -> str:
        """Get normalized ingredient name for matching."""
        return self.name.lower().strip()


@dataclass
class ParsedMeal:
    """Structured meal data parsed from API response."""

    id: str
    name: str
    category: str | None
    area: str | None
    instructions: str
    thumbnail: str | None
    tags: list[str]
    youtube_url: str | None
    source_url: str | None
    ingredients: list[MealIngredient]

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "ParsedMeal":
        """Parse meal from TheMealDB API response format."""
        # Extract ingredients (strIngredient1-20 and strMeasure1-20)
        ingredients = []
        for i in range(1, 21):
            ingredient = data.get(f"strIngredient{i}")
            measure = data.get(f"strMeasure{i}")

            # Skip empty ingredients
            if ingredient and ingredient.strip():
                ingredients.append(
                    MealIngredient(
                        name=ingredient.strip(),
                        measure=(measure or "").strip(),
                    )
                )

        # Parse tags
        tags_str = data.get("strTags") or ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        return cls(
            id=data.get("idMeal", ""),
            name=data.get("strMeal", "Unknown Meal"),
            category=data.get("strCategory"),
            area=data.get("strArea"),
            instructions=data.get("strInstructions", ""),
            thumbnail=data.get("strMealThumb"),
            tags=tags,
            youtube_url=data.get("strYoutube"),
            source_url=data.get("strSource"),
            ingredients=ingredients,
        )


class MealDBConnector:
    """Connector for TheMealDB API."""

    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 3
    BACKOFF_BASE = 1
    BACKOFF_MAX = 30
    # TheMealDB has no documented rate limits for the test API
    REQUEST_DELAY = 0.1  # Small delay between requests to be polite

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.mealdb_api_key
        self.base_url = base_url or f"{settings.mealdb_base_url}/{self.api_key}"
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0

    @property
    def name(self) -> str:
        """Return connector name."""
        return "mealdb"

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Foodplanner/1.0",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _throttle(self) -> None:
        """Apply rate limiting between requests."""
        import time

        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            await asyncio.sleep(self.REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> ConnectorResponse:
        """Make an HTTP request with retry logic."""
        await self._throttle()

        url = f"{self.base_url}/{endpoint}"
        client = await self._get_client()

        @retry(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            stop=stop_after_attempt(self.MAX_RETRIES),
            wait=wait_exponential(multiplier=self.BACKOFF_BASE, max=self.BACKOFF_MAX),
            reraise=True,
        )
        async def _do_request() -> httpx.Response:
            return await client.get(url, params=params)

        try:
            response = await _do_request()
        except RetryError as e:
            logger.error(f"Request failed after {self.MAX_RETRIES} retries: {url}")
            raise ConnectorError(
                f"Request failed after {self.MAX_RETRIES} retries",
                response=str(e),
            ) from e

        if response.status_code >= 400:
            error_detail = response.text[:500] if response.text else "No details"
            logger.error(f"API error {response.status_code} for {url}: {error_detail}")
            raise ConnectorError(
                f"API request failed with status {response.status_code}",
                status_code=response.status_code,
                response=error_detail,
            )

        try:
            data = response.json() if response.text else {}
        except Exception as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            data = {}

        return ConnectorResponse(
            data=data,
            status_code=response.status_code,
            headers=dict(response.headers),
            raw_response=data,
        )

    async def get_categories(self) -> list[dict[str, Any]]:
        """
        Fetch all meal categories.

        Returns:
            List of category dictionaries with id, name, thumb, description.
        """
        logger.info("Fetching meal categories")
        response = await self._request("categories.php")

        categories = response.data.get("categories", [])
        logger.info(f"Fetched {len(categories)} categories")
        return categories

    async def get_areas(self) -> list[str]:
        """
        Fetch all cuisine areas/regions.

        Returns:
            List of area names (e.g., "Italian", "Mexican").
        """
        logger.info("Fetching meal areas/cuisines")
        response = await self._request("list.php", params={"a": "list"})

        meals = response.data.get("meals", []) or []
        areas = [m.get("strArea") for m in meals if m.get("strArea")]
        logger.info(f"Fetched {len(areas)} areas")
        return areas

    async def get_ingredients_list(self) -> list[dict[str, Any]]:
        """
        Fetch all available ingredients.

        Returns:
            List of ingredient dictionaries with id, name, description.
        """
        logger.info("Fetching ingredients list")
        response = await self._request("list.php", params={"i": "list"})

        meals = response.data.get("meals", []) or []
        ingredients = [
            {
                "id": m.get("idIngredient"),
                "name": m.get("strIngredient"),
                "description": m.get("strDescription"),
            }
            for m in meals
            if m.get("strIngredient")
        ]
        logger.info(f"Fetched {len(ingredients)} ingredients")
        return ingredients

    async def search_meals_by_name(self, name: str) -> list[ParsedMeal]:
        """
        Search meals by name.

        Args:
            name: Meal name to search for.

        Returns:
            List of matching meals.
        """
        logger.info(f"Searching meals by name: {name}")
        response = await self._request("search.php", params={"s": name})

        meals_data = response.data.get("meals") or []
        meals = [ParsedMeal.from_api_response(m) for m in meals_data]
        logger.info(f"Found {len(meals)} meals for '{name}'")
        return meals

    async def search_meals_by_letter(self, letter: str) -> list[ParsedMeal]:
        """
        Search meals by first letter.

        Args:
            letter: Single letter to search by.

        Returns:
            List of meals starting with that letter.
        """
        letter = letter.lower()[:1]
        logger.debug(f"Fetching meals starting with '{letter}'")
        response = await self._request("search.php", params={"f": letter})

        meals_data = response.data.get("meals") or []
        meals = [ParsedMeal.from_api_response(m) for m in meals_data]
        logger.debug(f"Found {len(meals)} meals for letter '{letter}'")
        return meals

    async def get_meal_by_id(self, meal_id: str) -> ParsedMeal | None:
        """
        Get full meal details by ID.

        Args:
            meal_id: The meal ID.

        Returns:
            Parsed meal or None if not found.
        """
        logger.debug(f"Fetching meal by ID: {meal_id}")
        response = await self._request("lookup.php", params={"i": meal_id})

        meals_data = response.data.get("meals") or []
        if not meals_data:
            return None
        return ParsedMeal.from_api_response(meals_data[0])

    async def get_random_meal(self) -> ParsedMeal | None:
        """
        Get a random meal.

        Returns:
            Random parsed meal or None.
        """
        logger.debug("Fetching random meal")
        response = await self._request("random.php")

        meals_data = response.data.get("meals") or []
        if not meals_data:
            return None
        return ParsedMeal.from_api_response(meals_data[0])

    async def filter_by_ingredient(self, ingredient: str) -> list[dict[str, Any]]:
        """
        Filter meals by main ingredient.

        Note: This returns summary data only (id, name, thumb).
        Use get_meal_by_id for full details.

        Args:
            ingredient: Ingredient name.

        Returns:
            List of meal summaries.
        """
        logger.info(f"Filtering meals by ingredient: {ingredient}")
        response = await self._request("filter.php", params={"i": ingredient})

        meals = response.data.get("meals") or []
        logger.info(f"Found {len(meals)} meals with '{ingredient}'")
        return meals

    async def filter_by_category(self, category: str) -> list[dict[str, Any]]:
        """
        Filter meals by category.

        Note: This returns summary data only (id, name, thumb).

        Args:
            category: Category name (e.g., "Seafood", "Dessert").

        Returns:
            List of meal summaries.
        """
        logger.info(f"Filtering meals by category: {category}")
        response = await self._request("filter.php", params={"c": category})

        meals = response.data.get("meals") or []
        logger.info(f"Found {len(meals)} meals in category '{category}'")
        return meals

    async def filter_by_area(self, area: str) -> list[dict[str, Any]]:
        """
        Filter meals by area/cuisine.

        Note: This returns summary data only (id, name, thumb).

        Args:
            area: Area/cuisine name (e.g., "Italian", "Japanese").

        Returns:
            List of meal summaries.
        """
        logger.info(f"Filtering meals by area: {area}")
        response = await self._request("filter.php", params={"a": area})

        meals = response.data.get("meals") or []
        logger.info(f"Found {len(meals)} meals from '{area}'")
        return meals

    async def get_all_meals(self) -> list[ParsedMeal]:
        """
        Fetch all meals by iterating through A-Z.

        This makes 26 API calls, one for each letter.

        Returns:
            List of all parsed meals.
        """
        logger.info("Fetching all meals (A-Z)")
        all_meals: list[ParsedMeal] = []
        letters = "abcdefghijklmnopqrstuvwxyz"

        for letter in letters:
            try:
                meals = await self.search_meals_by_letter(letter)
                all_meals.extend(meals)
            except ConnectorError as e:
                logger.warning(f"Failed to fetch meals for letter '{letter}': {e}")
                continue

        logger.info(f"Fetched {len(all_meals)} total meals")
        return all_meals

    async def health_check(self) -> bool:
        """
        Check if TheMealDB API is reachable.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = await self._request("categories.php")
            return response.is_success
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    async def __aenter__(self) -> "MealDBConnector":
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
