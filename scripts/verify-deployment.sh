#!/usr/bin/env sh
set -eu

BASE_URL="${1:-}"
if [ -z "$BASE_URL" ]; then
  echo "Usage: API_TOKEN=... $0 https://your-service.onrender.com" >&2
  exit 2
fi
: "${API_TOKEN:?Set API_TOKEN in the environment before running this check}"

BASE_URL="${BASE_URL%/}"

echo "[1/4] Health endpoint"
curl --fail --silent --show-error "$BASE_URL/health"
echo

echo "[2/4] Public workspace shell"
workspace_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$BASE_URL/workspace")"
[ "$workspace_code" = "200" ] || { echo "Expected /workspace HTTP 200, got $workspace_code" >&2; exit 1; }

echo "[3/4] Protected API rejects anonymous access"
api_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "$BASE_URL/api/network")"
[ "$api_code" = "401" ] || { echo "Expected /api/network HTTP 401, got $api_code" >&2; exit 1; }

echo "[4/4] Administrator authentication"
admin_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  -H "Authorization: Bearer $API_TOKEN" "$BASE_URL/admin/tenants")"
[ "$admin_code" = "200" ] || { echo "Expected /admin/tenants HTTP 200, got $admin_code" >&2; exit 1; }

echo "Iskra deployment checks passed."
