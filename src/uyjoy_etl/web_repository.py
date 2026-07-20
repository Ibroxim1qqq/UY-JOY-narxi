from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
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
PROPERTY_LABELS = {
    "apartment": "Kvartira",
    "house": "Uy / hovli",
    "land": "Yer",
    "garage": "Garaj",
    "commercial": "Tijorat joy",
    "hotel": "Hotel",
    "hostel": "Hostel",
    "sanatorium": "Dam olish joyi",
}
VISIBLE_QUALITY_CLAUSE = "(quality_status is null or quality_status = 'ok')"
USD_TO_UZS_RATE = Decimal("12093.35")


@dataclass(frozen=True)
class ListingFilters:
    """Dashboard search formadan keladigan filterlar."""

    q: str = ""
    source: str = ""
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
class MarketInsightFilters:
    """Analytics sahifasida chartlarni kesimlash uchun filterlar."""

    deal_type: str = ""
    property_type: str = ""
    city: str = ""
    district: str = ""
    rooms: str = ""
    currency_code: str = "UZS"
    metric: str = "auto"
    chart_mode: str = "avg7"
    days: int = 60
    period_mode: str = "all"
    date_from: date | None = None
    date_to: date | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    area_min: Decimal | None = None
    area_max: Decimal | None = None

    @property
    def period_label(self) -> str:
        if self.period_mode == "relative":
            return f"Oxirgi {self.days} kun"
        if self.period_mode == "fixed":
            if self.date_from and self.date_to:
                return f"{self.date_from:%d.%m.%Y} - {self.date_to:%d.%m.%Y}"
            if self.date_from:
                return f"{self.date_from:%d.%m.%Y} dan"
            if self.date_to:
                return f"{self.date_to:%d.%m.%Y} gacha"
        return "Umumiy"


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
    """`real_estate_listings` clean warehouse jadvali uchun read-only querylar."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def search(self, filters: ListingFilters) -> SearchResult:
        where_sql, params = self._build_where_clause(filters)
        params.update({"limit": filters.per_page, "offset": filters.offset})

        with self._database.connect() as conn:
            total_row = conn.execute(
                f"select count(*) as total from real_estate_listings {where_sql}",
                params,
            ).fetchone()
            rows = conn.execute(
                f"""
                select
                    id,
                    source,
                    source_listing_id,
                    listing_code,
                    source_url,
                    source_name,
                    source_category,
                    title,
                    description,
                    price_display,
                    price_value,
                    currency_code,
                    city_name,
                    district_name,
                    region_name,
                    address,
                    room_count,
                    area_m2,
                    land_sotix,
                    posted_at,
                    last_seen_at,
                    quality_status
                from real_estate_listings
                {where_sql}
                order by coalesce(posted_at, last_seen_at, updated_at) desc nulls last
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

    def get_listing(self, listing_id: int) -> dict[str, Any] | None:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                select *
                from real_estate_listings
                where id = %(listing_id)s
                   or (source = 'olx' and source_listing_id = %(listing_id_text)s)
                """,
                {"listing_id": listing_id, "listing_id_text": str(listing_id)},
            ).fetchone()

        if not row:
            return None

        listing = dict(row)
        listing["category_label"] = self._category_label(listing.get("source_category"))
        listing["source_label"] = self._source_label(listing.get("source"), listing.get("source_name"))
        listing["area_display"] = self._area_display_from_columns(listing)
        listing["raw_payload_pretty"] = json.dumps(dict(listing), ensure_ascii=False, indent=2, default=str)
        return listing

    def get_facets(self) -> dict[str, list[dict[str, Any]]]:
        with self._database.connect() as conn:
            sources = conn.execute(
                """
                select source as value, count(*) as count
                from real_estate_listings
                where (quality_status is null or quality_status = 'ok')
                group by source
                order by count(*) desc, source
                """
            ).fetchall()
            categories = conn.execute(
                """
                select source_category as value, count(*) as count
                from real_estate_listings
                where (quality_status is null or quality_status = 'ok')
                group by source_category
                order by count(*) desc, source_category
                """
            ).fetchall()
            cities = conn.execute(
                """
                select city_name as value, count(*) as count
                from real_estate_listings
                where city_name is not null and city_name <> ''
                  and (quality_status is null or quality_status = 'ok')
                group by city_name
                order by count(*) desc, city_name
                limit 100
                """
            ).fetchall()
            districts = conn.execute(
                """
                select district_name as value, count(*) as count
                from real_estate_listings
                where district_name is not null and district_name <> ''
                  and (quality_status is null or quality_status = 'ok')
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
                    from real_estate_listings
                    where room_count is not null
                      and (quality_status is null or quality_status = 'ok')
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
                from real_estate_listings
                where (quality_status is null or quality_status = 'ok')
                """
            ).fetchone()

        category_facets: dict[str, dict[str, Any]] = {}
        for row in categories:
            source_path = row["value"]
            if not source_path:
                continue
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
            "sources": [
                {
                    "value": row["value"],
                    "label": self._source_label(row["value"], None),
                    "count": row["count"],
                }
                for row in sources
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
                    count(distinct source_category) as categories_count,
                    count(distinct city_name) filter (where city_name is not null) as cities_count,
                    max(coalesce(last_seen_at, updated_at)) as last_seen_at
                from real_estate_listings
                where (quality_status is null or quality_status = 'ok')
                """
            ).fetchone()

        return dict(row)

    def get_admin_overview(self) -> dict[str, Any]:
        """Admin panel uchun operatsion metrikalar va chart datasini qaytaradi."""

        with self._database.connect() as conn:
            olx_summary = dict(
                conn.execute(
                    """
                    select
                        count(*) as raw_total,
                        count(*) filter (where quality_status = 'ok' or quality_status is null) as visible_total,
                        count(*) filter (where quality_status = 'suspicious') as suspicious_total,
                        count(*) filter (where first_seen_at >= current_date) as new_today,
                        count(*) filter (where last_seen_at >= current_date) as seen_today,
                        max(last_seen_at) as last_seen_at
                    from real_estate_listings
                    where source = 'olx'
                    """
                ).fetchone()
            )
            telegram_summary = dict(
                conn.execute(
                    """
                    select
                        (select count(*) from telegram_posts) as raw_total,
                        count(*) as clean_total,
                        count(*) filter (where quality_status = 'ok' or quality_status is null) as visible_total,
                        count(*) filter (where quality_status = 'suspicious') as suspicious_total,
                        count(*) filter (where first_seen_at >= current_date) as clean_updated_today,
                        max(updated_at) as last_clean_at
                    from real_estate_listings
                    where source = 'telegram'
                    """
                ).fetchone()
            )
            fetch_summary = dict(
                conn.execute(
                    """
                    select
                        count(*) filter (where fetched_at >= current_date) as requests_today,
                        count(*) filter (where fetched_at >= current_date and ok is false) as failed_today,
                        max(fetched_at) as last_fetch_at
                    from olx_fetch_logs
                    """
                ).fetchone()
            )
            daily_flow = [dict(row) for row in conn.execute(
                """
                with days as (
                    select generate_series(
                        current_date - interval '6 days',
                        current_date,
                        interval '1 day'
                    )::date as day
                )
                select
                    to_char(days.day, 'DD.MM') as label,
                    count(raw.id) filter (where raw.first_seen_at::date = days.day) as olx_count,
                    (
                        select count(*)
                        from real_estate_listings listings
                        where listings.source = 'telegram'
                          and listings.first_seen_at::date = days.day
                    ) as telegram_count
                from days
                left join real_estate_listings raw
                    on raw.first_seen_at::date = days.day
                   and raw.source = 'olx'
                group by days.day
                order by days.day
                """
            ).fetchall()]
            source_breakdown = [dict(row) for row in conn.execute(
                """
                select
                    source,
                    count(*) as total,
                    count(*) filter (where first_seen_at >= current_date) as new_today
                from real_estate_listings
                where quality_status = 'ok' or quality_status is null
                group by source
                order by count(*) desc
                limit 8
                """
            ).fetchall()]
            city_breakdown = [dict(row) for row in conn.execute(
                """
                select city_name, count(*) as total
                from real_estate_listings
                where city_name is not null
                  and city_name <> ''
                  and (quality_status = 'ok' or quality_status is null)
                group by city_name
                order by count(*) desc
                limit 8
                """
            ).fetchall()]
            quality_reasons = [dict(row) for row in conn.execute(
                """
                select reason, count(*) as total
                from (
                    select jsonb_array_elements_text(quality_reasons) as reason
                    from real_estate_listings
                    where quality_status = 'suspicious'
                ) reasons
                group by reason
                order by count(*) desc
                limit 8
                """
            ).fetchall()]
            recent_runs = [dict(row) for row in conn.execute(
                """
                select
                    source,
                    status,
                    started_at,
                    finished_at,
                    listings_seen,
                    rows_inserted,
                    rows_updated,
                    error_message
                from etl_runs
                order by started_at desc
                limit 8
                """
            ).fetchall()]

        for row in source_breakdown:
            row["label"] = self._source_label(row.get("source"), None)

        return {
            "olx": olx_summary,
            "telegram": telegram_summary,
            "fetch": fetch_summary,
            "daily_flow": _with_percent(daily_flow, ("olx_count", "telegram_count")),
            "sources": _with_percent(source_breakdown, ("total",)),
            "cities": _with_percent(city_breakdown, ("total",)),
            "quality_reasons": _with_percent(quality_reasons, ("total",)),
            "recent_runs": recent_runs,
        }

    def get_market_insights(self, filters: MarketInsightFilters | None = None) -> dict[str, Any]:
        """Uy-joy bozori analytics sahifasi uchun source-backed agregat metrikalar."""

        filters = filters or MarketInsightFilters()
        filters = self._normalize_market_filters(filters)
        where_sql, params = self._build_market_where_clause(filters)
        trend = self._market_trend_sql(filters)
        city_expr = self._canonical_city_expr()
        district_expr = self._canonical_district_expr()
        region_expr = self._canonical_region_expr()
        price_uzs_expr = self._price_uzs_expression()
        with self._database.connect() as conn:
            currency_facets = self._get_market_currency_facets(conn, where_sql, params, trend["extra_predicate"])
            filters = self._with_available_currency(filters, currency_facets)
            trend = self._market_trend_sql(filters)
            facets = self._get_market_facets(conn, currency_facets)
            summary = dict(
                conn.execute(
                    f"""
                    select
                        count(*) as total,
                        count(*) filter (where deal_type = 'sale') as sale_total,
                        count(*) filter (where deal_type = 'rent') as rent_total,
                        count(*) filter (where property_type = 'apartment') as apartment_total,
                        count(*) filter (where property_type = 'house') as house_total,
                        count(*) filter (where source = 'olx') as olx_total,
                        count(*) filter (where source = 'telegram') as telegram_total,
                        count(*) filter (where price_value is not null) as priced_total,
                        count(distinct city_name) filter (where city_name is not null and city_name <> '') as city_total,
                        max(coalesce(posted_at, last_seen_at, updated_at)) as freshest_at
                    from real_estate_listings
                    {where_sql}
                    """,
                    params,
                ).fetchone()
            )
            source_mix = [dict(row) for row in conn.execute(
                f"""
                select source, count(*) as total
                from real_estate_listings
                {where_sql}
                group by source
                order by count(*) desc
                """,
                params,
            ).fetchall()]
            deal_mix = [dict(row) for row in conn.execute(
                f"""
                select coalesce(deal_type, 'unknown') as deal_type, count(*) as total
                from real_estate_listings
                {where_sql}
                group by coalesce(deal_type, 'unknown')
                order by count(*) desc
                """,
                params,
            ).fetchall()]
            property_mix = [dict(row) for row in conn.execute(
                f"""
                select coalesce(property_type, 'unknown') as property_type, count(*) as total
                from real_estate_listings
                {where_sql}
                group by coalesce(property_type, 'unknown')
                order by count(*) desc
                limit 10
                """,
                params,
            ).fetchall()]
            top_cities = [dict(row) for row in conn.execute(
                f"""
                select
                    {city_expr} as city_name,
                    count(*) as total,
                    count(*) filter (where deal_type = 'sale') as sale_total,
                    count(*) filter (where deal_type = 'rent') as rent_total,
                    percentile_cont(0.5) within group (order by {price_uzs_expr})
                        filter (where price_value > 0) as median_uzs
                from real_estate_listings
                {where_sql}
                  and city_name is not null
                  and city_name <> ''
                group by {city_expr}
                order by count(*) desc
                limit 10
                """,
                params,
            ).fetchall()]
            top_districts = [dict(row) for row in conn.execute(
                f"""
                select
                    {district_expr} as district_name,
                    count(*) as total,
                    count(*) filter (where deal_type = 'sale') as sale_total,
                    count(*) filter (where deal_type = 'rent') as rent_total
                from real_estate_listings
                {where_sql}
                group by {district_expr}
                order by count(*) desc
                limit 12
                """,
                params,
            ).fetchall()]
            regional_summary = [dict(row) for row in conn.execute(
                f"""
                select
                    {region_expr} as region_name,
                    count(*) as total,
                    count(*) filter (where deal_type = 'sale') as sale_total,
                    count(*) filter (where deal_type = 'rent') as rent_total,
                    count(*) filter (where property_type = 'apartment') as apartment_total,
                    count(*) filter (where property_type = 'house') as house_total,
                    percentile_cont(0.5) within group (order by {price_uzs_expr})
                        filter (where price_value > 0) as median_price
                from real_estate_listings
                {where_sql}
                group by {region_expr}
                order by count(*) desc, {region_expr}
                limit 20
                """,
                params,
            ).fetchall()]
            map_points = [dict(row) for row in conn.execute(
                f"""
                select
                    coalesce(nullif({district_expr}, 'Tuman ko''rsatilmagan'), {city_expr}, 'Noma''lum') as label,
                    avg(latitude)::float as lat,
                    avg(longitude)::float as lon,
                    count(*) as total,
                    count(*) filter (where deal_type = 'sale') as sale_total,
                    count(*) filter (where deal_type = 'rent') as rent_total,
                    percentile_cont(0.5) within group (order by {price_uzs_expr} / nullif(area_m2, 0))
                        filter (
                            where deal_type = 'sale'
                              and area_m2 is not null
                              and area_m2 >= 10
                              and area_m2 <= 1000
                              and price_value is not null
                              and price_value > 0
                        ) as median_sale_m2,
                    percentile_cont(0.5) within group (order by {price_uzs_expr})
                        filter (
                            where deal_type = 'rent'
                              and price_value is not null
                              and price_value > 0
                        ) as median_rent,
                    percentile_cont(0.5) within group (order by {price_uzs_expr})
                        filter (
                            where price_value is not null
                              and price_value > 0
                        ) as median_price
                from real_estate_listings
                {where_sql}
                  and latitude is not null
                  and longitude is not null
                group by coalesce(nullif({district_expr}, 'Tuman ko''rsatilmagan'), {city_expr}, 'Noma''lum')
                order by count(*) desc
                limit 60
                """,
                params,
            ).fetchall()]
            room_mix = [dict(row) for row in conn.execute(
                f"""
                with room_rows as (
                    select
                        case when room_count >= 6 then '6+' else room_count::text end as room_label,
                        case when room_count >= 6 then 6 else room_count end as sort_order
                    from real_estate_listings
                    {where_sql}
                      and room_count is not null
                )
                select room_label, count(*) as total
                from room_rows
                group by room_label, sort_order
                order by sort_order
                """,
                params,
            ).fetchall()]
            area_bands = [dict(row) for row in conn.execute(
                f"""
                with banded as (
                    select
                        case
                            when area_m2 < 40 then '0-40 m2'
                            when area_m2 < 60 then '40-60 m2'
                            when area_m2 < 80 then '60-80 m2'
                            when area_m2 < 120 then '80-120 m2'
                            else '120+ m2'
                        end as label,
                        case
                            when area_m2 < 40 then 1
                            when area_m2 < 60 then 2
                            when area_m2 < 80 then 3
                            when area_m2 < 120 then 4
                            else 5
                        end as sort_order
                    from real_estate_listings
                    {where_sql}
                      and area_m2 is not null
                      and area_m2 > 0
                )
                select label, count(*) as total
                from banded
                group by label, sort_order
                order by sort_order
                """,
                params,
            ).fetchall()]
            usd_price_bands = [dict(row) for row in conn.execute(
                f"""
                with banded as (
                    select
                        case
                            when {price_uzs_expr} < 500000000 then '< 500 mln'
                            when {price_uzs_expr} < 1000000000 then '500 mln-1 mlrd'
                            when {price_uzs_expr} < 2000000000 then '1-2 mlrd'
                            when {price_uzs_expr} < 5000000000 then '2-5 mlrd'
                            else '5 mlrd+'
                        end as label,
                        case
                            when {price_uzs_expr} < 500000000 then 1
                            when {price_uzs_expr} < 1000000000 then 2
                            when {price_uzs_expr} < 2000000000 then 3
                            when {price_uzs_expr} < 5000000000 then 4
                            else 5
                        end as sort_order
                    from real_estate_listings
                    {where_sql}
                      and price_value is not null
                      and price_value > 0
                )
                select label, count(*) as total
                from banded
                group by label, sort_order
                order by sort_order
                """,
                params,
            ).fetchall()]
            price_summary = [dict(row) for row in conn.execute(
                f"""
                select
                    coalesce(deal_type, 'unknown') as deal_type,
                    'UZS' as currency_code,
                    count(*) as total,
                    percentile_cont(0.5) within group (order by {price_uzs_expr}) as median_price,
                    percentile_cont(0.9) within group (order by {price_uzs_expr}) as p90_price
                from real_estate_listings
                {where_sql}
                  and price_value is not null
                  and price_value > 0
                group by coalesce(deal_type, 'unknown')
                order by coalesce(deal_type, 'unknown')
                """,
                params,
            ).fetchall()]
            price_segment_bars = [dict(row) for row in conn.execute(
                f"""
                with priced as (
                    select
                        case
                            when deal_type = 'sale' and property_type = 'apartment' then 'Kvartira sotuv'
                            when deal_type = 'sale' and property_type = 'house' then 'Hovli sotuv'
                            when deal_type = 'rent' and property_type = 'apartment' then 'Kvartira ijara'
                            when deal_type = 'rent' and property_type = 'house' then 'Hovli ijara'
                        end as segment_label,
                        case
                            when deal_type = 'sale' and property_type = 'apartment' then 1
                            when deal_type = 'sale' and property_type = 'house' then 2
                            when deal_type = 'rent' and property_type = 'apartment' then 3
                            when deal_type = 'rent' and property_type = 'house' then 4
                        end as segment_order,
                        case
                            when deal_type = 'rent' and {price_uzs_expr} < 2000000 then '< 2 mln'
                            when deal_type = 'rent' and {price_uzs_expr} < 5000000 then '2-5 mln'
                            when deal_type = 'rent' and {price_uzs_expr} < 10000000 then '5-10 mln'
                            when deal_type = 'rent' and {price_uzs_expr} < 20000000 then '10-20 mln'
                            when deal_type = 'rent' then '20 mln+'
                            when {price_uzs_expr} < 500000000 then '< 500 mln'
                            when {price_uzs_expr} < 1000000000 then '500 mln-1 mlrd'
                            when {price_uzs_expr} < 2000000000 then '1-2 mlrd'
                            when {price_uzs_expr} < 5000000000 then '2-5 mlrd'
                            else '5 mlrd+'
                        end as band_label,
                        case
                            when deal_type = 'rent' and {price_uzs_expr} < 2000000 then 1
                            when deal_type = 'rent' and {price_uzs_expr} < 5000000 then 2
                            when deal_type = 'rent' and {price_uzs_expr} < 10000000 then 3
                            when deal_type = 'rent' and {price_uzs_expr} < 20000000 then 4
                            when deal_type = 'rent' then 5
                            when {price_uzs_expr} < 500000000 then 1
                            when {price_uzs_expr} < 1000000000 then 2
                            when {price_uzs_expr} < 2000000000 then 3
                            when {price_uzs_expr} < 5000000000 then 4
                            else 5
                        end as band_order
                    from real_estate_listings
                    {where_sql}
                      and deal_type in ('sale', 'rent')
                      and property_type in ('apartment', 'house')
                      and price_value is not null
                      and price_value > 0
                )
                select segment_label, segment_order, band_label, band_order, count(*) as total
                from priced
                where segment_label is not null
                group by segment_label, segment_order, band_label, band_order
                order by segment_order, band_order
                """,
                params,
            ).fetchall()]
            daily_supply = [dict(row) for row in conn.execute(
                f"""
                with days as (
                    select generate_series(
                        current_date - interval '13 days',
                        current_date,
                        interval '1 day'
                    )::date as day
                )
                select
                    to_char(days.day, 'DD.MM') as label,
                    count(listings.id) filter (where listings.source = 'olx') as olx_total,
                    count(listings.id) filter (where listings.source = 'telegram') as telegram_total
                from days
                left join real_estate_listings listings
                    on listings.first_seen_at::date = days.day
                   and ({VISIBLE_QUALITY_CLAUSE})
                group by days.day
                order by days.day
                """
            ).fetchall()]
            market_comparison = self._get_market_comparison(conn, filters)
            trend_rows = self._query_market_trend_rows(conn, where_sql, params, filters, trend)
            segment_trends = [
                self._market_segment_trend(
                    conn,
                    filters,
                    deal_type="sale",
                    property_type="apartment",
                    metric="avg_price_m2",
                    title="Kvartira (sotuv)",
                    badge="SOTUV",
                    accent="green",
                ),
                self._market_segment_trend(
                    conn,
                    filters,
                    deal_type="sale",
                    property_type="house",
                    metric="avg_price_sotix",
                    title="Hovli (sotuv)",
                    badge="SOTUV",
                    accent="green",
                ),
                self._market_segment_trend(
                    conn,
                    filters,
                    deal_type="rent",
                    property_type="apartment",
                    metric="avg_price",
                    title="Kvartira (ijara)",
                    badge="IJARA",
                    accent="blue",
                ),
                self._market_segment_trend(
                    conn,
                    filters,
                    deal_type="rent",
                    property_type="house",
                    metric="avg_price",
                    title="Hovli (ijara)",
                    badge="IJARA",
                    accent="blue",
                ),
            ]

        for row in source_mix:
            row["label"] = self._source_label(row.get("source"), None)
        for row in deal_mix:
            row["label"] = self._deal_label(row.get("deal_type"))
        for row in property_mix:
            row["label"] = self._property_label(row.get("property_type"))
        for row in top_cities:
            row["median_uzs_display"] = self._format_money(row.get("median_uzs"), "UZS")
        for row in regional_summary:
            row["median_display"] = self._format_money(row.get("median_price"), "UZS")
        for row in price_summary:
            row["deal_label"] = self._deal_label(row.get("deal_type"))
            row["median_display"] = self._format_money(row.get("median_price"), row.get("currency_code"))
            row["p90_display"] = self._format_money(row.get("p90_price"), row.get("currency_code"))
        segment_price_cards = [
            {
                "title": row["title"],
                "badge": row["badge"],
                "accent": row["accent"],
                "metric_label": row["chart"]["metric_label"],
                "average_display": row["chart"]["average_display"],
                "latest_display": row["chart"]["latest_display"],
                "listing_total": row["listing_total"],
            }
            for row in segment_trends
        ]
        price_segment_bars = self._prepare_price_segment_bars(price_segment_bars)

        return {
            "filters": filters,
            "facets": facets,
            "summary": summary,
            "source_mix": _with_percent(source_mix, ("total",)),
            "deal_mix": _with_percent(deal_mix, ("total",)),
            "property_mix": _with_percent(property_mix, ("total",)),
            "top_cities": _with_percent(top_cities, ("total",)),
            "top_districts": _with_percent(top_districts, ("total", "sale_total", "rent_total")),
            "regional_summary": _with_percent(
                regional_summary,
                ("total", "sale_total", "rent_total", "apartment_total", "house_total"),
            ),
            "map": self._prepare_market_map(map_points, filters),
            "room_mix": _with_percent(room_mix, ("total",)),
            "area_bands": _with_percent(area_bands, ("total",)),
            "usd_price_bands": _with_percent(usd_price_bands, ("total",)),
            "price_segment_bars": price_segment_bars,
            "segment_price_cards": segment_price_cards,
            "price_summary": price_summary,
            "daily_supply": _with_percent(daily_supply, ("olx_total", "telegram_total")),
            "market_comparison": market_comparison,
            "price_trend": self._prepare_line_chart(trend_rows, filters, trend["label"]),
            "segment_trends": segment_trends,
            "sale_apartment_m2_trend": self._prepare_line_chart(
                segment_trends[0]["chart"]["raw_rows"],
                segment_trends[0]["filters"],
                segment_trends[0]["chart"]["metric_label"],
            ),
        }

    def iter_powerbi_rows(self) -> list[dict[str, Any]]:
        """Power BI uchun kontaktlarsiz, analizga qulay yassi dataset qaytaradi."""

        with self._database.connect() as conn:
            rows = conn.execute(
                """
                select
                    id,
                    listing_code,
                    source,
                    source_listing_id,
                    source_url,
                    title,
                    source_category,
                    deal_type,
                    price_value,
                    currency_code,
                    is_price_negotiable,
                    city_name,
                    district_name,
                    region_name,
                    room_count,
                    area_m2 as total_area,
                    land_sotix as land_area,
                    floor_number as floor,
                    total_floors,
                    seller_type,
                    is_business,
                    posted_at as created_time,
                    updated_at as last_refresh_time,
                    last_seen_at
                from real_estate_listings
                where (quality_status is null or quality_status = 'ok')
                order by coalesce(posted_at, last_seen_at, updated_at) desc nulls last
                """
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["category_label"] = self._category_label(item.get("source_category"))
            item["source_label"] = self._source_label(item.get("source"), None)
            result.append(item)
        return result

    def iter_looker_listing_rows(self) -> list[dict[str, Any]]:
        """Looker Studio / Google Sheets uchun yengil, kontaktlarsiz CSV dataset."""

        price_uzs_expr = self._price_uzs_expression()
        city_expr = self._canonical_city_expr()
        district_expr = self._canonical_district_expr()
        region_expr = self._canonical_region_expr()
        with self._database.connect() as conn:
            rows = conn.execute(
                f"""
                select
                    id,
                    source,
                    listing_code,
                    source_url,
                    title,
                    property_type,
                    deal_type,
                    {price_uzs_expr} as price_uzs,
                    currency_code as original_currency,
                    price_value as original_price,
                    {region_expr} as region_name,
                    {city_expr} as city_name,
                    {district_expr} as district_name,
                    room_count,
                    area_m2,
                    land_sotix,
                    case
                        when property_type = 'apartment'
                         and area_m2 is not null
                         and area_m2 >= 10
                         and area_m2 <= 1000
                            then {price_uzs_expr} / nullif(area_m2, 0)
                    end as price_per_m2_uzs,
                    case
                        when property_type = 'house'
                         and land_sotix is not null
                         and land_sotix > 0
                         and land_sotix <= 1000
                            then {price_uzs_expr} / nullif(land_sotix, 0)
                    end as price_per_sotix_uzs,
                    coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date as posted_date,
                    coalesce(posted_at, first_seen_at, last_seen_at, updated_at) as posted_at,
                    last_seen_at
                from real_estate_listings
                where (quality_status is null or quality_status = 'ok')
                  and price_value is not null
                  and price_value > 0
                  and (
                      nullif(city_name, '') is not null
                      or nullif(district_name, '') is not null
                      or nullif(address, '') is not null
                  )
                order by coalesce(posted_at, first_seen_at, last_seen_at, updated_at) desc nulls last, id desc
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def iter_looker_daily_metric_rows(
        self,
        *,
        days: int = 180,
        level: str = "city",
        include_rooms: bool = False,
        include_source: bool = False,
    ) -> list[dict[str, Any]]:
        """Looker chartlari uchun kunlik segment metrikalarini oldindan agregatlaydi."""

        days = min(max(days, 14), 365)
        level = level if level in {"region", "city", "district"} else "city"
        price_uzs_expr = self._price_uzs_expression()
        city_expr = self._canonical_city_expr()
        district_expr = self._canonical_district_expr()
        region_expr = self._canonical_region_expr()
        location_select = {
            "region": "region_name",
            "city": "city_name",
            "district": "district_name",
        }[level]
        source_select = "source" if include_source else "'all'::text as source"
        room_select = "room_count" if include_rooms else "null::integer as room_count"
        with self._database.connect() as conn:
            rows = conn.execute(
                f"""
                with base as (
                    select
                        coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date as posted_date,
                        {source_select},
                        property_type,
                        deal_type,
                        {region_expr} as region_name,
                        {city_expr} as city_name,
                        {district_expr} as district_name,
                        {room_select},
                        {price_uzs_expr} as price_uzs,
                        case
                            when property_type = 'apartment'
                             and area_m2 is not null
                             and area_m2 >= 10
                             and area_m2 <= 1000
                                then {price_uzs_expr} / nullif(area_m2, 0)
                        end as price_per_m2_uzs,
                        case
                            when property_type = 'house'
                             and land_sotix is not null
                             and land_sotix > 0
                             and land_sotix <= 1000
                                then {price_uzs_expr} / nullif(land_sotix, 0)
                        end as price_per_sotix_uzs
                    from real_estate_listings
                    where (quality_status is null or quality_status = 'ok')
                      and price_value is not null
                      and price_value > 0
                      and coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date
                            >= current_date - (%(days)s::int * interval '1 day')
                )
                select
                    posted_date,
                    source,
                    property_type,
                    deal_type,
                    {location_select} as location_name,
                    room_count,
                    count(*) as listing_count,
                    avg(price_uzs) as avg_price_uzs,
                    percentile_cont(0.5) within group (order by price_uzs) as median_price_uzs,
                    avg(price_per_m2_uzs) as avg_price_per_m2_uzs,
                    avg(price_per_sotix_uzs) as avg_price_per_sotix_uzs
                from base
                where posted_date is not null
                  and nullif({location_select}, '') is not null
                group by posted_date, source, property_type, deal_type, {location_select}, room_count
                order by posted_date desc, {location_select}, property_type, deal_type
                """
                ,
                {"days": days},
            ).fetchall()
        return [dict(row) for row in rows]

    def _normalize_market_filters(self, filters: MarketInsightFilters) -> MarketInsightFilters:
        metric = filters.metric if filters.metric in {"auto", "avg_price", "avg_price_m2", "avg_price_sotix"} else "auto"
        days = min(max(filters.days, 14), 180)
        period_mode = filters.period_mode if filters.period_mode in {"all", "relative", "fixed"} else "all"
        date_from = filters.date_from
        date_to = filters.date_to
        if period_mode == "fixed" and date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        if period_mode == "fixed" and not date_from and not date_to:
            period_mode = "all"
        return MarketInsightFilters(
            deal_type=filters.deal_type if filters.deal_type in DEAL_TYPE_FILTERS else "",
            property_type=filters.property_type.strip(),
            city=self._canonical_city_value(filters.city),
            district=self._canonical_district_value(filters.district),
            rooms=filters.rooms if filters.rooms == "7plus" or filters.rooms.isdigit() else "",
            currency_code="UZS",
            metric=metric,
            chart_mode=filters.chart_mode if filters.chart_mode in {"avg7", "daily"} else "avg7",
            days=days,
            period_mode=period_mode,
            date_from=date_from,
            date_to=date_to,
            price_min=filters.price_min if filters.price_min is None or filters.price_min >= 0 else None,
            price_max=filters.price_max if filters.price_max is None or filters.price_max >= 0 else None,
            area_min=filters.area_min if filters.area_min is None or filters.area_min >= 0 else None,
            area_max=filters.area_max if filters.area_max is None or filters.area_max >= 0 else None,
        )

    def _build_market_where_clause(self, filters: MarketInsightFilters) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = [VISIBLE_QUALITY_CLAUSE]
        params: dict[str, Any] = {}

        if filters.deal_type:
            params["market_deal_type"] = filters.deal_type
            clauses.append("deal_type = %(market_deal_type)s")

        if filters.property_type:
            params["market_property_type"] = filters.property_type
            clauses.append("property_type = %(market_property_type)s")

        if filters.city:
            params["market_city"] = filters.city
            clauses.append(f"{self._canonical_city_expr()} = %(market_city)s")

        if filters.district:
            params["market_district"] = filters.district
            clauses.append(f"{self._canonical_district_expr()} = %(market_district)s")

        if filters.rooms == "7plus":
            clauses.append("room_count >= 7")
        elif filters.rooms.isdigit():
            params["market_rooms"] = int(filters.rooms)
            clauses.append("room_count = %(market_rooms)s")

        price_uzs_expr = self._price_uzs_expression()
        if filters.price_min is not None:
            params["market_price_min"] = filters.price_min
            clauses.append(f"{price_uzs_expr} >= %(market_price_min)s")

        if filters.price_max is not None:
            params["market_price_max"] = filters.price_max
            clauses.append(f"{price_uzs_expr} <= %(market_price_max)s")

        if filters.area_min is not None:
            params["market_area_min"] = filters.area_min
            clauses.append("area_m2 >= %(market_area_min)s")

        if filters.area_max is not None:
            params["market_area_max"] = filters.area_max
            clauses.append("area_m2 <= %(market_area_max)s")

        listing_date = "coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date"
        if filters.period_mode == "relative":
            params["market_days"] = filters.days
            clauses.append(f"{listing_date} >= current_date - (%(market_days)s::int - 1) * interval '1 day'")
        elif filters.period_mode == "fixed":
            if filters.date_from:
                params["market_date_from"] = filters.date_from
                clauses.append(f"{listing_date} >= %(market_date_from)s")
            if filters.date_to:
                params["market_date_to"] = filters.date_to
                clauses.append(f"{listing_date} <= %(market_date_to)s")

        return "where " + " and ".join(clauses), params

    def _price_uzs_expression(self) -> str:
        """Narx metrikalari uchun hamma valyutani UZS qiymatga keltiradi."""

        return (
            "case "
            f"when currency_code = 'USD' then price_value * {USD_TO_UZS_RATE} "
            "when currency_code in ('UZS', 'SUM') then price_value "
            "else price_value "
            "end"
        )

    def _canonical_city_expr(self) -> str:
        """Lotin/kirill shahar nomlarini bitta dashboard nomiga yig'adi."""

        return """
            case
                when lower(coalesce(city_name, '')) in ('ташкент', 'toshkent', 'tashkent', 'toshkent shahri') then 'Toshkent'
                when lower(coalesce(city_name, '')) like '%%самарканд%%' or lower(coalesce(city_name, '')) like '%%samarqand%%' then 'Samarqand'
                when lower(coalesce(city_name, '')) like '%%чирчик%%' or lower(coalesce(city_name, '')) like '%%chirchiq%%' then 'Chirchiq'
                when lower(coalesce(city_name, '')) like '%%янгиюль%%' or lower(coalesce(city_name, '')) like '%%yangiy%%' then 'Yangiyo''l'
                when lower(coalesce(city_name, '')) like '%%наво%%' or lower(coalesce(city_name, '')) like '%%navo%%' then 'Navoiy'
                when lower(coalesce(city_name, '')) like '%%ферган%%' or lower(coalesce(city_name, '')) like '%%farg%%' then 'Farg''ona'
                when lower(coalesce(city_name, '')) like '%%андижан%%' or lower(coalesce(city_name, '')) like '%%andij%%' then 'Andijon'
                when lower(coalesce(city_name, '')) like '%%наманган%%' or lower(coalesce(city_name, '')) like '%%namang%%' then 'Namangan'
                when lower(coalesce(city_name, '')) like '%%бухар%%' or lower(coalesce(city_name, '')) like '%%buxor%%' then 'Buxoro'
                when lower(coalesce(city_name, '')) like '%%карши%%' or lower(coalesce(city_name, '')) like '%%qarshi%%' then 'Qarshi'
                when lower(coalesce(city_name, '')) like '%%термез%%' or lower(coalesce(city_name, '')) like '%%termiz%%' then 'Termiz'
                when lower(coalesce(city_name, '')) like '%%ургенч%%' or lower(coalesce(city_name, '')) like '%%urganch%%' then 'Urganch'
                when lower(coalesce(city_name, '')) like '%%нукус%%' or lower(coalesce(city_name, '')) like '%%nukus%%' then 'Nukus'
                else coalesce(nullif(city_name, ''), 'Noma''lum')
            end
        """

    def _canonical_region_expr(self) -> str:
        """Viloyat kesimidagi jadval uchun shahar/region nomlarini umumlashtiradi."""

        combined = "lower(coalesce(region_name, '') || ' ' || coalesce(city_name, ''))"
        return f"""
            case
                when {combined} like '%%ташкент%%' or {combined} like '%%toshkent%%' or {combined} like '%%tashkent%%' or {combined} like '%%чирчик%%' or {combined} like '%%chirchiq%%' or {combined} like '%%янгиюль%%' or {combined} like '%%yangiy%%' then 'Toshkent'
                when {combined} like '%%самарканд%%' or {combined} like '%%samarqand%%' then 'Samarqand'
                when {combined} like '%%наво%%' or {combined} like '%%navo%%' then 'Navoiy'
                when {combined} like '%%ферган%%' or {combined} like '%%farg%%' then 'Farg''ona'
                when {combined} like '%%андижан%%' or {combined} like '%%andij%%' then 'Andijon'
                when {combined} like '%%наманган%%' or {combined} like '%%namang%%' then 'Namangan'
                when {combined} like '%%бухар%%' or {combined} like '%%buxor%%' then 'Buxoro'
                when {combined} like '%%кашк%%' or {combined} like '%%qashq%%' or {combined} like '%%карши%%' or {combined} like '%%qarshi%%' then 'Qashqadaryo'
                when {combined} like '%%сурх%%' or {combined} like '%%surx%%' or {combined} like '%%термез%%' or {combined} like '%%termiz%%' then 'Surxondaryo'
                when {combined} like '%%хорезм%%' or {combined} like '%%xorazm%%' or {combined} like '%%ургенч%%' or {combined} like '%%urganch%%' then 'Xorazm'
                when {combined} like '%%нукус%%' or {combined} like '%%qoraqal%%' or {combined} like '%%каракал%%' then 'Qoraqalpog''iston'
                else coalesce(nullif(region_name, ''), {self._canonical_city_expr()}, 'Noma''lum')
            end
        """

    def _canonical_district_expr(self) -> str:
        """Toshkent tumanlarini lotin/kirill variantlaridan bitta nomga keltiradi."""

        source = "lower(coalesce(district_name, ''))"
        return f"""
            case
                when {source} like '%%юнус%%' or {source} like '%%yunus%%' then 'Yunusobod'
                when {source} like '%%мирзо%%' or {source} like '%%ulug%%' then 'Mirzo Ulug''bek'
                when {source} like '%%чилан%%' or {source} like '%%chilon%%' then 'Chilonzor'
                when {source} like '%%мирабад%%' or {source} like '%%mirobod%%' then 'Mirobod'
                when {source} like '%%алмазар%%' or {source} like '%%olmazor%%' then 'Olmazor'
                when {source} like '%%сергел%%' or {source} like '%%sergel%%' then 'Sergeli'
                when {source} like '%%шайхан%%' or {source} like '%%shayxon%%' then 'Shayxontohur'
                when {source} like '%%учтеп%%' or {source} like '%%uchtepa%%' then 'Uchtepa'
                when {source} like '%%яккас%%' or {source} like '%%yakkasaroy%%' then 'Yakkasaroy'
                when {source} like '%%янгиха%%' or {source} like '%%yangihayot%%' then 'Yangihayot'
                when {source} like '%%яшнаб%%' or {source} like '%%yashnobod%%' then 'Yashnobod'
                when {source} like '%%бектем%%' or {source} like '%%bektemir%%' then 'Bektemir'
                else coalesce(nullif(district_name, ''), 'Tuman ko''rsatilmagan')
            end
        """

    def _canonical_city_value(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = value.strip().lower().replace("ё", "е").replace("-", " ")
        if normalized in {"ташкент", "toshkent", "tashkent", "toshkent shahri"}:
            return "Toshkent"
        aliases = (
            (("самарканд", "samarqand"), "Samarqand"),
            (("чирчик", "chirchiq"), "Chirchiq"),
            (("янгиюль", "yangiy"), "Yangiyo'l"),
            (("наво", "navo"), "Navoiy"),
            (("ферган", "farg"), "Farg'ona"),
            (("андижан", "andij"), "Andijon"),
            (("наманган", "namang"), "Namangan"),
            (("бухар", "buxor"), "Buxoro"),
            (("карши", "qarshi"), "Qarshi"),
            (("термез", "termiz"), "Termiz"),
            (("ургенч", "urganch"), "Urganch"),
            (("нукус", "nukus"), "Nukus"),
        )
        for needles, canonical in aliases:
            if any(needle in normalized for needle in needles):
                return canonical
        return value.strip()

    def _canonical_district_value(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = (
            value.strip()
            .lower()
            .replace("ё", "е")
            .replace("'", "")
            .replace("`", "")
            .replace("ʻ", "")
            .replace("’", "")
            .replace("-", " ")
        )
        aliases = (
            (("юнус", "yunus"), "Yunusobod"),
            (("мирзо", "ulug"), "Mirzo Ulug'bek"),
            (("чилан", "chilon"), "Chilonzor"),
            (("мирабад", "mirobod"), "Mirobod"),
            (("алмазар", "olmazor"), "Olmazor"),
            (("сергел", "sergel"), "Sergeli"),
            (("шайхан", "shayxon"), "Shayxontohur"),
            (("учтеп", "uchtepa"), "Uchtepa"),
            (("яккас", "yakkasaroy"), "Yakkasaroy"),
            (("янгиха", "yangihayot"), "Yangihayot"),
            (("яшнаб", "yashnobod"), "Yashnobod"),
            (("бектем", "bektemir"), "Bektemir"),
        )
        for needles, canonical in aliases:
            if any(needle in normalized for needle in needles):
                return canonical
        return value.strip()

    def _get_market_facets(
        self,
        conn: Any,
        currency_facets: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        city_expr = self._canonical_city_expr()
        district_expr = self._canonical_district_expr()
        sources = conn.execute(
            f"""
            select source as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
            group by source
            order by count(*) desc, source
            """
        ).fetchall()
        properties = conn.execute(
            f"""
            select property_type as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
              and property_type is not null
              and property_type <> ''
            group by property_type
            order by count(*) desc, property_type
            """
        ).fetchall()
        cities = conn.execute(
            f"""
            select {city_expr} as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
              and city_name is not null
              and city_name <> ''
            group by {city_expr}
            order by count(*) desc, value
            limit 120
            """
        ).fetchall()
        districts = conn.execute(
            f"""
            select {district_expr} as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
              and district_name is not null
              and district_name <> ''
            group by {district_expr}
            order by count(*) desc, value
            limit 240
            """
        ).fetchall()
        rooms = conn.execute(
            f"""
            with room_rows as (
                select
                    case when room_count >= 7 then '7plus' else room_count::text end as value,
                    case when room_count >= 7 then 7 else room_count end as sort_order
                from real_estate_listings
                where {VISIBLE_QUALITY_CLAUSE}
                  and room_count is not null
            )
            select value, count(*) as count
            from room_rows
            group by value, sort_order
            order by sort_order
            """
        ).fetchall()

        return {
            "deal_types": [
                {
                    "value": key,
                    "label": config["label"],
                }
                for key, config in DEAL_TYPE_FILTERS.items()
            ],
            "property_types": [
                {
                    "value": row["value"],
                    "label": self._property_label(row["value"]),
                    "count": row["count"],
                }
                for row in properties
            ],
            "currencies": currency_facets or [],
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
            "sources": [
                {
                    "value": row["value"],
                    "label": self._source_label(row["value"], None),
                    "count": row["count"],
                }
                for row in sources
            ],
        }

    def _get_market_currency_facets(
        self,
        conn: Any,
        where_sql: str,
        params: dict[str, Any],
        extra_predicate: str = "",
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            select
                'UZS' as value,
                count(*) as count,
                count(distinct coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date) as day_count
            from real_estate_listings
            {where_sql}
              and price_value is not null
              and price_value > 0
              {extra_predicate}
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def _with_available_currency(
        self,
        filters: MarketInsightFilters,
        currency_facets: list[dict[str, Any]],
    ) -> MarketInsightFilters:
        return MarketInsightFilters(
            deal_type=filters.deal_type,
            property_type=filters.property_type,
            city=filters.city,
            district=filters.district,
            rooms=filters.rooms,
            currency_code="UZS",
            metric=filters.metric,
            chart_mode=filters.chart_mode,
            days=filters.days,
            period_mode=filters.period_mode,
            date_from=filters.date_from,
            date_to=filters.date_to,
            price_min=filters.price_min,
            price_max=filters.price_max,
            area_min=filters.area_min,
            area_max=filters.area_max,
        )

    def _get_market_comparison(self, conn: Any, filters: MarketInsightFilters) -> dict[str, Any]:
        """4 asosiy segment uchun region/tuman kesimida qimmat-arzon bar chart modeli."""

        comparison_filters = MarketInsightFilters(
            city=filters.city,
            district=filters.district,
            rooms=filters.rooms,
            currency_code="UZS",
            metric=filters.metric,
            chart_mode=filters.chart_mode,
            days=filters.days,
            period_mode=filters.period_mode,
            date_from=filters.date_from,
            date_to=filters.date_to,
            price_min=filters.price_min,
            price_max=filters.price_max,
            area_min=filters.area_min,
            area_max=filters.area_max,
        )
        where_sql, params = self._build_market_where_clause(comparison_filters)
        region_expr = self._canonical_region_expr()
        city_expr = self._canonical_city_expr()
        district_expr = self._canonical_district_expr()
        price_uzs_expr = self._price_uzs_expression()
        segment_case = """
            case
                when deal_type = 'sale' and property_type = 'apartment' then 'apartment_sale'
                when deal_type = 'sale' and property_type = 'house' then 'house_sale'
                when deal_type = 'rent' and property_type = 'apartment' then 'apartment_rent'
                when deal_type = 'rent' and property_type = 'house' then 'house_rent'
            end
        """
        segment_label_case = """
            case
                when deal_type = 'sale' and property_type = 'apartment' then 'Kvartira sotuv'
                when deal_type = 'sale' and property_type = 'house' then 'Hovli sotuv'
                when deal_type = 'rent' and property_type = 'apartment' then 'Kvartira ijara'
                when deal_type = 'rent' and property_type = 'house' then 'Hovli ijara'
            end
        """
        segment_order_case = """
            case
                when deal_type = 'sale' and property_type = 'apartment' then 1
                when deal_type = 'sale' and property_type = 'house' then 2
                when deal_type = 'rent' and property_type = 'apartment' then 3
                when deal_type = 'rent' and property_type = 'house' then 4
            end
        """
        metric_label_case = """
            case
                when deal_type = 'sale' and property_type = 'apartment' then 'O''rtacha m2 narxi'
                when deal_type = 'sale' and property_type = 'house' then 'O''rtacha sotix narxi'
                else 'O''rtacha narx'
            end
        """
        metric_value_case = f"""
            case
                when deal_type = 'sale'
                 and property_type = 'apartment'
                 and area_m2 is not null
                 and area_m2 >= 10
                 and area_m2 <= 1000
                    then {price_uzs_expr} / nullif(area_m2, 0)
                when deal_type = 'sale'
                 and property_type = 'house'
                 and land_sotix is not null
                 and land_sotix > 0
                 and land_sotix <= 1000
                    then {price_uzs_expr} / nullif(land_sotix, 0)
                when deal_type = 'rent' and property_type in ('apartment', 'house')
                    then {price_uzs_expr}
            end
        """
        base_cte = f"""
            with metric_rows as (
                select
                    id,
                    title,
                    source_url,
                    {city_expr} as city_name,
                    {region_expr} as region_name,
                    {district_expr} as district_name,
                    coalesce(nullif(address, ''), nullif({district_expr}, 'Tuman ko''rsatilmagan'), {city_expr}, 'Manzil yo''q') as location_label,
                    {price_uzs_expr} as price_uzs,
                    {segment_case} as segment_key,
                    {segment_label_case} as segment_label,
                    {segment_order_case} as segment_order,
                    {metric_label_case} as metric_label,
                    {metric_value_case} as metric_value,
                    coalesce(posted_at, first_seen_at, last_seen_at, updated_at) as listing_time
                from real_estate_listings
                {where_sql}
                  and deal_type in ('sale', 'rent')
                  and property_type in ('apartment', 'house')
                  and price_value is not null
                  and price_value > 0
            ),
            clean_rows as (
                select *
                from metric_rows
                where segment_key is not null
                  and metric_value is not null
                  and metric_value > 0
            )
        """
        aggregate_rows = [dict(row) for row in conn.execute(
            f"""
            {base_cte}
            select
                segment_key,
                segment_label,
                segment_order,
                metric_label,
                'region' as level,
                region_name as name,
                null::text as parent_name,
                avg(metric_value) as avg_value,
                count(*) as listing_count
            from clean_rows
            group by segment_key, segment_label, segment_order, metric_label, region_name
            union all
            select
                segment_key,
                segment_label,
                segment_order,
                metric_label,
                'district' as level,
                district_name as name,
                region_name as parent_name,
                avg(metric_value) as avg_value,
                count(*) as listing_count
            from clean_rows
            where district_name <> 'Tuman ko''rsatilmagan'
            group by segment_key, segment_label, segment_order, metric_label, region_name, district_name
            order by segment_order, level desc, avg_value desc
            """,
            params,
        ).fetchall()]
        listing_rows = [dict(row) for row in conn.execute(
            f"""
            {base_cte},
            ranked as (
                select
                    segment_key,
                    'region' as level,
                    region_name as name,
                    null::text as parent_name,
                    title,
                    source_url,
                    location_label,
                    price_uzs,
                    metric_label,
                    metric_value,
                    row_number() over (
                        partition by segment_key, region_name
                        order by listing_time desc nulls last, id desc
                    ) as row_no
                from clean_rows
                where source_url is not null and source_url <> ''
                union all
                select
                    segment_key,
                    'district' as level,
                    district_name as name,
                    region_name as parent_name,
                    title,
                    source_url,
                    location_label,
                    price_uzs,
                    metric_label,
                    metric_value,
                    row_number() over (
                        partition by segment_key, region_name, district_name
                        order by listing_time desc nulls last, id desc
                    ) as row_no
                from clean_rows
                where district_name <> 'Tuman ko''rsatilmagan'
                  and source_url is not null
                  and source_url <> ''
            )
            select *
            from ranked
            where row_no <= 8
            order by segment_key, level, name, row_no
            """,
            params,
        ).fetchall()]

        listings_by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in listing_rows:
            key = (
                row.get("segment_key") or "",
                row.get("level") or "",
                row.get("parent_name") or "",
                row.get("name") or "",
            )
            listings_by_key.setdefault(key, []).append(
                {
                    "title": self._shorten(row.get("title") or "E'lon", 90),
                    "url": row.get("source_url") or "",
                    "location": row.get("location_label") or "",
                    "price": self._format_money(row.get("price_uzs"), "UZS"),
                    "metric": self._format_trend_money(
                        float(row.get("metric_value") or 0),
                        "UZS",
                        row.get("metric_label") or "",
                    ),
                }
            )

        segment_map: dict[str, dict[str, Any]] = {}
        for row in aggregate_rows:
            segment_key = row.get("segment_key") or ""
            segment = segment_map.setdefault(
                segment_key,
                {
                    "key": segment_key,
                    "label": row.get("segment_label") or "",
                    "order": int(row.get("segment_order") or 99),
                    "metric_label": row.get("metric_label") or "",
                    "regions": [],
                    "districts": [],
                },
            )
            item_key = (
                segment_key,
                row.get("level") or "",
                row.get("parent_name") or "",
                row.get("name") or "",
            )
            avg_value = float(row.get("avg_value") or 0)
            item = {
                "name": row.get("name") or "Noma'lum",
                "parent": row.get("parent_name") or "",
                "level": row.get("level") or "region",
                "value": round(avg_value, 2),
                "display": self._format_trend_money(avg_value, "UZS", row.get("metric_label") or ""),
                "count": int(row.get("listing_count") or 0),
                "listings": listings_by_key.get(item_key, []),
            }
            if row.get("level") == "district":
                segment["districts"].append(item)
            else:
                segment["regions"].append(item)

        default_segments = [
            ("apartment_sale", "Kvartira sotuv", 1, "O'rtacha m2 narxi"),
            ("house_sale", "Hovli sotuv", 2, "O'rtacha sotix narxi"),
            ("apartment_rent", "Kvartira ijara", 3, "O'rtacha narx"),
            ("house_rent", "Hovli ijara", 4, "O'rtacha narx"),
        ]
        for key, label, order, metric_label in default_segments:
            segment_map.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "order": order,
                    "metric_label": metric_label,
                    "regions": [],
                    "districts": [],
                },
            )

        segments = sorted(segment_map.values(), key=lambda item: item["order"])
        for segment in segments:
            for key in ("regions", "districts"):
                segment[key] = sorted(segment[key], key=lambda item: item["value"], reverse=True)[:12]
        return {"segments": segments}

    def _market_trend_sql(self, filters: MarketInsightFilters) -> dict[str, str]:
        metric = filters.metric
        if metric == "auto" and filters.deal_type == "rent":
            metric = "avg_price"
        elif metric == "auto" and filters.deal_type == "sale" and filters.property_type == "house":
            metric = "avg_price_sotix"
        elif metric == "auto" and filters.property_type == "apartment":
            metric = "avg_price_m2"
        elif metric == "auto":
            metric = "avg_price"

        if metric == "avg_price_m2":
            price_uzs_expr = self._price_uzs_expression()
            return {
                "label": "O'rtacha m2 narxi",
                "value_expression": f"{price_uzs_expr} / nullif(area_m2, 0)",
                "extra_predicate": "and area_m2 is not null and area_m2 >= 10 and area_m2 <= 1000",
            }

        if metric == "avg_price_sotix":
            price_uzs_expr = self._price_uzs_expression()
            return {
                "label": "O'rtacha sotix narxi",
                "value_expression": f"{price_uzs_expr} / nullif(land_sotix, 0)",
                "extra_predicate": "and land_sotix is not null and land_sotix > 0",
            }

        return {
            "label": "O'rtacha narx",
            "value_expression": self._price_uzs_expression(),
            "extra_predicate": "",
        }

    def _market_segment_trend(
        self,
        conn: Any,
        base_filters: MarketInsightFilters,
        *,
        deal_type: str,
        property_type: str,
        metric: str,
        title: str,
        badge: str,
        accent: str,
    ) -> dict[str, Any]:
        segment_filters = MarketInsightFilters(
            deal_type=deal_type,
            property_type=property_type,
            city=base_filters.city,
            district=base_filters.district,
            rooms=base_filters.rooms,
            currency_code=base_filters.currency_code,
            metric=metric,
            chart_mode=base_filters.chart_mode,
            days=base_filters.days,
            period_mode=base_filters.period_mode,
            date_from=base_filters.date_from,
            date_to=base_filters.date_to,
            price_min=base_filters.price_min,
            price_max=base_filters.price_max,
            area_min=base_filters.area_min,
            area_max=base_filters.area_max,
        )
        where_sql, params = self._build_market_where_clause(segment_filters)
        trend = self._market_trend_sql(segment_filters)
        currency_facets = self._get_market_currency_facets(
            conn,
            where_sql,
            params,
            trend["extra_predicate"],
        )
        segment_filters = self._with_available_currency(segment_filters, currency_facets)
        trend = self._market_trend_sql(segment_filters)
        rows = self._query_market_trend_rows(conn, where_sql, params, segment_filters, trend)
        chart = self._prepare_line_chart(rows, segment_filters, trend["label"])
        chart["raw_rows"] = rows
        listing_total = sum(int(row.get("listing_count") or 0) for row in rows)
        return {
            "title": title,
            "badge": badge,
            "accent": accent,
            "filters": segment_filters,
            "chart": chart,
            "listing_total": listing_total,
        }

    def _prepare_market_map(
        self,
        points: list[dict[str, Any]],
        filters: MarketInsightFilters,
    ) -> dict[str, Any]:
        metric_field = "median_rent" if filters.deal_type == "rent" else "median_sale_m2"
        metric_label = "Ijara median narxi" if filters.deal_type == "rent" else "Sotuv median m2 narxi"
        metric_suffix = "" if filters.deal_type == "rent" else " / m2"

        district_metrics: list[dict[str, Any]] = []
        clean_points = [
            {
                "label": row.get("label") or "Noma'lum",
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "total": int(row.get("total") or 0),
                "sale_total": int(row.get("sale_total") or 0),
                "rent_total": int(row.get("rent_total") or 0),
                "metric_value": float(row.get(metric_field) or row.get("median_price") or 0),
                "metric_display": self._format_trend_money(
                    float(row.get(metric_field) or row.get("median_price") or 0),
                    filters.currency_code,
                    metric_label,
                )
                if (row.get(metric_field) or row.get("median_price"))
                else "-",
            }
            for row in points
            if row.get("lat") is not None and row.get("lon") is not None
        ]
        for point in clean_points:
            district_key = self._tashkent_district_key(point["label"])
            if district_key and point["metric_value"] > 0:
                district_metrics.append(
                    {
                        "key": district_key,
                        "label": point["label"],
                        "total": point["total"],
                        "sale_total": point["sale_total"],
                        "rent_total": point["rent_total"],
                        "metric_value": point["metric_value"],
                        "metric_display": point["metric_display"],
                    }
                )

        metric_values = [row["metric_value"] for row in district_metrics if row["metric_value"] > 0]
        min_metric = min(metric_values) if metric_values else None
        max_metric = max(metric_values) if metric_values else None
        if clean_points:
            center_lat = sum(point["lat"] for point in clean_points) / len(clean_points)
            center_lon = sum(point["lon"] for point in clean_points) / len(clean_points)
            zoom = 12 if filters.district else 11 if filters.city else 6
        elif filters.city == "Ташкент":
            center_lat, center_lon, zoom = 41.2995, 69.2401, 11
        else:
            center_lat, center_lon, zoom = 41.3111, 64.2797, 6

        return {
            "points": clean_points,
            "districts": district_metrics,
            "center_lat": round(center_lat, 6),
            "center_lon": round(center_lon, 6),
            "zoom": zoom,
            "geojson_url": "/static/tashkent_districts.geojson",
            "metric_label": metric_label,
            "metric_suffix": metric_suffix,
            "currency_code": filters.currency_code,
            "min_display": self._format_trend_money(min_metric, filters.currency_code, metric_label)
            if min_metric is not None
            else "-",
            "max_display": self._format_trend_money(max_metric, filters.currency_code, metric_label)
            if max_metric is not None
            else "-",
        }

    def _tashkent_district_key(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = (
            value.lower()
            .replace("ё", "е")
            .replace("'", "")
            .replace("`", "")
            .replace("ʻ", "")
            .replace("’", "")
            .replace("-", " ")
        )
        for removable in (" district", " tumani", "ский район", " район"):
            normalized = normalized.replace(removable, "")
        normalized = " ".join(normalized.split())
        aliases = {
            "bektemir": "bektemir",
            "бектемир": "bektemir",
            "chilonzor": "chilonzor",
            "чиланзар": "chilonzor",
            "mirobod": "mirobod",
            "мирабад": "mirobod",
            "mirzo ulugbek": "mirzo_ulugbek",
            "mirzo ulug bek": "mirzo_ulugbek",
            "мирзо улугбек": "mirzo_ulugbek",
            "olmazor": "olmazor",
            "алмазар": "olmazor",
            "sergeli": "sergeli",
            "сергели": "sergeli",
            "сергелий": "sergeli",
            "сергилий": "sergeli",
            "shayxontohur": "shayxontohur",
            "шайхантахур": "shayxontohur",
            "uchtepa": "uchtepa",
            "учтепин": "uchtepa",
            "yakkasaroy": "yakkasaroy",
            "яккасарай": "yakkasaroy",
            "yangihayot": "yangihayot",
            "янгихаёт": "yangihayot",
            "янгихаят": "yangihayot",
            "yashnobod": "yashnobod",
            "яшнабад": "yashnobod",
            "yunusobod": "yunusobod",
            "юнусабад": "yunusobod",
        }
        return aliases.get(normalized, "")

    def _query_market_trend_rows(
        self,
        conn: Any,
        where_sql: str,
        params: dict[str, Any],
        filters: MarketInsightFilters,
        trend: dict[str, str],
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            f"""
            with filtered as (
                select
                    coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date as day,
                    {trend["value_expression"]} as metric_value
                from real_estate_listings
                {where_sql}
                  and price_value is not null
                  and price_value > 0
                  {trend["extra_predicate"]}
            ),
            bounds as (
                select
                    coalesce(min(day), current_date) as start_day,
                    coalesce(max(day), current_date) as end_day
                from filtered
            ),
            days as (
                select generate_series(
                    bounds.start_day,
                    bounds.end_day,
                    interval '1 day'
                )::date as day
                from bounds
            ),
            daily_values as (
                select
                    day,
                    avg(metric_value) as avg_value,
                    count(*) as listing_count
                from filtered
                where metric_value is not null and metric_value > 0
                group by day
            )
            select
                days.day,
                to_char(days.day, 'DD.MM') as label,
                daily_values.avg_value,
                coalesce(daily_values.listing_count, 0) as listing_count,
                0 as anomaly_count
            from days
            left join daily_values on daily_values.day = days.day
            group by days.day
                , daily_values.avg_value
                , daily_values.listing_count
            order by days.day
            """,
            {**params, "currency_code": filters.currency_code},
        ).fetchall()
        return [dict(row) for row in rows]

    def _prepare_price_segment_bars(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            label = row.get("segment_label") or "Segment"
            segment = grouped.setdefault(
                label,
                {
                    "label": label,
                    "order": int(row.get("segment_order") or 99),
                    "total": 0,
                    "bands": [],
                },
            )
            total = int(row.get("total") or 0)
            segment["total"] += total
            segment["bands"].append(
                {
                    "label": row.get("band_label") or "-",
                    "order": int(row.get("band_order") or 99),
                    "total": total,
                    "pct": 0,
                }
            )

        prepared = sorted(grouped.values(), key=lambda item: item["order"])
        for segment in prepared:
            max_total = max((band["total"] for band in segment["bands"]), default=0)
            segment["bands"] = sorted(segment["bands"], key=lambda item: item["order"])
            for band in segment["bands"]:
                band["pct"] = round((band["total"] / max_total) * 100, 1) if max_total else 0
        return prepared

    def _prepare_line_chart(
        self,
        rows: list[dict[str, Any]],
        filters: MarketInsightFilters,
        metric_label: str,
    ) -> dict[str, Any]:
        width = 760
        height = 280
        pad_left = 70
        pad_right = 20
        pad_top = 22
        pad_bottom = 38
        values = [float(row["avg_value"]) for row in rows if row.get("avg_value") is not None]
        anomaly_total = sum(int(row.get("anomaly_count") or 0) for row in rows)
        if not values:
            return {
                "metric_label": metric_label,
                "currency_code": filters.currency_code,
                "points": [],
                "polyline": "",
                "path": "",
                "moving_average_polyline": "",
                "moving_average_path": "",
                "latest_display": "-",
                "average_display": "-",
                "moving_average_latest_display": "-",
                "average_y": None,
                "y_min_display": "-",
                "y_max_display": "-",
                "y_min_short": "-",
                "y_max_short": "-",
                "y_mid_short": "-",
                "anomaly_total": anomaly_total,
                "width": width,
                "height": height,
            }

        y_min = min(values)
        y_max = max(values)
        if y_min == y_max:
            y_min = y_min * 0.95
            y_max = y_max * 1.05 if y_max else 1

        usable_width = width - pad_left - pad_right
        usable_height = height - pad_top - pad_bottom
        denominator = max(len(rows) - 1, 1)
        bar_width = max(4, min(12, usable_width / max(len(rows), 1) * 0.46))

        points: list[dict[str, Any]] = []
        polyline_parts: list[str] = []
        moving_polyline_parts: list[str] = []
        line_coordinates: list[tuple[float, float]] = []
        moving_coordinates: list[tuple[float, float]] = []
        for index, row in enumerate(rows):
            raw_value = row.get("avg_value")
            x = pad_left + (usable_width * index / denominator)
            moving_average = self._moving_average_value(rows, index, window=7)
            moving_y = None
            moving_display = "-"
            if moving_average is not None:
                moving_y = pad_top + ((y_max - moving_average) / (y_max - y_min) * usable_height)
                moving_display = self._format_trend_money(moving_average, filters.currency_code, metric_label)
                moving_x = round(x, 2)
                moving_y_rounded = round(moving_y, 2)
                moving_polyline_parts.append(f"{moving_x},{moving_y_rounded}")
                moving_coordinates.append((moving_x, moving_y_rounded))

            if raw_value is None:
                points.append(
                    {
                        "x": round(x, 2),
                        "y": None,
                        "bar_x": round(x - (bar_width / 2), 2),
                        "bar_y": None,
                        "bar_width": round(bar_width, 2),
                        "bar_height": 0,
                        "moving_y": round(moving_y, 2) if moving_y is not None else None,
                        "label": row["label"],
                        "display": "-",
                        "moving_display": moving_display,
                        "count": int(row.get("listing_count") or 0),
                        "anomaly_count": int(row.get("anomaly_count") or 0),
                        "show_label": index == 0 or index == len(rows) - 1 or index % 7 == 0,
                    }
                )
                continue

            value = float(raw_value)
            y = pad_top + ((y_max - value) / (y_max - y_min) * usable_height)
            bar_y = min(y, pad_top + usable_height)
            bar_height = max(2, (pad_top + usable_height) - bar_y)
            point = {
                "x": round(x, 2),
                "y": round(y, 2),
                "bar_x": round(x - (bar_width / 2), 2),
                "bar_y": round(bar_y, 2),
                "bar_width": round(bar_width, 2),
                "bar_height": round(bar_height, 2),
                "moving_y": round(moving_y, 2) if moving_y is not None else None,
                "label": row["label"],
                "display": self._format_trend_money(value, filters.currency_code, metric_label),
                "moving_display": moving_display,
                "count": int(row.get("listing_count") or 0),
                "anomaly_count": int(row.get("anomaly_count") or 0),
                "show_label": index == 0 or index == len(rows) - 1 or index % 7 == 0,
            }
            points.append(point)
            polyline_parts.append(f"{point['x']},{point['y']}")
            line_coordinates.append((point["x"], point["y"]))

        latest_value = values[-1]
        average_value = sum(values) / len(values)
        latest_moving_average = self._last_moving_average(rows, window=7)
        average_y = pad_top + ((y_max - average_value) / (y_max - y_min) * usable_height)
        y_mid = (y_min + y_max) / 2
        return {
            "metric_label": metric_label,
            "currency_code": filters.currency_code,
            "points": points,
            "polyline": " ".join(polyline_parts),
            "path": self._smooth_svg_path(line_coordinates),
            "moving_average_polyline": " ".join(moving_polyline_parts),
            "moving_average_path": self._smooth_svg_path(moving_coordinates),
            "latest_display": self._format_trend_money(latest_value, filters.currency_code, metric_label),
            "average_display": self._format_trend_money(average_value, filters.currency_code, metric_label),
            "moving_average_latest_display": self._format_trend_money(
                latest_moving_average,
                filters.currency_code,
                metric_label,
            )
            if latest_moving_average is not None
            else "-",
            "average_y": round(average_y, 2),
            "y_min_display": self._format_trend_money(y_min, filters.currency_code, metric_label),
            "y_max_display": self._format_trend_money(y_max, filters.currency_code, metric_label),
            "y_min_short": self._format_compact_money(y_min, filters.currency_code, metric_label),
            "y_max_short": self._format_compact_money(y_max, filters.currency_code, metric_label),
            "y_mid_short": self._format_compact_money(y_mid, filters.currency_code, metric_label),
            "anomaly_total": anomaly_total,
            "width": width,
            "height": height,
        }

    def _smooth_svg_path(self, coordinates: list[tuple[float, float]]) -> str:
        """Nuqtalardan o'tadigan yumshoq SVG path yaratadi."""

        if not coordinates:
            return ""
        if len(coordinates) == 1:
            x, y = coordinates[0]
            return f"M {x:g} {y:g}"
        if len(coordinates) == 2:
            (x1, y1), (x2, y2) = coordinates
            return f"M {x1:g} {y1:g} L {x2:g} {y2:g}"

        commands = [f"M {coordinates[0][0]:g} {coordinates[0][1]:g}"]
        smoothing = 0.14
        for index in range(len(coordinates) - 1):
            x0, y0 = coordinates[index - 1] if index > 0 else coordinates[index]
            x1, y1 = coordinates[index]
            x2, y2 = coordinates[index + 1]
            x3, y3 = coordinates[index + 2] if index + 2 < len(coordinates) else coordinates[index + 1]
            cp1_x = x1 + (x2 - x0) * smoothing
            cp1_y = y1 + (y2 - y0) * smoothing
            cp2_x = x2 - (x3 - x1) * smoothing
            cp2_y = y2 - (y3 - y1) * smoothing
            commands.append(f"C {cp1_x:g} {cp1_y:g} {cp2_x:g} {cp2_y:g} {x2:g} {y2:g}")
        return " ".join(commands)

    def _moving_average_value(
        self,
        rows: list[dict[str, Any]],
        index: int,
        window: int,
    ) -> float | None:
        window_rows = rows[max(0, index - window + 1) : index + 1]
        values = [float(row["avg_value"]) for row in window_rows if row.get("avg_value") is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def _last_moving_average(self, rows: list[dict[str, Any]], window: int) -> float | None:
        for index in range(len(rows) - 1, -1, -1):
            value = self._moving_average_value(rows, index, window)
            if value is not None:
                return value
        return None

    def _build_where_clause(self, filters: ListingFilters) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = [VISIBLE_QUALITY_CLAUSE]
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
                    or source_url ilike %(q)s
                    or listing_code ilike %(q)s
                )
                """
            )

        if filters.source:
            params["source"] = filters.source
            clauses.append("source = %(source)s")

        if filters.category:
            params["category"] = filters.category
            if category_by_path(filters.category):
                params["category_prefix"] = filters.category.rstrip("/") + "/%"
                clauses.append("(source_category = %(category)s or source_category like %(category_prefix)s)")
            else:
                clauses.append("source_category = %(category)s")

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

        return "where " + " and ".join(clauses), params

    def _format_listing_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["category_label"] = self._category_label(row.get("source_category"))
        row["source_label"] = self._source_label(row.get("source"), row.get("source_name"))
        row["area_display"] = self._area_display_from_columns(row)
        row["rooms_display"] = str(row.get("room_count")) if row.get("room_count") else ""
        row["contact_display"] = ""
        row["short_description"] = self._shorten(row.get("description") or "", max_length=180)
        return row

    def _category_label(self, path: str | None) -> str:
        if not path:
            return ""
        category = category_for_source_path(path)
        return category.name if category else path

    def _source_label(self, source: str | None, source_name: str | None) -> str:
        if source_name:
            return source_name
        if source == "olx":
            return "OLX.uz"
        if source == "telegram":
            return "Telegram"
        return source or ""

    def _deal_label(self, deal_type: str | None) -> str:
        if deal_type in DEAL_TYPE_FILTERS:
            return DEAL_TYPE_FILTERS[deal_type]["label"]
        if deal_type == "rent_daily":
            return "Sutkalik ijara"
        if deal_type == "rent_long":
            return "Uzoq muddatli ijara"
        if deal_type == "unknown":
            return "Aniqlanmagan"
        return deal_type or "Aniqlanmagan"

    def _property_label(self, property_type: str | None) -> str:
        if not property_type:
            return "Aniqlanmagan"
        return PROPERTY_LABELS.get(property_type, property_type)

    def _format_money(self, value: Any, currency_code: str | None) -> str:
        if value in (None, ""):
            return "-"
        amount = float(value)
        if currency_code == "USD":
            return f"${amount:,.0f}"
        if currency_code == "UZS":
            return f"{amount:,.0f} so'm"
        return f"{amount:,.0f}"

    def _format_trend_money(self, value: float, currency_code: str | None, metric_label: str) -> str:
        suffix = " / sotix" if "sotix" in metric_label else " / m2" if "m2" in metric_label else ""
        if currency_code == "USD":
            return f"${value:,.0f}{suffix}"
        if currency_code == "UZS":
            return f"{value:,.0f} so'm{suffix}"
        return f"{value:,.0f}{suffix}"

    def _format_compact_money(self, value: float, currency_code: str | None, metric_label: str) -> str:
        suffix = "/sotix" if "sotix" in metric_label else "/m2" if "m2" in metric_label else ""
        abs_value = abs(value)
        if abs_value >= 1_000_000_000:
            amount = f"{value / 1_000_000_000:.1f}B"
        elif abs_value >= 1_000_000:
            amount = f"{value / 1_000_000:.1f}M"
        elif abs_value >= 1_000:
            amount = f"{value / 1_000:.0f}k"
        else:
            amount = f"{value:,.0f}"

        if currency_code == "USD":
            return f"${amount}{suffix}"
        if currency_code == "UZS":
            return f"{amount} so'm{suffix}"
        return f"{amount}{suffix}"

    def _area_display_from_columns(self, row: dict[str, Any]) -> str:
        if row.get("area_m2") not in (None, ""):
            return f"{row['area_m2']} m2"
        if row.get("land_sotix") not in (None, ""):
            return f"{row['land_sotix']} sotix"
        return ""

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


def _with_percent(rows: list[dict[str, Any]], value_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    max_value = 0
    for row in rows:
        for key in value_keys:
            max_value = max(max_value, int(row.get(key) or 0))

    for row in rows:
        for key in value_keys:
            value = int(row.get(key) or 0)
            row[f"{key}_pct"] = round((value / max_value) * 100, 2) if max_value else 0
    return rows
