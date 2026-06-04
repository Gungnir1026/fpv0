#!/usr/bin/env bash
set -euo pipefail

VALHALLA_URL="${VALHALLA_URL:-http://localhost:8002}"
PAYLOAD="${1:-infra/valhalla/custom_files/motorcycle_route_sample.json}"

curl \
  --fail \
  --silent \
  --show-error \
  --request POST \
  --header "Content-Type: application/json" \
  --data @"${PAYLOAD}" \
  "${VALHALLA_URL}/route"
