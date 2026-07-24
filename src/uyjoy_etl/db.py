from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from uyjoy_etl.config import DatabaseConfig

logger = logging.getLogger(__name__)


class Database:
    """Postgres bilan ishlash uchun kichik wrapper."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self._config.dsn, connect_timeout=8, row_factory=dict_row)

    def connect_admin(self) -> psycopg.Connection:
        return psycopg.connect(self._config.admin_dsn, autocommit=True, connect_timeout=8, row_factory=dict_row)

    def ensure_database_exists(self) -> None:
        """`POSTGRES_DB` mavjud bo'lmasa yaratadi."""

        if self._config.database_is_managed:
            logger.info("Managed database URL ishlatilmoqda, database yaratish o'tkazib yuborildi.")
            return

        with self.connect_admin() as conn:
            exists = conn.execute(
                "select 1 from pg_database where datname = %s",
                (self._config.database,),
            ).fetchone()
            if exists:
                logger.info("Database mavjud: %s", self._config.database)
                return

            db_name = sql.Identifier(self._config.database)
            conn.execute(sql.SQL("create database {}").format(db_name))
            logger.info("Database yaratildi: %s", self._config.database)

    def run_schema(self, schema_path: Path) -> None:
        """`sql/schema.sql` migration faylini ishlatadi."""

        sql_text = schema_path.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.execute(sql_text)
            conn.commit()
        logger.info("Schema migration bajarildi: %s", schema_path)

    def start_run(
        self,
        source: str,
        categories: tuple[str, ...],
        max_pages_per_category: int,
    ) -> str:
        with self.connect() as conn:
            row = conn.execute(
                """
                insert into etl_runs (source, categories, max_pages_per_category)
                values (%s, %s, %s)
                returning id
                """,
                (source, Jsonb(list(categories)), max_pages_per_category),
            ).fetchone()
            conn.commit()
        run_id = str(row["id"])
        logger.info("ETL run boshlandi | run_id=%s", run_id)
        return run_id

    def finish_run(self, run_id: str, status: str, error_message: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                update etl_runs
                set status = %s,
                    finished_at = now(),
                    error_message = %s
                where id = %s
                """,
                (status, error_message, run_id),
            )
            conn.commit()
        logger.info("ETL run tugadi | run_id=%s | status=%s", run_id, status)

    def increment_run_counters(self, run_id: str, **counters: int) -> None:
        allowed = {
            "pages_processed",
            "listings_seen",
            "detail_pages_fetched",
            "rows_inserted",
            "rows_updated",
        }
        updates = [(key, value) for key, value in counters.items() if key in allowed and value]
        if not updates:
            return

        set_sql = ", ".join(f"{key} = {key} + %s" for key, _ in updates)
        values = [value for _, value in updates]
        values.append(run_id)

        with self.connect() as conn:
            conn.execute(f"update etl_runs set {set_sql} where id = %s", values)
            conn.commit()

    def log_fetch(
        self,
        run_id: str | None,
        url: str,
        http_status: int | None,
        elapsed_ms: int,
        ok: bool,
        error_message: str | None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into olx_fetch_logs
                    (run_id, url, http_status, elapsed_ms, ok, error_message)
                values (%s, %s, %s, %s, %s, %s)
                """,
                (run_id, url, http_status, elapsed_ms, ok, error_message),
            )
            conn.commit()

    def upsert_listing(self, record: dict[str, Any]) -> str:
        """Bitta e'lonni `olx_listing_raw` jadvaliga insert/update qiladi."""

        with self.connect() as conn:
            row = conn.execute(
                """
                insert into olx_listing_raw (
                    olx_id, listing_url, source_category_path, source_page,
                    category_id, category_type, title, description, price_display,
                    price_value, currency_code, is_price_negotiable, city_name,
                    district_name, region_name, location_path, latitude, longitude,
                    seller_id, seller_name, seller_type, is_business, contact_phone,
                    phone_number,
                    contact_name, contact_source, contact_raw, contact_updated_at, created_time,
                    last_refresh_time, pushup_time, valid_to_time, is_active,
                    status, raw_params, param_values, raw_photos, raw_listing,
                    raw_detail, content_hash, detail_fetched_at
                )
                values (
                    %(olx_id)s, %(listing_url)s, %(source_category_path)s, %(source_page)s,
                    %(category_id)s, %(category_type)s, %(title)s, %(description)s,
                    %(price_display)s, %(price_value)s, %(currency_code)s,
                    %(is_price_negotiable)s, %(city_name)s, %(district_name)s,
                    %(region_name)s, %(location_path)s, %(latitude)s, %(longitude)s,
                    %(seller_id)s, %(seller_name)s, %(seller_type)s, %(is_business)s,
                    %(contact_phone)s,
                    case when %(contact_phone)s = 'True' then null else %(contact_phone)s end,
                    %(contact_name)s, %(contact_source)s, %(contact_raw)s,
                    case when %(has_contact)s and %(contact_phone)s <> 'True' then now() else null end,
                    %(created_time)s, %(last_refresh_time)s, %(pushup_time)s,
                    %(valid_to_time)s, %(is_active)s, %(status)s, %(raw_params)s,
                    %(param_values)s, %(raw_photos)s, %(raw_listing)s, %(raw_detail)s,
                    %(content_hash)s,
                    case when %(has_detail)s then now() else null end
                )
                on conflict (olx_id) do update
                set listing_url = excluded.listing_url,
                    source_category_path = excluded.source_category_path,
                    source_page = excluded.source_page,
                    category_id = excluded.category_id,
                    category_type = excluded.category_type,
                    title = excluded.title,
                    description = excluded.description,
                    price_display = excluded.price_display,
                    price_value = excluded.price_value,
                    currency_code = excluded.currency_code,
                    is_price_negotiable = excluded.is_price_negotiable,
                    city_name = excluded.city_name,
                    district_name = excluded.district_name,
                    region_name = excluded.region_name,
                    location_path = excluded.location_path,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    seller_id = excluded.seller_id,
                    seller_name = excluded.seller_name,
                    seller_type = excluded.seller_type,
                    is_business = excluded.is_business,
                    contact_phone = case
                        when excluded.contact_phone is not null and excluded.contact_phone <> 'True' then excluded.contact_phone
                        else olx_listing_raw.contact_phone
                    end,
                    phone_number = case
                        when excluded.contact_phone is not null and excluded.contact_phone <> 'True' then excluded.contact_phone
                        else olx_listing_raw.phone_number
                    end,
                    contact_name = coalesce(excluded.contact_name, olx_listing_raw.contact_name),
                    contact_source = case
                        when excluded.contact_phone is not null and excluded.contact_phone <> 'True' then excluded.contact_source
                        else olx_listing_raw.contact_source
                    end,
                    contact_raw = case
                        when excluded.contact_phone is not null and excluded.contact_phone <> 'True' then excluded.contact_raw
                        else olx_listing_raw.contact_raw
                    end,
                    contact_updated_at = case
                        when excluded.contact_phone is not null and excluded.contact_phone <> 'True' then now()
                        else olx_listing_raw.contact_updated_at
                    end,
                    created_time = excluded.created_time,
                    last_refresh_time = excluded.last_refresh_time,
                    pushup_time = excluded.pushup_time,
                    valid_to_time = excluded.valid_to_time,
                    is_active = excluded.is_active,
                    status = excluded.status,
                    raw_params = excluded.raw_params,
                    param_values = excluded.param_values,
                    raw_photos = excluded.raw_photos,
                    raw_listing = excluded.raw_listing,
                    raw_detail = coalesce(excluded.raw_detail, olx_listing_raw.raw_detail),
                    content_hash = excluded.content_hash,
                    last_seen_at = now(),
                    detail_fetched_at = case
                        when excluded.raw_detail is not null then now()
                        else olx_listing_raw.detail_fetched_at
                    end,
                    updated_at = now()
                returning case when xmax = 0 then 'inserted' else 'updated' end as action
                """,
                {
                    **record,
                    "raw_params": Jsonb(record["raw_params"]),
                    "param_values": Jsonb(record["param_values"]),
                    "raw_photos": Jsonb(record["raw_photos"]),
                    "raw_listing": Jsonb(record["raw_listing"]),
                    "raw_detail": Jsonb(record["raw_detail"]) if record["raw_detail"] else None,
                    "contact_raw": Jsonb(record.get("contact_raw") or {}),
                },
            ).fetchone()
            conn.commit()

        action = row["action"]
        logger.info("Listing saqlandi | action=%s | olx_id=%s", action, record["olx_id"])
        return action

    def ping(self) -> dict[str, Any]:
        with self.connect() as conn:
            return conn.execute(
                "select current_database() as database, current_user as user, now() as server_time"
            ).fetchone()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return value[:2] + "***" + value[-2:] if len(value) > 4 else "***"
