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
    currency_code: str = "USD"
    metric: str = "auto"
    days: int = 60


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
        with self._database.connect() as conn:
            facets = self._get_market_facets(conn)
            summary = dict(
                conn.execute(
                    f"""
                    select
                        count(*) as total,
                        count(*) filter (where deal_type = 'sale') as sale_total,
                        count(*) filter (where deal_type = 'rent') as rent_total,
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
                    city_name,
                    count(*) as total,
                    count(*) filter (where deal_type = 'sale') as sale_total,
                    count(*) filter (where deal_type = 'rent') as rent_total,
                    percentile_cont(0.5) within group (order by price_value)
                        filter (where currency_code = 'USD' and price_value > 0) as median_usd,
                    percentile_cont(0.5) within group (order by price_value)
                        filter (where currency_code = 'UZS' and price_value > 0) as median_uzs
                from real_estate_listings
                {where_sql}
                  and city_name is not null
                  and city_name <> ''
                group by city_name
                order by count(*) desc
                limit 10
                """,
                params,
            ).fetchall()]
            top_districts = [dict(row) for row in conn.execute(
                f"""
                select
                    coalesce(district_name, 'Tuman ko''rsatilmagan') as district_name,
                    count(*) as total,
                    count(*) filter (where deal_type = 'sale') as sale_total,
                    count(*) filter (where deal_type = 'rent') as rent_total
                from real_estate_listings
                {where_sql}
                group by coalesce(district_name, 'Tuman ko''rsatilmagan')
                order by count(*) desc
                limit 12
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
                            when price_value < 30000 then '< $30k'
                            when price_value < 50000 then '$30k-$50k'
                            when price_value < 80000 then '$50k-$80k'
                            when price_value < 120000 then '$80k-$120k'
                            else '$120k+'
                        end as label,
                        case
                            when price_value < 30000 then 1
                            when price_value < 50000 then 2
                            when price_value < 80000 then 3
                            when price_value < 120000 then 4
                            else 5
                        end as sort_order
                    from real_estate_listings
                    {where_sql}
                      and currency_code = 'USD'
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
                    currency_code,
                    count(*) as total,
                    percentile_cont(0.5) within group (order by price_value) as median_price,
                    percentile_cont(0.9) within group (order by price_value) as p90_price
                from real_estate_listings
                {where_sql}
                  and price_value is not null
                  and price_value > 0
                  and currency_code in ('USD', 'UZS')
                group by coalesce(deal_type, 'unknown'), currency_code
                order by coalesce(deal_type, 'unknown'), currency_code
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
            trend_rows = [dict(row) for row in conn.execute(
                f"""
                with days as (
                    select generate_series(
                        current_date - (%(days)s::int - 1) * interval '1 day',
                        current_date,
                        interval '1 day'
                    )::date as day
                ),
                filtered as (
                    select
                        coalesce(posted_at, first_seen_at, last_seen_at, updated_at)::date as day,
                        {trend["value_expression"]} as metric_value
                    from real_estate_listings
                    {where_sql}
                      and currency_code = %(currency_code)s
                      and price_value is not null
                      and price_value > 0
                      {trend["extra_predicate"]}
                )
                select
                    days.day,
                    to_char(days.day, 'DD.MM') as label,
                    avg(filtered.metric_value) as avg_value,
                    count(filtered.metric_value) as listing_count
                from days
                left join filtered on filtered.day = days.day
                group by days.day
                order by days.day
                """,
                {**params, "currency_code": filters.currency_code, "days": filters.days},
            ).fetchall()]

        for row in source_mix:
            row["label"] = self._source_label(row.get("source"), None)
        for row in deal_mix:
            row["label"] = self._deal_label(row.get("deal_type"))
        for row in property_mix:
            row["label"] = self._property_label(row.get("property_type"))
        for row in top_cities:
            row["median_usd_display"] = self._format_money(row.get("median_usd"), "USD")
            row["median_uzs_display"] = self._format_money(row.get("median_uzs"), "UZS")
        for row in price_summary:
            row["deal_label"] = self._deal_label(row.get("deal_type"))
            row["median_display"] = self._format_money(row.get("median_price"), row.get("currency_code"))
            row["p90_display"] = self._format_money(row.get("p90_price"), row.get("currency_code"))

        return {
            "filters": filters,
            "facets": facets,
            "summary": summary,
            "source_mix": _with_percent(source_mix, ("total",)),
            "deal_mix": _with_percent(deal_mix, ("total",)),
            "property_mix": _with_percent(property_mix, ("total",)),
            "top_cities": _with_percent(top_cities, ("total",)),
            "top_districts": _with_percent(top_districts, ("total", "sale_total", "rent_total")),
            "room_mix": _with_percent(room_mix, ("total",)),
            "area_bands": _with_percent(area_bands, ("total",)),
            "usd_price_bands": _with_percent(usd_price_bands, ("total",)),
            "price_summary": price_summary,
            "daily_supply": _with_percent(daily_supply, ("olx_total", "telegram_total")),
            "price_trend": self._prepare_line_chart(trend_rows, filters, trend["label"]),
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

    def _normalize_market_filters(self, filters: MarketInsightFilters) -> MarketInsightFilters:
        currency_code = filters.currency_code if filters.currency_code in {"USD", "UZS"} else "USD"
        metric = filters.metric if filters.metric in {"auto", "avg_price", "avg_price_m2"} else "auto"
        days = min(max(filters.days, 14), 180)
        return MarketInsightFilters(
            deal_type=filters.deal_type if filters.deal_type in DEAL_TYPE_FILTERS else "",
            property_type=filters.property_type.strip(),
            city=filters.city.strip(),
            district=filters.district.strip(),
            currency_code=currency_code,
            metric=metric,
            days=days,
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
            clauses.append("city_name = %(market_city)s")

        if filters.district:
            params["market_district"] = filters.district
            clauses.append("district_name = %(market_district)s")

        return "where " + " and ".join(clauses), params

    def _get_market_facets(self, conn: Any) -> dict[str, list[dict[str, Any]]]:
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
        currencies = conn.execute(
            f"""
            select currency_code as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
              and currency_code in ('USD', 'UZS')
              and price_value is not null
            group by currency_code
            order by count(*) desc, currency_code
            """
        ).fetchall()
        cities = conn.execute(
            f"""
            select city_name as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
              and city_name is not null
              and city_name <> ''
            group by city_name
            order by count(*) desc, city_name
            limit 120
            """
        ).fetchall()
        districts = conn.execute(
            f"""
            select district_name as value, count(*) as count
            from real_estate_listings
            where {VISIBLE_QUALITY_CLAUSE}
              and district_name is not null
              and district_name <> ''
            group by district_name
            order by count(*) desc, district_name
            limit 240
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
            "currencies": [dict(row) for row in currencies],
            "cities": [dict(row) for row in cities],
            "districts": [dict(row) for row in districts],
            "sources": [
                {
                    "value": row["value"],
                    "label": self._source_label(row["value"], None),
                    "count": row["count"],
                }
                for row in sources
            ],
        }

    def _market_trend_sql(self, filters: MarketInsightFilters) -> dict[str, str]:
        metric = filters.metric
        if metric == "auto" and filters.deal_type == "rent":
            metric = "avg_price"
        elif metric == "auto" and filters.property_type == "apartment":
            metric = "avg_price_m2"
        elif metric == "auto":
            metric = "avg_price"

        if metric == "avg_price_m2":
            return {
                "label": "O'rtacha m2 narxi",
                "value_expression": "price_value / nullif(area_m2, 0)",
                "extra_predicate": "and area_m2 is not null and area_m2 > 0",
            }

        return {
            "label": "O'rtacha narx",
            "value_expression": "price_value",
            "extra_predicate": "",
        }

    def _prepare_line_chart(
        self,
        rows: list[dict[str, Any]],
        filters: MarketInsightFilters,
        metric_label: str,
    ) -> dict[str, Any]:
        width = 760
        height = 280
        pad_left = 58
        pad_right = 20
        pad_top = 22
        pad_bottom = 38
        values = [float(row["avg_value"]) for row in rows if row.get("avg_value") is not None]
        if not values:
            return {
                "metric_label": metric_label,
                "currency_code": filters.currency_code,
                "points": [],
                "polyline": "",
                "latest_display": "-",
                "average_display": "-",
                "y_min_display": "-",
                "y_max_display": "-",
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

        points: list[dict[str, Any]] = []
        polyline_parts: list[str] = []
        for index, row in enumerate(rows):
            raw_value = row.get("avg_value")
            x = pad_left + (usable_width * index / denominator)
            if raw_value is None:
                points.append(
                    {
                        "x": round(x, 2),
                        "y": None,
                        "label": row["label"],
                        "display": "-",
                        "count": int(row.get("listing_count") or 0),
                        "show_label": index == 0 or index == len(rows) - 1 or index % 7 == 0,
                    }
                )
                continue

            value = float(raw_value)
            y = pad_top + ((y_max - value) / (y_max - y_min) * usable_height)
            point = {
                "x": round(x, 2),
                "y": round(y, 2),
                "label": row["label"],
                "display": self._format_trend_money(value, filters.currency_code, metric_label),
                "count": int(row.get("listing_count") or 0),
                "show_label": index == 0 or index == len(rows) - 1 or index % 7 == 0,
            }
            points.append(point)
            polyline_parts.append(f"{point['x']},{point['y']}")

        latest_value = values[-1]
        average_value = sum(values) / len(values)
        return {
            "metric_label": metric_label,
            "currency_code": filters.currency_code,
            "points": points,
            "polyline": " ".join(polyline_parts),
            "latest_display": self._format_trend_money(latest_value, filters.currency_code, metric_label),
            "average_display": self._format_trend_money(average_value, filters.currency_code, metric_label),
            "y_min_display": self._format_trend_money(y_min, filters.currency_code, metric_label),
            "y_max_display": self._format_trend_money(y_max, filters.currency_code, metric_label),
            "width": width,
            "height": height,
        }

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
        suffix = " / m2" if "m2" in metric_label else ""
        if currency_code == "USD":
            return f"${value:,.0f}{suffix}"
        if currency_code == "UZS":
            return f"{value:,.0f} so'm{suffix}"
        return f"{value:,.0f}{suffix}"

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
