# Contributing to Foodplanner

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, inclusive, and constructive in all interactions. We're building this tool to help people save money and eat better.

## Getting Started

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 14+ (for local development)
- `uv` package manager ([installation guide](https://github.com/astral-sh/uv))

### Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/foodplanner.git
   cd foodplanner
   ```

2. **Install dependencies**:
   ```bash
   uv venv
   uv sync --extra dev
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and database connection
   ```

4. **Set up the database**:
   ```bash
   # Create database
   createdb foodplanner

   # Run migrations (when available)
   # uv run alembic upgrade head
   ```

5. **Run tests**:
   ```bash
   uv run pytest
   ```

6. **Start the dev server**:
   ```bash
   uv run uvicorn foodplanner.main:app --reload
   ```

## How to Contribute

### Reporting Bugs

1. Check if the issue already exists in [GitHub Issues](https://github.com/yourusername/foodplanner/issues)
2. If not, create a new issue with:
   - Clear description of the bug
   - Steps to reproduce
   - Expected vs actual behavior
   - Your environment (OS, Python version)
   - Relevant logs or screenshots

### Suggesting Features

1. Open an issue with the `enhancement` label
2. Describe the feature and its use case
3. Explain why it would benefit users
4. If possible, suggest an implementation approach

### Submitting Pull Requests

1. **Fork the repository** and create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Follow the code style (see below)
   - Add tests for new functionality
   - Update documentation as needed

3. **Run linting and tests**:
   ```bash
   uv run ruff check .
   uv run pyrefly src
   uv run pytest
   ```

4. **Commit your changes**:
   - Use clear, descriptive commit messages
   - Follow the format: `type: description`
     - `feat: add recipe search endpoint`
     - `fix: correct discount calculation for bundled items`
     - `docs: update pipeline architecture diagram`
     - `test: add unit tests for product matching`

5. **Push and create a pull request**:
   ```bash
   git push origin feature/your-feature-name
   ```
   - Fill out the PR template
   - Link related issues
   - Request review

6. **Respond to feedback**:
   - Address reviewer comments
   - Push additional commits to your branch

## Code Style Guide

### Python

- Follow PEP 8 conventions
- Line length: 100 characters
- Use type hints for all function signatures
- Docstrings for all public functions and classes

**Example**:
```python
def calculate_discount(original_price: float, discount_percentage: float) -> float:
    """Calculate the discounted price.

    Args:
        original_price: The original price of the product.
        discount_percentage: The discount as a percentage (0-100).

    Returns:
        The discounted price.
    """
    return original_price * (1 - discount_percentage / 100)
```

### Linting

We use `ruff` for linting and formatting:

```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Type Checking

We use `pyrefly` for type checking:

```bash
uv run pyrefly src
```

## Testing Guidelines

### Unit Tests

- Place tests in `tests/` with the same structure as `src/`
- Test file names: `test_<module_name>.py`
- Test function names: `test_<function_name>_<scenario>`

**Example**:
```python
def test_calculate_discount_valid_percentage():
    result = calculate_discount(100.0, 20.0)
    assert result == 80.0

def test_calculate_discount_zero_percentage():
    result = calculate_discount(100.0, 0.0)
    assert result == 100.0
```

### Integration Tests

- Test API endpoints with `TestClient`
- Mock external services (scrapers, LLM calls)
- Use fixtures for common test data

### Running Tests

```bash
# All tests
uv run pytest

# Specific file
uv run pytest tests/test_schemas.py

# With coverage
uv run pytest --cov=foodplanner --cov-report=html
```

## Project Structure

```
foodplanner/
├── src/foodplanner/
│   ├── ingest/              # External data ingestion
│   │   ├── connectors/      # Recipe API connectors (MealDB)
│   │   ├── scrapers/        # Grocery store web scrapers
│   │   │   ├── base.py      # BaseScraper abstract class
│   │   │   └── rema1000.py  # REMA 1000 scraper
│   │   ├── batch_ingest.py  # Daily batch ingestion pipeline
│   │   └── schemas.py       # Data validation schemas
│   ├── graph/               # Neo4j knowledge graph
│   ├── normalize/           # Data transformation
│   ├── plan/                # Meal planning logic
│   ├── order/               # Cart and ordering
│   ├── orchestrator/        # LLM orchestration
│   ├── routers/             # API endpoints
│   ├── tasks/               # Celery background tasks
│   ├── database.py          # Database config
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   └── main.py              # FastAPI app
├── tests/                   # Test files
├── docs/                    # Documentation
├── .cursor/                 # Cursor IDE rules
└── pyproject.toml           # Dependencies and config
```

## Areas That Need Help

### High Priority

- [ ] Recipe database seeding (import from open datasets)
- [ ] Product matching algorithm (ingredient → product)
- [ ] Meal plan optimization logic
- [ ] User authentication and authorization
- [ ] Frontend implementation

### Medium Priority

- [ ] Additional store scrapers (Netto, Føtex, Bilka, Coop)
- [ ] Email notifications for discounts
- [ ] Export to shopping list apps
- [ ] Multi-language support (English + Danish)

### Nice to Have

- [ ] Recipe photos and styling
- [ ] Social sharing features
- [ ] Mobile app (React Native or Flutter)
- [ ] Integration with meal prep containers

## Adding a New Store Scraper

To add a scraper for a new grocery store:

1. **Create a new file** in `src/foodplanner/ingest/scrapers/`:

```python
# src/foodplanner/ingest/scrapers/newstore.py
from foodplanner.ingest.scrapers.base import BaseScraper

class NewStoreScraper(BaseScraper):
    BASE_URL = "https://newstore.dk"
    STORE_NAME = "New Store"
    STORE_BRAND = "newstore"

    async def scrape_products(self, category=None, limit=None):
        # Implement product scraping
        pass

    async def scrape_categories(self):
        # Implement category scraping
        pass
```

2. **Register the scraper** in `src/foodplanner/ingest/scrapers/__init__.py`:

```python
from foodplanner.ingest.scrapers.newstore import NewStoreScraper

SCRAPER_REGISTRY["newstore"] = NewStoreScraper
```

3. **Add tests** in `tests/test_scrapers.py`:

```python
class TestNewStoreScraper:
    def test_scraper_initialization(self):
        scraper = NewStoreScraper()
        assert scraper.STORE_NAME == "New Store"
        # ... more tests
```

4. **Update documentation** in `docs/integrations.md`

## Documentation

- Update README.md if you change setup steps
- Update docs/ for architecture or design changes
- Add inline comments for complex logic
- Document breaking changes in your PR

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

- Open a [GitHub Discussion](https://github.com/yourusername/foodplanner/discussions)
- Join our community chat (link TBD)
- Email the maintainers (link TBD)

Thank you for contributing to Foodplanner!
