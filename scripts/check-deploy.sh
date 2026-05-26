#!/usr/bin/env bash
set -euo pipefail

# Verify that staging and production are running the expected git SHA.
# Usage: ./scripts/check-deploy.sh
#
# Works with any project that exposes GET /api/health returning {"sha": "..."}
# Configure environments via DEPLOY_TARGETS or use defaults below.

# Defaults — reads TRAEFIK_HOST from .env.stg and .env.prod if available
: "${LOCAL_SHA:=$(git rev-parse --short HEAD)}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

read_host() {
    local env_file="$PROJECT_DIR/.env.$1"
    if [[ -f "$env_file" ]]; then
        local host
        host=$(grep -m1 '^TRAEFIK_HOST=' "$env_file" 2>/dev/null | cut -d= -f2 | cut -d, -f1) || true
        echo "$host"
    fi
}

: "${STG_URL:=https://$(read_host stg)}"
: "${PROD_URL:=https://$(read_host prod)}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

check_env() {
    local name="$1"
    local url="$2"

    local response
    response=$(curl -sfL --max-time 5 "${url}/api/health" 2>/dev/null) || {
        printf "  ${YELLOW}%-6s${NC} ${RED}UNREACHABLE${NC} ${url}/api/health\n" "$name"
        return 1
    }

    local remote_sha
    remote_sha=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('sha','unknown'))" 2>/dev/null)

    local check_url="${url}/api/health"

    # Compare using only the first 7 chars of each SHA
    local local_short="${LOCAL_SHA:0:7}"
    local remote_short="${remote_sha:0:7}"

    if [[ "$local_short" == "$remote_short" ]]; then
        printf "  ${GREEN}%-6s${NC} %s  ${GREEN}✓ %s${NC}\n" "$name" "$check_url" "$remote_sha"
    else
        printf "  ${RED}%-6s${NC} %s  ${RED}✗ detected '%s' (expected %s)${NC}\n" "$name" "$check_url" "${remote_sha:-<empty>}" "$LOCAL_SHA"
        return 1
    fi
}

echo "Local HEAD: $LOCAL_SHA"
echo ""

FAILED=0
check_env "STG" "$STG_URL" || FAILED=$((FAILED + 1))
check_env "PROD" "$PROD_URL" || FAILED=$((FAILED + 1))

echo ""
if [[ $FAILED -eq 0 ]]; then
    printf "${GREEN}All environments up to date.${NC}\n"
else
    printf "${YELLOW}%d environment(s) out of sync or unreachable.${NC}\n" "$FAILED"
    exit 1
fi
