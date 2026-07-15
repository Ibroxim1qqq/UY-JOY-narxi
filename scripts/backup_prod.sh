#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env.prod" ]]; then
  echo ".env.prod topilmadi."
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.prod
set +a

mkdir -p backups
BACKUP_PATH="backups/uyjoy_olx_$(date +%Y%m%d_%H%M%S).dump"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

docker compose --env-file .env.prod -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$BACKUP_PATH"

find backups -type f -name "uyjoy_olx_*.dump" -mtime +"$RETENTION_DAYS" -delete
echo "Backup tayyor: $BACKUP_PATH"
