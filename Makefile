.PHONY: help build up down logs shell test lint clean migrate ingest

help:
	@echo "Foodplanner - Make Commands"
	@echo ""
	@echo "Core Commands:"
	@echo "  make build          - Build Docker images"
	@echo "  make up             - Start all services (API, DB, Redis, Celery)"
	@echo "  make down           - Stop all services"
	@echo "  make logs           - View all logs"
	@echo "  make ps             - Show running containers"
	@echo "  make clean          - Remove containers and volumes"
	@echo ""
	@echo "Development:"
	@echo "  make shell          - Open shell in API container"
	@echo "  make shell-db       - Open PostgreSQL shell"
	@echo "  make test           - Run tests"
	@echo "  make test-cov       - Run tests with coverage"
	@echo "  make lint           - Run linter"
	@echo "  make lint-fix       - Run linter and fix issues"
	@echo ""
	@echo "Logs:"
	@echo "  make logs-api       - View API logs only"
	@echo "  make logs-worker    - View Celery worker logs"
	@echo "  make logs-beat      - View Celery beat scheduler logs"
	@echo ""
	@echo "Ingestion:"
	@echo "  make ingest         - Trigger ingestion manually"
	@echo "  make ingest-status  - Check recent ingestion runs"
	@echo ""
	@echo "Optional Services:"
	@echo "  make up-monitoring  - Start with Flower (Celery monitoring)"
	@echo "  make up-tools       - Start with pgAdmin"
	@echo "  make up-all         - Start all services including optional ones"

# Core commands
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

ps:
	docker-compose ps

clean:
	docker-compose down -v
	docker system prune -f

restart:
	docker-compose restart

# Optional services
up-monitoring:
	docker-compose --profile monitoring up -d

up-tools:
	docker-compose --profile tools up -d

up-all:
	docker-compose --profile monitoring --profile tools up -d

# Individual service logs
logs-api:
	docker-compose logs -f api

logs-worker:
	docker-compose logs -f celery-worker

logs-beat:
	docker-compose logs -f celery-beat

logs-redis:
	docker-compose logs -f redis

logs-db:
	docker-compose logs -f postgres

# Shell access
shell:
	docker-compose exec api /bin/bash

shell-db:
	docker-compose exec postgres psql -U foodplanner -d foodplanner

shell-redis:
	docker-compose exec redis redis-cli

shell-worker:
	docker-compose exec celery-worker /bin/bash

# Testing
test:
	docker-compose exec api pytest

test-cov:
	docker-compose exec api pytest --cov=foodplanner --cov-report=html

test-local:
	uv run pytest

# Linting
lint:
	docker-compose exec api ruff check .

lint-fix:
	docker-compose exec api ruff check --fix .

lint-local:
	uv run ruff check .

# Ingestion commands
ingest:
	@echo "Triggering manual ingestion via API..."
	curl -X POST http://localhost:8000/api/v1/ingestion/trigger \
		-H "Content-Type: application/json" \
		-d '{"force": false}'

ingest-force:
	@echo "Triggering forced ingestion via API..."
	curl -X POST http://localhost:8000/api/v1/ingestion/trigger \
		-H "Content-Type: application/json" \
		-d '{"force": true}'

ingest-status:
	@echo "Getting recent ingestion runs..."
	curl -s http://localhost:8000/api/v1/ingestion/runs | python -m json.tool

ingest-health:
	@echo "Checking ingestion health..."
	curl -s http://localhost:8000/api/v1/ingestion/health | python -m json.tool

ingest-stats:
	@echo "Getting ingestion statistics..."
	curl -s http://localhost:8000/api/v1/ingestion/stats | python -m json.tool

# Database migrations (placeholder)
migrate:
	@echo "Migrations not yet implemented - will use Alembic"
	# docker-compose exec api alembic upgrade head

# Individual service restarts
restart-api:
	docker-compose restart api

restart-worker:
	docker-compose restart celery-worker

restart-beat:
	docker-compose restart celery-beat

# Health checks
health:
	@echo "API Health:"
	@curl -s http://localhost:8000/health | python -m json.tool
	@echo "\nIngestion Health:"
	@curl -s http://localhost:8000/api/v1/ingestion/health | python -m json.tool
