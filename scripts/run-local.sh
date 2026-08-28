#!/bin/sh
set -e

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8042}"
USE_DAPHNE="${USE_DAPHNE:-0}"
PYTHON="${PYTHON:-python}"
DJANGO_DB_PATH="${DJANGO_DB_PATH:-db/db.sqlite3}"

mkdir -p "$(dirname "$DJANGO_DB_PATH")"
export DJANGO_DB_PATH

echo "Running migrations..."
"$PYTHON" manage.py migrate --noinput

echo "Collecting static files..."
"$PYTHON" manage.py collectstatic --noinput

if [ "$USE_DAPHNE" = "1" ]; then
  echo "Starting Daphne ASGI server on ${HOST}:${PORT} (no live reload)..."
  exec daphne -b "$HOST" -p "$PORT" con_quest.asgi:application
fi

echo "Starting Django dev server with live reload on ${HOST}:${PORT}..."
exec "$PYTHON" manage.py runserver "${HOST}:${PORT}"
