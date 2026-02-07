"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://localhost/foodplanner"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Neo4j Graph Database
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "foodplanner_dev"

    # External APIs
    mealdb_api_key: str = "1"  # Default test key
    mealdb_base_url: str = "https://www.themealdb.com/api/json/v1"

    # Web Scraping (basic)
    scraping_rate_limit: float = 1.0  # seconds between requests
    scraping_timeout: float = 30.0  # request timeout in seconds
    scraping_max_retries: int = 3

    # Full Scrape Settings (anti-blocking configuration)
    # These control the behavior of comprehensive product scrapes
    full_scrape_min_delay: float = 2.0  # Min seconds between page loads
    full_scrape_max_delay: float = 5.0  # Max seconds between page loads
    full_scrape_category_delay: float = 30.0  # Delay between category scrapes
    full_scrape_max_retries: int = 5  # Max consecutive errors before circuit break
    full_scrape_backoff_factor: float = 2.0  # Multiplier for exponential backoff

    # LLM APIs (optional)
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    @property
    def mealdb_url(self) -> str:
        """Get the full MealDB API URL with API key."""
        return f"{self.mealdb_base_url}/{self.mealdb_api_key}"

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# For backward compatibility with existing code using os.getenv
settings = get_settings()
