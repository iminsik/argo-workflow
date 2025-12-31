FROM python:3.11-alpine
WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files (from apps/backend directory)
COPY apps/backend/pyproject.toml apps/backend/uv.lock* ./

# Install dependencies
RUN uv sync --no-install-project --frozen

# Copy application code (from apps/backend directory)
COPY apps/backend/app/ ./app/
# Copy infrastructure directory (from repo root)
COPY infrastructure/ /infrastructure/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

