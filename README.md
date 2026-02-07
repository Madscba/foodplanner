# Foodplanner

Open-source meal planning that prioritizes local discounts and healthy recipes.

## Goals

- Generate meal plans based on user preferences, pantry items, and store discounts.
- Favor deterministic, replayable pipelines with LLMs as orchestrators.
- Support Danish grocery stores via web scraping (starting with REMA 1000).

## Quick Start (Docker - Recommended)

### Prerequisites

- Docker and Docker Compose installed

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/foodplanner.git
   cd foodplanner
   ```

2. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start all services**:
   ```bash
   docker-compose up -d
   ```

   This will automatically:
   - Start PostgreSQL, Redis, and Neo4j databases
   - Start the FastAPI backend and Celery workers
   - **Seed the database** with REMA 1000 products (runs once on first startup)

4. **View logs**:
   ```bash
   docker-compose logs -f

   # Watch the seeding progress
   docker-compose logs -f seed
   ```

5. **Access the services**:
   | Service | URL |
   |---------|-----|
   | API | http://localhost:8000 |
   | API Docs | http://localhost:8000/docs |
   | Health Check | http://localhost:8000/health |
   | Neo4j Browser | http://localhost:7474 |

### Docker Compose Profiles

Start optional services with profiles:

```bash
# Start with React frontend
docker-compose --profile frontend up -d
# Frontend: http://localhost:3000

# Start with pgAdmin (database management)
docker-compose --profile tools up -d
# pgAdmin: http://localhost:5050 (admin@foodplanner.local / admin)

# Start with Flower (Celery monitoring)
docker-compose --profile monitoring up -d
# Flower: http://localhost:5555

# Start with everything
docker-compose --profile frontend --profile tools --profile monitoring up -d
```

### Automatic Data Seeding

On first startup, the `seed` service automatically:
1. Waits for all databases to be healthy
2. Creates the REMA 1000 store record
3. Scrapes products from 9 food categories
4. Syncs products to Neo4j knowledge graph

**Seeding Configuration** (via environment variables):

| Variable | Default | Description |
|----------|---------|-------------|
| `SEED_CATEGORIES` | avisvarer,brod-bavinchi,... | Comma-separated category slugs to scrape |
| `SEED_LIMIT_PER_CATEGORY` | 100 | Max products per category |
| `SEED_SKIP_IF_EXISTS` | true | Skip seeding if products already exist |
| `SEED_MIN_PRODUCTS` | 100 | Minimum products before skipping seed |
| `SEED_SYNC_TO_GRAPH` | true | Sync products to Neo4j after seeding |

**Re-run seeding manually**:
```bash
# Force re-seed (removes SEED_SKIP_IF_EXISTS behavior)
docker-compose run --rm -e SEED_SKIP_IF_EXISTS=false seed
```

## Development Commands

We provide a Makefile for common operations:

```bash
make build          # Build Docker images
make up             # Start all services
make down           # Stop all services
make logs           # View all logs
make logs-api       # View API logs only
make shell          # Open shell in API container
make test           # Run tests
make lint           # Run linter
make clean          # Remove containers and volumes
make ingest         # Run ingestion manually
```

## Local Setup (without Docker)

If you prefer running locally with `uv`:

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- `uv` package manager

### Setup

```bash
# Install dependencies
uv venv
uv sync --extra dev

# Set up database
createdb foodplanner

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run API
uv run uvicorn foodplanner.main:app --reload
```

### Tooling

```bash
# Lint
uv run ruff check .

# Test (unit tests only)
uv run pytest -m "not integration"

# Test with coverage
uv run pytest -m "not integration" --cov=foodplanner

# Integration tests
uv run pytest -m integration

# Type check
uv run pyrefly src

# Run daily ingestion
uv run python -m foodplanner.ingest.batch_ingest
```

See [docs/testing.md](docs/testing.md) for the complete testing strategy.

## Architecture

- **Backend**: Python + FastAPI + SQLAlchemy
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Databases**: PostgreSQL 16 (relational), Neo4j 5 (knowledge graph)
- **Task Queue**: Celery + Redis
- **Data Sources**:
  - Web scraping (REMA 1000, more stores planned)
  - TheMealDB (recipes)

See [docs/pipeline.md](docs/pipeline.md) for detailed architecture.
See [docs/graph-database.md](docs/graph-database.md) for the recipe knowledge graph.
See [docs/testing.md](docs/testing.md) for the testing strategy.

## Frontend

The frontend is a React single-page application that provides meal planning functionality.

### Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | React 18 + TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS |
| Components | shadcn/ui + Radix UI |
| Server State | TanStack Query v5 |
| Client State | Zustand |
| Routing | React Router v6 |
| Drag & Drop | dnd-kit |

### Local Development

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

The frontend proxies API requests to the backend at http://localhost:8000.

### Frontend Structure

```
frontend/
├── src/
│   ├── api/           # Typed API client
│   │   ├── client.ts  # Fetch wrapper
│   │   ├── endpoints.ts
│   │   └── types.ts   # TypeScript types
│   ├── components/    # Reusable components
│   │   ├── ui/        # shadcn/ui primitives
│   │   ├── MealCard.tsx
│   │   ├── MealDayColumn.tsx
│   │   └── ...
│   ├── hooks/         # TanStack Query hooks
│   ├── stores/        # Zustand stores
│   ├── pages/         # Route components
│   └── utils/         # Helpers and constants
└── package.json
```

### User Flow

1. **Plan Setup** (`/plan/setup`) - Select dates, people count, and dietary preferences
2. **Meal Plan View** (`/plan/view/:id`) - View/edit the generated meal plan calendar
3. **Shopping List** (`/plan/shopping/:id`) - View aggregated shopping list with export

### Build for Production

```bash
cd frontend
npm run build   # Output in frontend/dist/
```

The build output is a static bundle that can be served from any CDN.

### Extending the UI

1. **Add new components**: Create in `src/components/` following existing patterns
2. **Add new pages**: Create in `src/pages/` and register route in `App.tsx`
3. **Add API calls**: Add endpoint in `src/api/endpoints.ts` with types in `types.ts`
4. **Server state**: Create TanStack Query hook in `src/hooks/`
5. **Client state**: Add slice to appropriate Zustand store in `src/stores/`

## Project Structure

```
foodplanner/
├── src/foodplanner/       # Backend application code
│   ├── graph/             # Neo4j knowledge graph
│   ├── ingest/            # Data ingestion
│   │   ├── connectors/    # Recipe API connectors (MealDB)
│   │   └── scrapers/      # Grocery store web scrapers
│   ├── normalize/         # Data transformation
│   ├── plan/              # Meal planning logic
│   ├── order/             # Shopping cart operations
│   ├── orchestrator/      # LLM orchestration
│   ├── routers/           # API endpoints
│   ├── tasks/             # Celery background tasks
│   ├── models.py          # Database models
│   ├── schemas.py         # API schemas
│   └── main.py            # FastAPI app
├── frontend/              # React frontend
│   ├── src/
│   │   ├── api/           # Typed API client
│   │   ├── components/    # UI components
│   │   ├── hooks/         # TanStack Query hooks
│   │   ├── stores/        # Zustand stores
│   │   └── pages/         # Route components
│   └── package.json
├── tests/                 # Test suite
├── docs/                  # Documentation
├── Dockerfile             # Container definition
├── docker-compose.yml     # Service orchestration
└── pyproject.toml         # Python dependencies
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and recent changes.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Roadmap

- [x] Core architecture and data models
- [x] Web scraping infrastructure for grocery stores
- [x] REMA 1000 product scraper
- [x] Daily batch ingestion pipeline
- [x] Recipe database and search (Neo4j + TheMealDB)
- [x] Product matching algorithm (fuzzy + synonym matching)
- [x] Frontend implementation (React + TypeScript)
- [x] Meal plan API endpoints
- [x] Shopping list generation
- [ ] Additional store scrapers (Netto, Føtex, Bilka)
- [ ] Meal plan optimization (cost + nutrition)
- [ ] User authentication
- [ ] Recipe recommendations (LLM)
- [ ] External shop cart integration

## Support

- Issues: [GitHub Issues](https://github.com/yourusername/foodplanner/issues)
- Documentation: [docs/](docs/)
- API Reference: http://localhost:8000/docs (when running)
