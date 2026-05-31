#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Daphne ASGI server on port 8004..."
exec daphne -b 0.0.0.0 -p 8003 con_quest.asgi:application
