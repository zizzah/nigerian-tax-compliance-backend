#!/bin/bash
set -e
echo "=== Starting application ==="
echo "=== Listing migration files ==="
ls alembic/versions/
echo "=== Running database migrations ==="
alembic upgrade head 2>&1
MIGRATION_EXIT=$?
if [ $MIGRATION_EXIT -ne 0 ]; then
    echo "=== Migration failed with exit code $MIGRATION_EXIT ==="
    echo "=== Attempting to stamp head and continue ==="
    alembic stamp head 2>&1 || echo "Stamp also failed, continuing anyway"
fi
echo "=== Starting uvicorn ==="
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1