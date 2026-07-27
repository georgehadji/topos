#!/usr/bin/env bash
# run.sh — Lightweight developer CLI wrapper for Topos (Windows/macOS/Linux)
# Use this instead of 'make' if it is not installed on your system.

set -e

show_help() {
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  up         Start PostgreSQL, MinIO, API, and background worker"
    echo "  down       Stop all background containers"
    echo "  upgrade    Apply database migrations inside the active API container"
    echo "  test       Run the full automated test suite (96 tests)"
    echo "  check      Run Ruff format, lint, and strict MyPy type checking"
    echo "  ingest     Trigger a live document ingestion request to test the pipeline"
    echo "  search     Query the live search endpoint"
    echo ""
}

case "${1:-}" in
    up)
        echo "🚀 Starting backend infrastructure..."
        docker compose up -d --build
        ;;
    down)
        echo "🛑 Stopping backend infrastructure..."
        docker compose down
        ;;
    upgrade)
        echo "🗄️ Applying database migrations inside the API container..."
        docker compose exec api /app/.venv/bin/alembic upgrade head
        ;;
    test)
        echo "🧪 Running the automated test suite..."
        uv run pytest
        ;;
    check)
        echo "🧪 Running Ruff formatting, lint checks, and MyPy static typing..."
        uv run ruff format src tests && uv run ruff check src tests && uv run mypy
        ;;
    ingest)
        echo "📥 Triggering a live document ingestion..."
        curl -X POST "http://localhost:8000/artifacts/ingest?limit=1"
        echo ""
        ;;
    search)
        echo "🔍 Querying the live search endpoint..."
        curl "http://localhost:8000/api/search"
        echo ""
        ;;
    *)
        show_help
        ;;
esac
