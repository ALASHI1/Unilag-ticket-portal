#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
PNG_B64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9jv1QAAAAASUVORK5CYII="

echo "Health check"
curl -s "$BASE_URL/api/v1/health"
printf "\n\n"

echo "Node A entry event"
curl -s -X POST "$BASE_URL/api/v1/log_event" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "A",
    "timestamp": 1000,
    "plate_text_override": "LAG123AA",
    "plate_image_base64": "'"$PNG_B64"'"
  }'
printf "\n\n"

echo "Node B exit event"
curl -s -X POST "$BASE_URL/api/v1/log_event" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "B",
    "timestamp": 1005,
    "plate_text_override": "LAG123AA",
    "plate_image_base64": "'"$PNG_B64"'"
  }'
printf "\n\n"

echo "Gate check"
curl -s "$BASE_URL/api/v1/check_ticket?plate=LAG123AA"
printf "\n\n"

echo "Ticket list"
curl -s "$BASE_URL/api/v1/tickets"
printf "\n"
