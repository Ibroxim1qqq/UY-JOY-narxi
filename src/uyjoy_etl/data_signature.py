from __future__ import annotations

import json
import sys

from uyjoy_etl.config import load_config
from uyjoy_etl.db import Database


def get_data_signature(database: Database) -> dict[str, object]:
    with database.connect() as conn:
        return dict(
            conn.execute(
                """
                select
                    (select count(*) from public.olx_listing_raw) as olx_count,
                    (select coalesce(max(updated_at), 'epoch'::timestamptz)::text from public.olx_listing_raw) as olx_updated_at,
                    (select count(*) from public.telegram_posts) as telegram_post_count,
                    (select coalesce(max(updated_at), 'epoch'::timestamptz)::text from public.telegram_posts) as telegram_updated_at,
                    (select count(*) from public.telegram_real_estate_posts) as telegram_clean_count,
                    (select coalesce(max(updated_at), 'epoch'::timestamptz)::text from public.telegram_real_estate_posts) as telegram_clean_updated_at,
                    (select count(*) from public.real_estate_listings) as unified_count,
                    (select coalesce(max(updated_at), 'epoch'::timestamptz)::text from public.real_estate_listings) as unified_updated_at
                """
            ).fetchone()
        )


def main() -> int:
    config = load_config()
    database = Database(config.database)
    signature = get_data_signature(database)
    print(json.dumps(signature, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
