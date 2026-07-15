from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from uyjoy_etl.db import Database

CLOUD_COLUMNS = (
    "olx_id",
    "listing_url",
    "source_category_path",
    "source_page",
    "category_id",
    "category_type",
    "title",
    "description",
    "price_display",
    "price_value",
    "currency_code",
    "is_price_negotiable",
    "city_name",
    "district_name",
    "region_name",
    "location_path",
    "latitude",
    "longitude",
    "seller_id",
    "seller_name",
    "seller_type",
    "is_business",
    "contact_phone",
    "contact_name",
    "contact_source",
    "contact_raw",
    "contact_imported_at",
    "contact_updated_at",
    "created_time",
    "last_refresh_time",
    "pushup_time",
    "valid_to_time",
    "is_active",
    "status",
    "raw_params",
    "param_values",
    "raw_photos",
    "raw_listing",
    "raw_detail",
    "content_hash",
    "first_seen_at",
    "last_seen_at",
    "detail_fetched_at",
    "updated_at",
    "phone_number",
)


def export_cloud_csv(database: Database, csv_path: Path) -> int:
    """Cloud warehouse uchun yengil CSV tayyorlaydi.

    Lokal raw datada katta JSON va foto ro'yxatlar qoladi; cloudga esa dashboard
    va Power BI ishlashi uchun kerak bo'lgan ustunlar chiqadi.
    """

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    query = """
        select
            olx_id,
            listing_url,
            source_category_path,
            source_page,
            category_id,
            category_type,
            title,
            description,
            price_display,
            price_value,
            currency_code,
            is_price_negotiable,
            city_name,
            district_name,
            region_name,
            location_path,
            latitude,
            longitude,
            seller_id,
            null::text as seller_name,
            seller_type,
            is_business,
            null::text as contact_phone,
            null::text as contact_name,
            null::text as contact_source,
            '{}'::jsonb as contact_raw,
            null::timestamptz as contact_imported_at,
            null::timestamptz as contact_updated_at,
            created_time,
            last_refresh_time,
            pushup_time,
            valid_to_time,
            is_active,
            status,
            '[]'::jsonb as raw_params,
            param_values,
            '[]'::jsonb as raw_photos,
            '{}'::jsonb as raw_listing,
            null::jsonb as raw_detail,
            content_hash,
            first_seen_at,
            last_seen_at,
            detail_fetched_at,
            updated_at,
            null::text as phone_number
        from olx_listing_raw
        order by olx_id
    """
    with database.connect() as conn, csv_path.open("w", encoding="utf-8", newline="") as file:
        rows = conn.execute(query).fetchall()
        writer = csv.DictWriter(file, fieldnames=CLOUD_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in CLOUD_COLUMNS})
    return len(rows)


def import_cloud_csv(database: Database, schema_path: Path, csv_path: Path) -> int:
    """Cloud Postgresga schema yaratib, yengil CSV datani import qiladi."""

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV topilmadi: {csv_path}")

    database.run_schema(schema_path)
    with database.connect() as conn, csv_path.open("r", encoding="utf-8", newline="") as file:
        rows = csv.DictReader(file)
        records = [_record_from_row(row) for row in rows]
        conn.execute("truncate table olx_fetch_logs, etl_runs, olx_listing_raw restart identity cascade")
        if records:
            placeholders = ", ".join([f"%({column})s" for column in CLOUD_COLUMNS])
            columns = ", ".join(CLOUD_COLUMNS)
            with conn.cursor() as cur:
                cur.executemany(
                    f"insert into olx_listing_raw ({columns}) values ({placeholders})",
                    records,
                )
        conn.commit()
    return len(records)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _record_from_row(row: dict[str, str]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for column in CLOUD_COLUMNS:
        value = row.get(column) or None
        if column in {"raw_params", "param_values", "raw_photos", "raw_listing", "raw_detail", "contact_raw"}:
            record[column] = Jsonb(_json_value(column, value))
        elif column in {"olx_id", "source_page", "category_id", "seller_id"}:
            record[column] = int(value) if value else None
        elif column in {"price_value", "latitude", "longitude"}:
            record[column] = value
        elif column in {"is_price_negotiable", "is_business", "is_active"}:
            record[column] = _bool_value(value)
        else:
            record[column] = value
    return record


def _bool_value(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"true", "t", "1", "yes"}


def _json_value(column: str, value: str | None) -> Any:
    if not value:
        if column in {"raw_params", "raw_photos"}:
            return []
        if column == "raw_detail":
            return None
        return {}
    return json.loads(value)
