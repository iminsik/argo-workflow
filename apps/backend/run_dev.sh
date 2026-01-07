#!/bin/bash
# Development server startup script with proper poetry environment

set -e

cd "$(dirname "$0")"

# Set feature flag (default to false if not set)
export USE_HERA_SDK="${USE_HERA_SDK:-false}"

echo "Starting backend development server..."
echo "USE_HERA_SDK=$USE_HERA_SDK"
echo ""

# Use poetry run to ensure correct virtual environment
poetry run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

