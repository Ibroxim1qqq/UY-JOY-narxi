from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg

from uyjoy_etl.category_catalog import category_by_path, category_for_source_path
from uyjoy_etl.db import Database


DEAL_TYPE_FILTERS = {
    "sale": {"label": "Sotuv"},
    "rent": {"label": "Ijara"},
    "exchange": {"label": "Almashuv"},
}


@dataclass(frozen=True)
class ListingFilters:
    """Dashboard search formadan keladigan filterlar."""

    q: str = ""
    category: str = ""
    deal_type: str = ""
    city: str = ""
    district: str = ""
    rooms: str = ""
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    page: int = 1
    per_page: int = 25

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


@dataclass(frozen=True)
class SearchResult:
    listings: list[dict[str, Any]]
    total: int
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        if self.total == 0:
            return 1
        return ((self.total - 1) // self.per_page) + 1


class ListingRepository:
    """`olx_listing_raw` jadvali uchun read-only querylar."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def search(self, filters: ListingFilters) -> SearchResult:
        where_sql, params = self._build_where_clause(filters)
        params.update({"limit": filters.per_page, "offset": filters.offset})

        with self._database.connect() as conn:
            total_row = conn.execute(
                f"select count(*) as total from olx_listing_raw {where_sql}",
                params,
            ).fetchone()
            rows = conn.execute(
                f"""
                select
                    olx_id,
                    listing_url,
                    source_category_path,
                    title,
                    description,
                    price_display,
                    price_value,
                    currency_code,
                    city_name,
                    district_name,
                    region_name,
                    contact_phone,
                    contact_name,
                    created_time,
                    last_refresh_time,
                    last_seen_at,
                    param_values
                from olx_listing_raw
                {where_sql}
                order by coalesce(last_refresh_time, created_time, last_seen_at) desc nulls last
                limit %(limit)s offset %(offset)s
                """,
                params,
            ).fetchall()

        listings = [self._format_listing_row(dict(row)) for row in rows]
        return SearchResult(
            listings=listings,
            total=int(total_row["total"]),
            page=filters.page,
            per_page=filters.per_page,
        )

    def get_listing(self, olx_id: int) -> dict[str, Any] | None:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                select *
                from olx_listing_raw
                where olx_id = %s
                """,
                (olx_id,),
            ).fetchone()

        if not row:
            return None

        listing = dict(row)
        listing["category_label"] = self._category_label(listing.get("source_category_path"))
        listing["area_display"] = self._area_display(listing.get("param_values") or {})
        listing["raw_payload_pretty"] = json.dumps(
            listing.get("raw_detail") or listing.get("raw_listing") or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        return listing

    def get_facets(self) -> dict[str, list[dict[str, Any]]]:
        with self._database.connect() as conn:
            categories = conn.execute(
                """
                select source_category_path as value, count(*) as count
                from olx_listing_raw
                group by source_category_path
                order by count(*) desc, source_category_path
                """
            ).fetchall()
            cities = conn.execute(
                """
                select city_name as value, count(*) as count
                from olx_listing_raw
                where city_name is not null and city_name <> ''
                group by city_name
                order by count(*) desc, city_name
                limit 100
                """
            ).fetchall()
            districts = conn.execute(
                """
                select district_name as value, count(*) as count
                from olx_listing_raw
                where district_name is not null and district_name <> ''
                group by district_name
                order by count(*) desc, district_name
                limit 200
                """
            ).fetchall()
            rooms = conn.execute(
                """
                with normalized_rooms as (
                    select
                        case when room_count >= 7 then '7plus' else room_count::text end as value,
                        case when room_count >= 7 then 7 else room_count end as sort_order
                    from olx_listing_raw
                    where room_count is not null
                )
                select value, count(*) as count
                from normalized_rooms
                group by value, sort_order
                order by sort_order
                """
            ).fetchall()
            deal_type_counts = conn.execute(
                """
                select
                    count(*) filter (where deal_type = 'sale') as sale,
                    count(*) filter (where deal_type = 'rent') as rent,
                    count(*) filter (where deal_type = 'exchange') as exchange
                from olx_listing_raw
                """
            ).fetchone()

        category_facets: dict[str, dict[str, Any]] = {}
        for row in categories:
            source_path = row["value"]
            category = category_for_source_path(source_path)
            value = category.path if category else source_path
            label = category.name if category else source_path
            if value not in category_facets:
                category_facets[value] = {"value": value, "label": label, "count": 0}
            category_facets[value]["count"] += int(row["count"])

        return {
            "deal_types": [
                {
                    "value": key,
                    "label": config["label"],
                    "count": int(deal_type_counts[key] or 0),
                }
                for key, config in DEAL_TYPE_FILTERS.items()
            ],
            "categories": sorted(
                category_facets.values(),
                key=lambda item: (-int(item["count"]), str(item["label"])),
            ),
            "cities": [dict(row) for row in cities],
            "districts": [dict(row) for row in districts],
            "rooms": [
                {
                    "value": row["value"],
                    "label": "7+" if row["value"] == "7plus" else row["value"],
                    "count": row["count"],
                }
                for row in rooms
            ],
        }

    def get_stats(self) -> dict[str, Any]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                select
                    count(*) as total_listings,
                    count(distinct source_category_path) as categories_count,
                    count(distinct city_name) filter (where city_name is not null) as cities_count,
                    max(last_seen_at) as last_seen_at
                from olx_listing_raw
                """
            ).fetchone()

        return dict(row)

    def iter_powerbi_rows(self) -> list[dict[str, Any]]:
        """Power BI uchun kontaktlarsiz, analizga qulay yassi dataset qaytaradi."""

        with self._database.connect() as conn:
            rows = conn.execute(
                """
                select
                    olx_id,
                    listing_code,
                    listing_url,
                    title,
                    source_category_path,
                    deal_type,
                    price_value,
                    currency_code,
                    is_price_negotiable,
                    city_name,
                    district_name,
                    region_name,
                    room_count,
                    param_values -> 'total_area' ->> 'normalizedValue' as total_area,
                    param_values -> 'land_area' ->> 'normalizedValue' as land_area,
                    param_values -> 'floor' ->> 'normalizedValue' as floor,
                    param_values -> 'total_floors' ->> 'normalizedValue' as total_floors,
                    seller_type,
                    is_business,
                    created_time,
                    last_refresh_time,
                    last_seen_at
                from olx_listing_raw
                order by coalesce(last_refresh_time, created_time, last_seen_at) desc nulls last
                """
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["category_label"] = self._category_label(item.get("source_category_path"))
            result.append(item)
        return result

    def _build_where_clause(self, filters: ListingFilters) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}

        if filters.q:
            params["q"] = f"%{filters.q}%"
            clauses.append(
                """
                (
                    title ilike %(q)s
                    or description ilike %(q)s
                    or city_name ilike %(q)s
                    or district_name ilike %(q)s
                    or region_name ilike %(q)s
                    or listing_url ilike %(q)s
                    or contact_phone ilike %(q)s
                )
                """
            )

        if filters.category:
            params["category"] = filters.category
            if category_by_path(filters.category):
                params["category_prefix"] = filters.category.rstrip("/") + "/%"
                clauses.append(
                    "(source_category_path = %(category)s or source_category_path like %(category_prefix)s)"
                )
            else:
                clauses.append("source_category_path = %(category)s")

        if filters.deal_type in DEAL_TYPE_FILTERS:
            params["deal_type"] = filters.deal_type
            clauses.append("deal_type = %(deal_type)s")

        if filters.city:
            params["city"] = filters.city
            clauses.append("city_name = %(city)s")

        if filters.district:
            params["district"] = filters.district
            clauses.append("district_name = %(district)s")

        if filters.rooms == "7plus":
            clauses.append("room_count >= 7")
        elif filters.rooms.isdigit():
            params["rooms"] = int(filters.rooms)
            clauses.append("room_count = %(rooms)s")

        if filters.price_min is not None:
            params["price_min"] = filters.price_min
            clauses.append("price_value >= %(price_min)s")

        if filters.price_max is not None:
            params["price_max"] = filters.price_max
            clauses.append("price_value <= %(price_max)s")

        if not clauses:
            return "", params
        return "where " + " and ".join(clauses), params

    def _format_listing_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["category_label"] = self._category_label(row.get("source_category_path"))
        row["area_display"] = self._area_display(row.get("param_values") or {})
        row["rooms_display"] = self._param_display(row.get("param_values") or {}, "number_of_rooms")
        row["contact_display"] = self._contact_display(row)
        row["short_description"] = self._shorten(row.get("description") or "", max_length=180)
        return row

    def _category_label(self, path: str | None) -> str:
        if not path:
            return ""
        category = category_for_source_path(path)
        return category.name if category else path

    def _area_display(self, params: dict[str, Any]) -> str:
        for key in ("total_area", "land_area", "total_living_area"):
            raw_value = self._param_display(params, key)
            if raw_value:
                return raw_value
        return ""

    def _param_display(self, params: dict[str, Any], key: str) -> str:
        value = params.get(key) or {}
        raw_value = value.get("value") or value.get("normalizedValue")
        if raw_value not in (None, ""):
            return str(raw_value).strip()
        return ""

    def _contact_display(self, row: dict[str, Any]) -> str:
        phone = row.get("contact_phone")
        if not phone:
            return ""
        name = row.get("contact_name")
        return f"{name}: {phone}" if name else str(phone)

    def _shorten(self, value: str, max_length: int) -> str:
        clean_value = " ".join(value.split())
        if len(clean_value) <= max_length:
            return clean_value
        return clean_value[: max_length - 1].rstrip() + "..."


def parse_decimal(value: str | None) -> Decimal | None:
    """Form inputdan kelgan narxni Decimalga aylantiradi."""

    if not value:
        return None
    normalized = value.replace(" ", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def is_missing_table_error(exc: Exception) -> bool:
    return isinstance(exc, psycopg.errors.UndefinedTable)
