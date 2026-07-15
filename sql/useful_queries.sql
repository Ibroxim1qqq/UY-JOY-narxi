-- Oxirgi ETL run holatlari
select
    id,
    source,
    status,
    started_at,
    finished_at,
    pages_processed,
    listings_seen,
    detail_pages_fetched,
    rows_inserted,
    rows_updated,
    error_message
from etl_runs
order by started_at desc
limit 20;

-- Kategoriya va shahar bo'yicha e'lonlar soni
select
    source_category_path,
    region_name,
    city_name,
    count(*) as listings_count
from olx_listing_raw
group by source_category_path, region_name, city_name
order by listings_count desc;

-- Narxi bor e'lonlardan birinchi 100 tasi
select
    olx_id,
    title,
    price_display,
    price_value,
    currency_code,
    region_name,
    city_name,
    district_name,
    created_time,
    listing_url
from olx_listing_raw
where price_value is not null
order by last_seen_at desc
limit 100;

-- OLX params ichida umumiy maydon / yer maydoni bor e'lonlar.
-- Bu cleaning emas: OLX bergan raw value va normalizedValue ko'rsatiladi.
select
    olx_id,
    title,
    param_values -> 'total_area' ->> 'value' as total_area_raw,
    param_values -> 'total_area' ->> 'normalizedValue' as total_area_normalized,
    param_values -> 'land_area' ->> 'value' as land_area_raw,
    param_values -> 'land_area' ->> 'normalizedValue' as land_area_normalized,
    listing_url
from olx_listing_raw
where param_values ? 'total_area' or param_values ? 'land_area'
limit 100;

-- HTTP xatolar va sekin requestlar
select
    fetched_at,
    http_status,
    elapsed_ms,
    ok,
    url,
    error_message
from olx_fetch_logs
where ok = false or elapsed_ms > 5000
order by fetched_at desc
limit 100;
