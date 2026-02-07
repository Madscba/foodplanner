FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including:
# - PostgreSQL client libraries
# - Playwright browser dependencies (Chromium)
# - curl for health checks
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    wget \
    gnupg \
    # Playwright/Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml README.md ./

# Install Python dependencies directly with pip
RUN pip install --no-cache-dir -e .

# Install Playwright browsers (Chromium only for smaller image)
RUN playwright install chromium

# Copy application source code
COPY src/ ./src/

# Copy scripts for seeding and utilities
COPY scripts/ ./scripts/

# Set Python path
ENV PYTHONPATH="/app/src:$PYTHONPATH"

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "foodplanner.main:app", "--host", "0.0.0.0", "--port", "8000"]
