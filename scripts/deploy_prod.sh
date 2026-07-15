#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env.prod" ]]; then
  echo ".env.prod topilmadi. Avval: cp .env.prod.example .env.prod"
  exit 1
fi

docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T web python -m uyjoy_etl.cli ping-db
curl --fail --silent --show-error http://127.0.0.1:8000/health
echo
echo "Deploy tayyor: web=127.0.0.1:8000"
