#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <stg|prod>"
    exit 1
}

[[ $# -ne 1 ]] && usage

ENV="$1"
case "$ENV" in
    stg)  ENV_FILE=".env.stg" ;;
    prod) ENV_FILE=".env.prod" ;;
    *)    echo "Error: argument must be 'stg' or 'prod'"; usage ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found in $PROJECT_DIR"
    exit 1
fi

echo "==> Stopping existing containers..."
export ENV_FILE
docker compose --env-file "$ENV_FILE" down --remove-orphans

echo "==> Starting con-quest ($ENV) with $ENV_FILE..."
docker compose --env-file "$ENV_FILE" up -d --force-recreate

echo "==> Container status:"
docker compose --env-file "$ENV_FILE" ps
