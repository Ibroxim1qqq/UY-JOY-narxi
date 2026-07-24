from __future__ import annotations

from dataclasses import dataclass

from uyjoy_etl.db import Database
from uyjoy_etl.market_quality import SUSPICIOUS_CASES, market_quality_reasons_sql


@dataclass(frozen=True)
class QualitySummary:
    olx_total: int
    olx_suspicious: int
    telegram_total: int
    telegram_suspicious: int


def mark_suspicious_records(database: Database) -> QualitySummary:
    """OLX va Telegram e'lonlariga quality flag qo'yadi.

    Bu funksiya e'lonni fizik o'chirmaydi. `quality_status='suspicious'`
    bo'lgan qatorlar dashboard va Power BI querylaridan yashiriladi.
    """

    with database.connect() as conn:
        olx_total, olx_suspicious = _mark_olx(conn)
        telegram_total, telegram_suspicious = _mark_telegram(conn)
        conn.commit()

    return QualitySummary(
        olx_total=olx_total,
        olx_suspicious=olx_suspicious,
        telegram_total=telegram_total,
        telegram_suspicious=telegram_suspicious,
    )


def _mark_olx(conn) -> tuple[int, int]:
    property_type_expr = """
        case
            when position('/kvartir' in lower(source_category_path)) > 0 then 'apartment'
            when position('/doma' in lower(source_category_path)) > 0 then 'house'
            when position('/zemlja' in lower(source_category_path)) > 0 then 'land'
            else category_type
        end
    """
    price_uzs_expr = """
        case
            when currency_code = 'USD' then price_value * 12093.35
            when currency_code in ('UZS', 'SUM') then price_value
            else price_value
        end
    """
    market_reasons_sql = market_quality_reasons_sql(
        price_uzs_expr=price_uzs_expr,
        property_type_expr=property_type_expr,
        area_m2_expr="_total_area_m2",
        land_sotix_expr="_land_sotix",
        floor_number_expr="_floor",
        total_floors_expr="_total_floors",
    )
    conn.execute(
        f"""
        with olx as materialized (
            select
                *,
                case
                    when (param_values -> 'total_area' ->> 'normalizedValue') ~ '^[0-9]+([.,][0-9]+)?$'
                        then replace(param_values -> 'total_area' ->> 'normalizedValue', ',', '.')::numeric
                end as _total_area_m2,
                case
                    when (param_values -> 'plot' ->> 'normalizedValue') ~ '^[0-9]+([.,][0-9]+)?$'
                        then replace(param_values -> 'plot' ->> 'normalizedValue', ',', '.')::numeric
                    when (param_values -> 'land_area' ->> 'normalizedValue') ~ '^[0-9]+([.,][0-9]+)?$'
                        then replace(param_values -> 'land_area' ->> 'normalizedValue', ',', '.')::numeric
                end as _land_sotix,
                case
                    when (param_values -> 'floor' ->> 'normalizedValue') ~ '^[0-9]+$'
                        then (param_values -> 'floor' ->> 'normalizedValue')::integer
                end as _floor,
                case
                    when (param_values -> 'total_floors' ->> 'normalizedValue') ~ '^[0-9]+$'
                        then (param_values -> 'total_floors' ->> 'normalizedValue')::integer
                end as _total_floors
            from olx_listing_raw
        ),
        scored as materialized (
            select
                olx_id,
                array_cat(
                    array_remove(array[
                        case
                            when is_active is false or status in ('removed', 'inactive', 'archived', 'deleted')
                                then 'inactive_or_removed'
                        end,
                        case
                            when length(coalesce(title, '')) < 5 and length(coalesce(description, '')) < 20
                                then 'too_little_text'
                        end,
                        case
                            when price_value is null
                                 and is_price_negotiable is not true
                                 and coalesce(price_display, '') !~* '(kelish|kelishiladi|dogovor)'
                                then 'missing_price'
                        end,
                        case
                            when lower(coalesce(title, '') || ' ' || coalesce(description, '')) ~
                                 '(test|asdf|qwerty|demo)'
                                then 'test_or_placeholder_text'
                        end
                    ], null),
                    {market_reasons_sql}
                ) as reasons
            from olx
        )
        update olx_listing_raw raw
        set quality_status = case when array_length(scored.reasons, 1) > 0 then 'suspicious' else 'ok' end,
            quality_reasons = to_jsonb(scored.reasons),
            quality_checked_at = now()
        from scored
        where raw.olx_id = scored.olx_id
          and (
              raw.quality_status is distinct from
                  case when array_length(scored.reasons, 1) > 0 then 'suspicious' else 'ok' end
              or raw.quality_reasons is distinct from to_jsonb(scored.reasons)
          )
        """
    )
    row = conn.execute(
        """
        select
            count(*) as total,
            count(*) filter (where quality_status = 'suspicious') as suspicious
        from olx_listing_raw
        """
    ).fetchone()
    return int(row["total"]), int(row["suspicious"])


def _mark_telegram(conn) -> tuple[int, int]:
    price_uzs_expr = """
        case
            when price_currency = 'USD' then price_value * 12093.35
            when price_currency in ('UZS', 'SUM') then price_value
            else price_value
        end
    """
    market_reasons_sql = market_quality_reasons_sql(
        price_uzs_expr=price_uzs_expr,
        currency_code_expr="price_currency",
    )
    conn.execute(
        f"""
        with scored as materialized (
            select
                id,
                array_cat(
                    array_remove(array[
                        case when is_sold then 'sold_post' end,
                        case
                            when length(coalesce(source_text, '')) < 25
                                then 'too_little_text'
                        end,
                        case
                            when address is null and price_value is null
                                then 'missing_location_and_price'
                        end
                    ], null),
                    {market_reasons_sql}
                ) as reasons
            from telegram_real_estate_posts
        )
        update telegram_real_estate_posts posts
        set quality_status = case when array_length(scored.reasons, 1) > 0 then 'suspicious' else 'ok' end,
            quality_reasons = to_jsonb(scored.reasons),
            quality_checked_at = now()
        from scored
        where posts.id = scored.id
          and (
              posts.quality_status is distinct from
                  case when array_length(scored.reasons, 1) > 0 then 'suspicious' else 'ok' end
              or posts.quality_reasons is distinct from to_jsonb(scored.reasons)
          )
        """
    )
    row = conn.execute(
        """
        select
            count(*) as total,
            count(*) filter (where quality_status = 'suspicious') as suspicious
        from telegram_real_estate_posts
        """
    ).fetchone()
    return int(row["total"]), int(row["suspicious"])
