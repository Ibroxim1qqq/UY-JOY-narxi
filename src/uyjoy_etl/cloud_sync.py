from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from uyjoy_etl.cloud_export import export_cloud_csv, import_cloud_csv, upsert_cloud_csv
from uyjoy_etl.config import DatabaseConfig
from uyjoy_etl.db import Database
from uyjoy_etl.unified_listings import refresh_unified_listings

TELEGRAM_TABLES = (
    "telegram_channels",
    "telegram_posts",
    "telegram_real_estate_posts",
)

REAL_ESTATE_LISTING_COLUMNS = (
    "source",
    "source_listing_id",
    "listing_code",
    "source_url",
    "source_name",
    "source_category",
    "title",
    "description",
    "property_type",
    "deal_type",
    "price_display",
    "price_value",
    "currency_code",
    "is_price_negotiable",
    "city_name",
    "district_name",
    "region_name",
    "neighborhood",
    "address",
    "latitude",
    "longitude",
    "room_count",
    "floor_number",
    "total_floors",
    "area_m2",
    "land_sotix",
    "seller_type",
    "is_business",
    "has_media",
    "views",
    "quality_status",
    "quality_reasons",
    "posted_at",
    "first_seen_at",
    "last_seen_at",
    "updated_at",
)


def sync_cloud_database(
    local_database: Database,
    cloud_database_url: str,
    schema_path: Path,
    csv_path: Path,
    *,
    full_sync: bool = False,
    olx_updated_since_days: int = 3,
) -> dict[str, int]:
    """Lokal warehouse datani cloud Postgresga yuboradi.

    Render dashboard Neon database'dan o'qiydi. Shuning uchun kodni redeploy
    qilmasdan sayt yangilanishi uchun daily ETL oxirida shu sync ishlaydi.
    """

    cloud_database = Database(
        DatabaseConfig(
            host="",
            port=5432,
            database="",
            user="",
            password="",
            connection_url=cloud_database_url,
        )
    )

    olx_rows = export_cloud_csv(
        local_database,
        csv_path,
        updated_since_days=None if full_sync else olx_updated_since_days,
    )
    imported_olx_rows = (
        import_cloud_csv(cloud_database, schema_path, csv_path)
        if full_sync
        else upsert_cloud_csv(cloud_database, schema_path, csv_path)
    )
    telegram_counts = _sync_telegram_tables(local_database, cloud_database)
    unified_summary = refresh_unified_listings(cloud_database)

    return {
        "olx_exported": olx_rows,
        "olx_imported": imported_olx_rows,
        "unified_total": unified_summary.total_rows,
        "unified_olx": unified_summary.olx_rows,
        "unified_telegram": unified_summary.telegram_rows,
        **telegram_counts,
    }


def sync_dashboard_database(
    local_database: Database,
    cloud_database_url: str,
    schema_path: Path,
) -> dict[str, int]:
    """Render dashboard uchun faqat tayyor warehouse jadvalini cloudga yuboradi.

    Neon free tierda katta raw JSON jadvallar tez joy egallaydi. Web dashboard,
    Power BI va analytics sahifalar esa `real_estate_listings` jadvalidan
    o'qiydi, shuning uchun deploy uchun shu yengil sync yetarli.
    """

    cloud_database = Database(
        DatabaseConfig(
            host="",
            port=5432,
            database="",
            user="",
            password="",
            connection_url=cloud_database_url,
        )
    )

    cloud_database.run_schema(schema_path)
    with cloud_database.connect() as target:
        target.execute("drop index if exists idx_re_listings_desc_trgm")
        target.execute(
            "truncate table real_estate_listings, olx_listing_raw, telegram_real_estate_posts, "
            "telegram_posts, telegram_channels restart identity cascade"
        )
        target.commit()

    rows = _copy_real_estate_listings(local_database, cloud_database)
    return {"dashboard_rows": rows}


def _copy_real_estate_listings(local_database: Database, cloud_database: Database) -> int:
    columns_sql = ", ".join(f'"{column}"' for column in REAL_ESTATE_LISTING_COLUMNS)
    placeholders = ", ".join(["%s"] * len(REAL_ESTATE_LISTING_COLUMNS))
    insert_sql = f'insert into real_estate_listings ({columns_sql}) values ({placeholders})'

    total = 0
    batch: list[tuple[Any, ...]] = []
    with local_database.connect() as source, cloud_database.connect() as target:
        with source.cursor(name="sync_real_estate_listings", row_factory=dict_row) as cursor:
            cursor.itersize = 1000
            cursor.execute(f"select {columns_sql} from real_estate_listings order by id")
            for row in cursor:
                batch.append(
                    tuple(
                        _adapt_dashboard_value(column, row[column])
                        for column in REAL_ESTATE_LISTING_COLUMNS
                    )
                )
                if len(batch) >= 1000:
                    total += _insert_batch(target, insert_sql, batch)
                    target.commit()
                    batch.clear()

        if batch:
            total += _insert_batch(target, insert_sql, batch)
            target.commit()

    return total


def _adapt_dashboard_value(column: str, value: Any) -> Any:
    if column == "quality_reasons":
        return _adapt_value(value, True)
    if column == "description" and isinstance(value, str):
        return value[:800]
    return value


def _sync_telegram_tables(local_database: Database, cloud_database: Database) -> dict[str, int]:
    counts: dict[str, int] = {}

    with local_database.connect() as source, cloud_database.connect() as target:
        target.execute(
            "truncate table telegram_real_estate_posts, telegram_posts, telegram_channels "
            "restart identity cascade"
        )
        target.commit()

        for table in TELEGRAM_TABLES:
            counts[table] = _copy_table(source, target, table)
            target.commit()

        _reset_sequence(target, "telegram_posts", "id")
        _reset_sequence(target, "telegram_real_estate_posts", "id")
        target.commit()

    return counts


def _copy_table(source: psycopg.Connection, target: psycopg.Connection, table: str) -> int:
    columns, json_columns = _columns_and_json_columns(source, table)
    if not columns:
        return 0

    column_sql = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f'insert into "{table}" ({column_sql}) values ({placeholders})'

    total = 0
    batch: list[tuple[Any, ...]] = []
    with source.cursor(name=f"sync_{table}", row_factory=dict_row) as cursor:
        cursor.itersize = 1000
        cursor.execute(f'select {column_sql} from "{table}" order by 1')
        for row in cursor:
            batch.append(tuple(_adapt_value(row[column], column in json_columns) for column in columns))
            if len(batch) >= 1000:
                total += _insert_batch(target, insert_sql, batch)
                batch.clear()

    if batch:
        total += _insert_batch(target, insert_sql, batch)

    return total


def _columns_and_json_columns(conn: psycopg.Connection, table: str) -> tuple[list[str], set[str]]:
    rows = conn.execute(
        """
        select column_name, udt_name
        from information_schema.columns
        where table_schema = 'public' and table_name = %s
        order by ordinal_position
        """,
        (table,),
    ).fetchall()
    columns = [row["column_name"] for row in rows]
    json_columns = {row["column_name"] for row in rows if row["udt_name"] in {"json", "jsonb"}}
    return columns, json_columns


def _adapt_value(value: Any, is_json: bool) -> Any:
    if value is not None and is_json:
        return Jsonb(value)
    return value


def _insert_batch(conn: psycopg.Connection, insert_sql: str, batch: list[tuple[Any, ...]]) -> int:
    with conn.cursor() as cursor:
        cursor.executemany(insert_sql, batch)
    return len(batch)


def _reset_sequence(conn: psycopg.Connection, table: str, column: str) -> None:
    conn.execute(
        f"""
        select setval(
            pg_get_serial_sequence(%s, %s),
            coalesce((select max("{column}") from "{table}"), 1),
            true
        )
        """,
        (table, column),
    )
