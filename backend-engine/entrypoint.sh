#!/bin/sh
set -e
cd /app
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete. Starting server..."
exec uvicorn api.main:app --host 0.0.0.0 --port 8000
