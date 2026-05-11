#!/usr/bin/env bash
set -euo pipefail

SEASON_SLUG="${1:-qa-season}"
BASE_URL="${2:-http://localhost:8000}"

state_url="${BASE_URL}/seasons/${SEASON_SLUG}/state/"
conn_url="${BASE_URL}/seasons/${SEASON_SLUG}/connection-test/?client_time_ms=1000"

state_out="$(mktemp)"
conn_out="$(mktemp)"
trap 'rm -f "$state_out" "$conn_out"' EXIT

echo "Bursting season state endpoint: ${state_url}"
seq 1 200 | xargs -I{} -P20 sh -c "curl -s -o /dev/null -w '%{http_code}\n' '${state_url}'" > "$state_out"

echo "Bursting connection-test endpoint: ${conn_url}"
seq 1 40 | xargs -I{} -P10 sh -c "curl -s -o /dev/null -w '%{http_code}\n' '${conn_url}'" > "$conn_out"

state_200=$(grep -c '^200$' "$state_out" || true)
state_429=$(grep -c '^429$' "$state_out" || true)
conn_200=$(grep -c '^200$' "$conn_out" || true)
conn_429=$(grep -c '^429$' "$conn_out" || true)

echo ""
echo "State endpoint summary"
echo "200: ${state_200}"
echo "429: ${state_429}"

echo ""
echo "Connection-test endpoint summary"
echo "200: ${conn_200}"
echo "429: ${conn_429}"

echo ""
echo "Sample throttled response headers (if throttled):"
curl -s -D - -o /dev/null "${conn_url}" | grep -E 'HTTP/|X-RateLimit|Retry-After' || true
