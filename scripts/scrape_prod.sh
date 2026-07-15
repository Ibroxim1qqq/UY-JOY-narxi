#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MAX_PAGES="${MAX_PAGES:-25}"
MAX_VISIBLE="${MAX_VISIBLE:-1000}"

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T web \
  python -m uyjoy_etl.cli scrape-discovered --max-pages "$MAX_PAGES" --max-visible "$MAX_VISIBLE"
