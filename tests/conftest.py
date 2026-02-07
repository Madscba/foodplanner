"""Pytest configuration and shared fixtures."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from foodplanner.database import Base
from foodplanner.models import Store

# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require external services)"
    )
    config.addinivalue_line("markers", "slow: marks tests as slow running")


# =============================================================================
# Scraped Product Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_scraped_products():
    """Sample scraped products data."""
    return [
        {
            "id": "rema-001",
            "name": "Kyllingebryst 500g",
            "price": 59.95,
            "unit": "500g",
            "ean": "5701234567890",
            "category": "Kød & Fjerkræ",
            "image_url": "https://example.com/chicken.jpg",
        },
        {
            "id": "rema-002",
            "name": "Hakket oksekød 400g",
            "price": 49.95,
            "unit": "400g",
            "ean": "5709876543210",
            "category": "Kød & Fjerkræ",
            "image_url": "https://example.com/beef.jpg",
        },
        {
            "id": "rema-003",
            "name": "Øko mælk 1L",
            "price": 15.50,
            "unit": "1L",
            "ean": None,
            "category": "Mejeri",
            "image_url": None,
        },
    ]


@pytest.fixture
def mock_rema1000_store():
    """Sample REMA 1000 store data."""
    return {
        "id": "rema1000-main",
        "name": "REMA 1000",
        "brand": "rema1000",
        "address": None,
        "city": None,
        "zip_code": None,
        "is_active": True,
    }


# =============================================================================
# MealDB Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_mealdb_categories_response():
    """Sample categories response from MealDB API."""
    return {
        "categories": [
            {
                "idCategory": "1",
                "strCategory": "Beef",
                "strCategoryThumb": "https://www.themealdb.com/images/category/beef.png",
                "strCategoryDescription": "Beef is the culinary name...",
            },
            {
                "idCategory": "2",
                "strCategory": "Chicken",
                "strCategoryThumb": "https://www.themealdb.com/images/category/chicken.png",
                "strCategoryDescription": "Chicken is a type of...",
            },
            {
                "idCategory": "3",
                "strCategory": "Dessert",
                "strCategoryThumb": "https://www.themealdb.com/images/category/dessert.png",
                "strCategoryDescription": "Dessert is a course...",
            },
        ]
    }


@pytest.fixture
def mock_mealdb_areas_response():
    """Sample areas response from MealDB API."""
    return {
        "meals": [
            {"strArea": "American"},
            {"strArea": "British"},
            {"strArea": "Canadian"},
            {"strArea": "Chinese"},
            {"strArea": "Italian"},
            {"strArea": "Japanese"},
            {"strArea": "Mexican"},
        ]
    }


@pytest.fixture
def mock_mealdb_ingredients_response():
    """Sample ingredients list response from MealDB API."""
    return {
        "meals": [
            {"idIngredient": "1", "strIngredient": "Chicken", "strDescription": "..."},
            {"idIngredient": "2", "strIngredient": "Salmon", "strDescription": "..."},
            {"idIngredient": "3", "strIngredient": "Beef", "strDescription": "..."},
            {"idIngredient": "4", "strIngredient": "Garlic", "strDescription": "..."},
            {"idIngredient": "5", "strIngredient": "Onion", "strDescription": "..."},
        ]
    }


@pytest.fixture
def mock_mealdb_meal_response():
    """Sample single meal response from MealDB API."""
    return {
        "meals": [
            {
                "idMeal": "52772",
                "strMeal": "Teriyaki Chicken Casserole",
                "strDrinkAlternate": None,
                "strCategory": "Chicken",
                "strArea": "Japanese",
                "strInstructions": "Preheat oven to 350° F. Spray a 9x13-inch baking pan...",
                "strMealThumb": "https://www.themealdb.com/images/media/meals/wvpsxx1468256321.jpg",
                "strTags": "Meat,Casserole",
                "strYoutube": "https://www.youtube.com/watch?v=4aZr5hZXP_s",
                "strIngredient1": "soy sauce",
                "strIngredient2": "water",
                "strIngredient3": "brown sugar",
                "strIngredient4": "ground ginger",
                "strIngredient5": "minced garlic",
                "strIngredient6": "cornstarch",
                "strIngredient7": "chicken breasts",
                "strIngredient8": "stir-fry vegetables",
                "strIngredient9": "brown rice",
                "strIngredient10": "",
                "strIngredient11": "",
                "strIngredient12": "",
                "strIngredient13": "",
                "strIngredient14": "",
                "strIngredient15": "",
                "strIngredient16": "",
                "strIngredient17": "",
                "strIngredient18": "",
                "strIngredient19": "",
                "strIngredient20": "",
                "strMeasure1": "3/4 cup",
                "strMeasure2": "1/2 cup",
                "strMeasure3": "1/4 cup",
                "strMeasure4": "1/2 teaspoon",
                "strMeasure5": "1/2 teaspoon",
                "strMeasure6": "4 Tablespoons",
                "strMeasure7": "2",
                "strMeasure8": "1 (12 oz.)",
                "strMeasure9": "3 cups",
                "strMeasure10": "",
                "strMeasure11": "",
                "strMeasure12": "",
                "strMeasure13": "",
                "strMeasure14": "",
                "strMeasure15": "",
                "strMeasure16": "",
                "strMeasure17": "",
                "strMeasure18": "",
                "strMeasure19": "",
                "strMeasure20": "",
                "strSource": "https://example.com/recipe",
                "strImageSource": None,
                "strCreativeCommonsConfirmed": None,
                "dateModified": None,
            }
        ]
    }


@pytest.fixture
def mock_mealdb_search_response():
    """Sample search response with multiple meals."""
    return {
        "meals": [
            {
                "idMeal": "52772",
                "strMeal": "Teriyaki Chicken Casserole",
                "strCategory": "Chicken",
                "strArea": "Japanese",
                "strInstructions": "Preheat oven...",
                "strMealThumb": "https://example.com/thumb.jpg",
                "strTags": "Meat,Casserole",
                "strYoutube": None,
                "strIngredient1": "chicken",
                "strIngredient2": "rice",
                "strIngredient3": "",
                "strMeasure1": "500g",
                "strMeasure2": "2 cups",
                "strMeasure3": "",
                **{f"strIngredient{i}": "" for i in range(4, 21)},
                **{f"strMeasure{i}": "" for i in range(4, 21)},
                "strSource": None,
            },
            {
                "idMeal": "52773",
                "strMeal": "Honey Teriyaki Salmon",
                "strCategory": "Seafood",
                "strArea": "Japanese",
                "strInstructions": "Mix all sauce...",
                "strMealThumb": "https://example.com/thumb2.jpg",
                "strTags": "Fish",
                "strYoutube": None,
                "strIngredient1": "salmon",
                "strIngredient2": "honey",
                "strIngredient3": "soy sauce",
                "strIngredient4": "",
                "strMeasure1": "2 fillets",
                "strMeasure2": "2 tbsp",
                "strMeasure3": "1/4 cup",
                "strMeasure4": "",
                **{f"strIngredient{i}": "" for i in range(5, 21)},
                **{f"strMeasure{i}": "" for i in range(5, 21)},
                "strSource": None,
            },
        ]
    }


@pytest.fixture
def mock_neo4j_driver():
    """Mock Neo4j async driver."""
    driver = AsyncMock()
    driver.verify_connectivity = AsyncMock()
    driver.close = AsyncMock()

    session = AsyncMock()
    driver.session = MagicMock(return_value=session)

    return driver


@pytest.fixture
def sample_products():
    """Sample products for matching tests."""
    return [
        {"id": "p1", "name": "chicken breast", "price": 59.95, "store_id": "s1"},
        {"id": "p2", "name": "kyllingbryst", "price": 49.95, "store_id": "s1"},
        {"id": "p3", "name": "brown rice", "price": 24.95, "store_id": "s1"},
        {"id": "p4", "name": "jasmine rice", "price": 29.95, "store_id": "s1"},
        {"id": "p5", "name": "soy sauce", "price": 19.95, "store_id": "s1"},
        {"id": "p6", "name": "fresh garlic", "price": 12.95, "store_id": "s1"},
        {"id": "p7", "name": "hvidløg", "price": 9.95, "store_id": "s1"},
        {"id": "p8", "name": "yellow onion", "price": 8.95, "store_id": "s1"},
        {"id": "p9", "name": "løg", "price": 6.95, "store_id": "s1"},
    ]


# =============================================================================
# PostgreSQL Test Database Fixtures
# =============================================================================


def get_test_database_url() -> str:
    """Get the test database URL from environment or use default.

    Uses a separate test database to avoid conflicts with development data.
    Default uses the standard development PostgreSQL with a _test suffix.
    """
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://foodplanner:foodplanner_dev@localhost:5432/foodplanner_test",
    )


@pytest.fixture(scope="function")
def test_db_engine():
    """Create a PostgreSQL test database engine.

    Creates all tables and cleans up after each test.
    Requires PostgreSQL to be running (via Docker or locally).
    """
    database_url = get_test_database_url()
    engine = create_engine(database_url, echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Clean up: drop all tables after test
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_session(test_db_engine):
    """Create a test database session."""
    with Session(test_db_engine) as session:
        yield session


@pytest.fixture
def sample_store(test_session):
    """Create a sample store for testing."""
    store = Store(
        id="rema1000-test",
        name="Test REMA 1000",
        brand="rema1000",
        address="Test Address 1",
        city="Test City",
        zip_code="8000",
        is_active=True,
    )
    test_session.add(store)
    test_session.commit()
    return store


@pytest.fixture
def sample_scraped_products():
    """Sample scraped product data for ingestion tests."""
    return [
        {
            "id": "prod-001",
            "name": "Kyllingebryst 500g",
            "price": 59.95,
            "unit": "500g",
            "ean": "5701234567890",
            "category": "Kød & Fjerkræ",
            "image_url": "https://example.com/image.jpg",
        },
        {
            "id": "prod-002",
            "name": "Hakket oksekød 400g",
            "price": 49.95,
            "unit": "400g",
            "ean": "5709876543210",
            "category": "Kød & Fjerkræ",
            "image_url": None,
        },
    ]
