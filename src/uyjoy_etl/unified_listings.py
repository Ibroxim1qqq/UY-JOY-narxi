from __future__ import annotations

from dataclasses import dataclass

from uyjoy_etl.db import Database


@dataclass(frozen=True)
class UnifiedRefreshSummary:
    total_rows: int
    olx_rows: int
    telegram_rows: int


def refresh_unified_listings(database: Database) -> UnifiedRefreshSummary:
    """OLX va Telegram staging jadvallaridan bitta clean warehouse jadvalini yig'adi."""

    with database.connect() as conn:
        conn.execute("truncate table real_estate_listings restart identity")
        conn.execute(_OLX_INSERT_SQL)
        conn.execute(_TELEGRAM_INSERT_SQL)
        row = conn.execute(
            """
            select
                count(*) as total_rows,
                count(*) filter (where source = 'olx') as olx_rows,
                count(*) filter (where source = 'telegram') as telegram_rows
            from real_estate_listings
            """
        ).fetchone()
        conn.commit()

    return UnifiedRefreshSummary(
        total_rows=int(row["total_rows"]),
        olx_rows=int(row["olx_rows"]),
        telegram_rows=int(row["telegram_rows"]),
    )


_OLX_INSERT_SQL = """
insert into real_estate_listings (
    source, source_listing_id, listing_code, source_url, source_name, source_category,
    title, description, property_type, deal_type,
    price_display, price_value, currency_code, is_price_negotiable,
    city_name, district_name, region_name, neighborhood, address, latitude, longitude,
    room_count, floor_number, total_floors, area_m2, land_sotix,
    seller_type, is_business, has_media, views,
    quality_status, quality_reasons, posted_at, first_seen_at, last_seen_at, updated_at
)
select
    'olx' as source,
    olx_id::text as source_listing_id,
    listing_code,
    listing_url as source_url,
    'OLX.uz' as source_name,
    source_category_path as source_category,
    title,
    description,
    case
        when position('/kvartir' in lower(source_category_path)) > 0 then 'apartment'
        when position('/doma' in lower(source_category_path)) > 0 then 'house'
        when position('/zemlja' in lower(source_category_path)) > 0 then 'land'
        else category_type
    end as property_type,
    deal_type,
    price_display,
    price_value,
    currency_code,
    is_price_negotiable,
    city_name,
    district_name,
    region_name,
    null::text as neighborhood,
    nullif(location_path, '') as address,
    latitude,
    longitude,
    room_count,
    case
        when (param_values -> 'floor' ->> 'normalizedValue') ~ '^[0-9]+$'
            then (param_values -> 'floor' ->> 'normalizedValue')::integer
    end as floor_number,
    case
        when (param_values -> 'total_floors' ->> 'normalizedValue') ~ '^[0-9]+$'
            then (param_values -> 'total_floors' ->> 'normalizedValue')::integer
    end as total_floors,
    case
        when (param_values -> 'total_area' ->> 'normalizedValue') ~ '^[0-9]+([.,][0-9]+)?$'
            then replace(param_values -> 'total_area' ->> 'normalizedValue', ',', '.')::numeric
    end as area_m2,
    case
        -- OLX uy/hovli kategoriyasida yer maydoni ko'pincha `plot`
        -- parametrida keladi; eski importlar uchun `land_area` ham qo'llab-quvvatlanadi.
        when (param_values -> 'plot' ->> 'normalizedValue') ~ '^[0-9]+([.,][0-9]+)?$'
            then replace(param_values -> 'plot' ->> 'normalizedValue', ',', '.')::numeric
        when (param_values -> 'land_area' ->> 'normalizedValue') ~ '^[0-9]+([.,][0-9]+)?$'
            then replace(param_values -> 'land_area' ->> 'normalizedValue', ',', '.')::numeric
    end as land_sotix,
    seller_type,
    is_business,
    jsonb_array_length(coalesce(raw_photos, '[]'::jsonb)) > 0 as has_media,
    null::integer as views,
    quality_status,
    quality_reasons,
    coalesce(created_time, last_refresh_time, first_seen_at) as posted_at,
    first_seen_at,
    last_seen_at,
    updated_at
from olx_listing_raw
where price_value is not null
  and (
      nullif(city_name, '') is not null
      or nullif(district_name, '') is not null
      or nullif(location_path, '') is not null
  )
  and (
      case
          when position('/kvartir' in lower(source_category_path)) > 0 then 'apartment'
          when position('/doma' in lower(source_category_path)) > 0 then 'house'
          when position('/zemlja' in lower(source_category_path)) > 0 then 'land'
          else category_type
      end is distinct from 'apartment'
      or room_count is not null
  );
"""


_TELEGRAM_INSERT_SQL = """
insert into real_estate_listings (
    source, source_listing_id, listing_code, source_url, source_name, source_category,
    title, description, property_type, deal_type,
    price_display, price_value, currency_code, is_price_negotiable,
    city_name, district_name, region_name, neighborhood, address, latitude, longitude,
    room_count, floor_number, total_floors, area_m2, land_sotix,
    seller_type, is_business, has_media, views,
    quality_status, quality_reasons, posted_at, first_seen_at, last_seen_at, updated_at
)
select
    'telegram' as source,
    channel_id::text || ':' || message_id::text as source_listing_id,
    'TG-' || channel_id::text || '-' || message_id::text as listing_code,
    post_url as source_url,
    coalesce(channel_title, channel_username, 'Telegram') as source_name,
    channel_username as source_category,
    coalesce(
        nullif(address, ''),
        left(regexp_replace(coalesce(source_text, ''), '\\s+', ' ', 'g'), 120),
        'Telegram e''lon'
    ) as title,
    source_text as description,
    property_type,
    deal_type,
    price_display,
    price_value,
    price_currency as currency_code,
    null::boolean as is_price_negotiable,
    city_name,
    district_name,
    null::text as region_name,
    neighborhood,
    address,
    null::numeric as latitude,
    null::numeric as longitude,
    room_count,
    floor_number,
    total_floors,
    area_m2,
    land_sotix,
    null::text as seller_type,
    null::boolean as is_business,
    has_media,
    views,
    quality_status,
    quality_reasons,
    posted_at,
    posted_at as first_seen_at,
    updated_at as last_seen_at,
    updated_at
from telegram_real_estate_posts
where price_value is not null
  and (
      nullif(city_name, '') is not null
      or nullif(district_name, '') is not null
      or nullif(address, '') is not null
      or nullif(neighborhood, '') is not null
  )
  and (
      property_type is distinct from 'apartment'
      or room_count is not null
  );
"""
