from __future__ import annotations

from decimal import Decimal
from typing import Any

from uyjoy_etl.db import Database


USD_TO_UZS_RATE = Decimal("12093.35")
VISIBLE_QUALITY_CLAUSE = "(quality_status is null or quality_status = 'ok')"


DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "Bektemir": ("Bektemir", "Bektemir tumani", "Бектемирский район"),
    "Chilonzor": ("Chilonzor", "Chilonzor tumani", "Чиланзарский район", "Чилонзор тумани"),
    "Mirobod": ("Mirobod", "Mirobod tumani", "Мирабад", "Мирабадский район"),
    "Mirzo Ulugbek": (
        "Mirzo Ulugbek",
        "Mirzo Ulug'bek",
        "Mirzo Ulugbek tumani",
        "Мирзо-Улугбекский район",
        "Мирзо Улуғбек тумани",
    ),
    "Olmazor": ("Olmazor", "Olmazor tumani", "Алмазарский район"),
    "Sergeli": ("Sergeli", "Sergeli tumani", "Сергели тумани", "Сергелийский район"),
    "Shayxontohur": ("Shayxontohur", "Shayxontohur tumani", "Шайхантахурский район"),
    "Uchtepa": ("Uchtepa", "Uchtepa tumani", "Учтепа", "Учтепинский район"),
    "Yakkasaroy": ("Yakkasaroy", "Yakkasaroy tumani", "Яккасарайский район"),
    "Yangihayot": ("Yangihayot", "Yangihayot tumani", "Янгихаёт тумани", "Янгихает"),
    "Yashnobod": ("Yashnobod", "Yashnobod tumani", "Яшнобод тумани", "Яшнабадский район"),
    "Yunusobod": ("Yunusobod", "Yunusobod tumani", "Юнусабадский район"),
}


class ListingRepository:
    """FastAPI valuation formasi uchun kerak bo'ladigan eng kichik query qatlami."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get_stats(self) -> dict[str, int]:
        with self._database.connect() as conn:
            row = conn.execute(
                """
                select
                    count(*) as total_listings,
                    count(*) filter (
                        where deal_type = 'sale'
                          and property_type = 'apartment'
                          and (quality_status is null or quality_status = 'ok')
                    ) as sale_apartment_listings
                from real_estate_listings
                """
            ).fetchone()
        return {
            "total_listings": int(row.get("total_listings") or 0),
            "sale_apartment_listings": int(row.get("sale_apartment_listings") or 0),
        }

    def get_apartment_valuation_market_context(self, district: str, currency: str = "UZS") -> dict[str, Any]:
        canonical_district = canonical_district_value(district)
        if not canonical_district:
            return _empty_market_context(district)

        with self._database.connect() as conn:
            row = conn.execute(
                """
                with base as (
                    select
                        valid_price_uzs::float as price_uzs,
                        price_m2_uzs::float as unit_price_uzs
                    from bi_tashkent_sale_market
                    where deal_type = 'sale'
                      and property_segment = 'Kvartira'
                      and district_name = %(district)s
                      and valid_area_m2 between 12 and 500
                      and valid_price_uzs between 100000000 and 20000000000
                      and price_m2_uzs between 4000000 and 70000000
                      and coalesce(posted_at, first_seen_at, updated_at) >= now() - interval '30 days'
                      and (quality_status is null or quality_status = 'ok')
                )
                select
                    count(*) as listing_count,
                    percentile_cont(0.5) within group (order by price_uzs)
                        filter (where price_uzs is not null and price_uzs > 0) as median_price_uzs,
                    percentile_cont(0.5) within group (order by unit_price_uzs)
                        filter (where unit_price_uzs is not null and unit_price_uzs > 0)
                        as median_unit_price_uzs
                from base
                """,
                {"district": canonical_district},
            ).fetchone()

        return {
            "district": canonical_district,
            "listing_count": int(row.get("listing_count") or 0),
            "district_median_price_uzs": _optional_float(row.get("median_price_uzs")),
            "district_unit_price_uzs": _optional_float(row.get("median_unit_price_uzs")),
        }


def canonical_district_value(value: str) -> str:
    key = _alias_key(value)
    for canonical, aliases in DISTRICT_ALIASES.items():
        if key in {_alias_key(alias) for alias in (canonical, *aliases)}:
            return canonical
    return value.strip()


def _empty_market_context(district: str) -> dict[str, Any]:
    return {
        "district": district,
        "listing_count": 0,
        "district_median_price_uzs": None,
        "district_unit_price_uzs": None,
    }


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _alias_key(value: str) -> str:
    return value.strip().lower().replace("'", "").replace("ʼ", "").replace("’", "").replace("-", " ")
