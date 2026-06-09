#!/bin/bash
set -e

if [ ! -f /app/data/fund.duckdb ]; then
    echo "[entrypoint] Initializing DuckDB..."
    uv run python phase1/generate.py
fi

if [ ! -f /app/data/chroma/chroma.sqlite3 ]; then
    echo "[entrypoint] Initializing ChromaDB..."
    uv run python phase4/ingest.py
fi

exec "$@"
