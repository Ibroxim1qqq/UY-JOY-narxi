from __future__ import annotations

from dataclasses import dataclass

from uyjoy_etl.db import Database


@dataclass(frozen=True)
class QualitySummary:
    olx_total: int
    olx_suspicious: int
    telegram_total: int
    telegram_suspicious: int


SUSPICIOUS_CASES = (
    "Juda arzon yoki juda qimmat narx: masalan sotuv kvartira 500 USD yoki 100 mln USD.",
    "Ijara narxi noreal: masalan oyiga 1 USD yoki 100 000 USD.",
    "Xona soni noreal: masalan 80 xona kvartira.",
    "Maydon noreal: masalan kvartira 5000 m2 yoki maydon 0 m2.",
    "Qavat xato: masalan 12-qavat, lekin uy jami 5 qavatli.",
    "Matn juda bo'sh: title va description deyarli yo'q.",
    "Telegram post sotilgan deb belgilangan bo'lsa, aktiv e'lon sifatida yashiriladi.",
    "Manzil ham, narx ham yo'q bo'lsa, analitika uchun shubhali deb belgilanadi.",
)


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
    conn.execute(
        """
        with scored as (
            select
                olx_id,
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
                             and coalesce(price_display, '') !~* '(kelish|келиш|договор)'
                            then 'missing_price'
                    end,
                    case
                        when deal_type = 'sale'
                             and currency_code = 'USD'
                             and price_value is not null
                             and (price_value < 3000 or price_value > 5000000)
                            then 'sale_price_usd_outlier'
                    end,
                    case
                        when deal_type = 'sale'
                             and currency_code in ('UZS', 'SUM')
                             and price_value is not null
                             and (price_value < 30000000 or price_value > 80000000000)
                            then 'sale_price_uzs_outlier'
                    end,
                    case
                        when deal_type = 'rent'
                             and currency_code = 'USD'
                             and price_value is not null
                             and (price_value < 20 or price_value > 20000)
                            then 'rent_price_usd_outlier'
                    end,
                    case
                        when deal_type = 'rent'
                             and currency_code in ('UZS', 'SUM')
                             and price_value is not null
                             and (price_value < 100000 or price_value > 100000000)
                            then 'rent_price_uzs_outlier'
                    end,
                    case
                        when room_count is not null and room_count > 30
                            then 'room_count_outlier'
                    end,
                    case
                        when _total_area_m2 is not null
                             and (_total_area_m2 <= 0 or _total_area_m2 > 10000)
                            then 'area_outlier'
                    end,
                    case
                        when source_category_path like '%kvartir%'
                             and _total_area_m2 is not null
                             and (_total_area_m2 < 10 or _total_area_m2 > 2000)
                            then 'apartment_area_outlier'
                    end,
                    case
                        when _land_sotix is not null and (_land_sotix <= 0 or _land_sotix > 1000)
                            then 'land_sotix_outlier'
                    end,
                    case
                        when _floor is not null
                             and _total_floors is not null
                             and _floor > _total_floors
                            then 'floor_greater_than_total_floors'
                    end,
                    case
                        when lower(coalesce(title, '') || ' ' || coalesce(description, '')) ~
                             '(test|asdf|qwerty|demo|тест)'
                            then 'test_or_placeholder_text'
                    end
                ], null) as reasons
            from (
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
            ) olx
        )
        update olx_listing_raw raw
        set quality_status = case when array_length(scored.reasons, 1) > 0 then 'suspicious' else 'ok' end,
            quality_reasons = to_jsonb(scored.reasons),
            quality_checked_at = now()
        from scored
        where raw.olx_id = scored.olx_id
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
    conn.execute(
        """
        with scored as (
            select
                id,
                array_remove(array[
                    case when is_sold then 'sold_post' end,
                    case
                        when length(coalesce(source_text, '')) < 25
                            then 'too_little_text'
                    end,
                    case
                        when address is null and price_value is null
                            then 'missing_location_and_price'
                    end,
                    case
                        when deal_type = 'sale'
                             and price_currency = 'USD'
                             and price_value is not null
                             and (price_value < 3000 or price_value > 5000000)
                            then 'sale_price_usd_outlier'
                    end,
                    case
                        when deal_type = 'sale'
                             and price_currency = 'UZS'
                             and price_value is not null
                             and (price_value < 30000000 or price_value > 80000000000)
                            then 'sale_price_uzs_outlier'
                    end,
                    case
                        when deal_type = 'rent'
                             and price_currency = 'USD'
                             and price_value is not null
                             and (price_value < 20 or price_value > 20000)
                            then 'rent_price_usd_outlier'
                    end,
                    case
                        when deal_type = 'rent'
                             and price_currency = 'UZS'
                             and price_value is not null
                             and (price_value < 100000 or price_value > 100000000)
                            then 'rent_price_uzs_outlier'
                    end,
                    case
                        when room_count is not null and room_count > 30
                            then 'room_count_outlier'
                    end,
                    case
                        when area_m2 is not null and (area_m2 <= 0 or area_m2 > 10000)
                            then 'area_outlier'
                    end,
                    case
                        when property_type = 'apartment'
                             and area_m2 is not null
                             and (area_m2 < 10 or area_m2 > 2000)
                            then 'apartment_area_outlier'
                    end,
                    case
                        when land_sotix is not null and (land_sotix <= 0 or land_sotix > 1000)
                            then 'land_sotix_outlier'
                    end,
                    case
                        when floor_number is not null
                             and total_floors is not null
                             and floor_number > total_floors
                            then 'floor_greater_than_total_floors'
                    end
                ], null) as reasons
            from telegram_real_estate_posts
        )
        update telegram_real_estate_posts posts
        set quality_status = case when array_length(scored.reasons, 1) > 0 then 'suspicious' else 'ok' end,
            quality_reasons = to_jsonb(scored.reasons),
            quality_checked_at = now()
        from scored
        where posts.id = scored.id
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
