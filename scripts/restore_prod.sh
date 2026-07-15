#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -ne 1 ]]; then
  echo "Ishlatish: scripts/restore_prod.sh backups/uyjoy_olx_YYYYMMDD_HHMMSS.dump"
  exit 1
fi

if [[ ! -f ".env.prod" ]]; then
  echo ".env.prod topilmadi."
  exit 1
fi

BACKUP_PATH="$1"
if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "Backup fayl topilmadi: $BACKUP_PATH"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.prod
set +a

docker compose --env-file .env.prod -f docker-compose.prod.yml stop web
docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$BACKUP_PATH"
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d web
echo "Restore tugadi: $BACKUP_PATH"
