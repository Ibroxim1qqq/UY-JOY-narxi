create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create table if not exists etl_runs (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    status text not null default 'running',
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    categories jsonb not null default '[]'::jsonb,
    max_pages_per_category integer,
    pages_processed integer not null default 0,
    listings_seen integer not null default 0,
    detail_pages_fetched integer not null default 0,
    rows_inserted integer not null default 0,
    rows_updated integer not null default 0,
    error_message text
);

create table if not exists olx_fetch_logs (
    id bigserial primary key,
    run_id uuid references etl_runs(id) on delete set null,
    url text not null,
    http_status integer,
    elapsed_ms integer,
    ok boolean not null default false,
    error_message text,
    fetched_at timestamptz not null default now()
);

create table if not exists olx_listing_raw (
    olx_id bigint primary key,
    listing_url text not null,
    source_category_path text not null,
    source_page integer not null default 0,
    category_id bigint,
    category_type text,

    title text,
    description text,
    price_display text,
    price_value numeric,
    currency_code text,
    is_price_negotiable boolean,

    city_name text,
    district_name text,
    region_name text,
    location_path text,
    latitude numeric,
    longitude numeric,

    seller_id bigint,
    seller_name text,
    seller_type text,
    is_business boolean,
    contact_phone text,
    contact_name text,
    contact_source text,
    contact_raw jsonb not null default '{}'::jsonb,
    contact_imported_at timestamptz,
    contact_updated_at timestamptz,

    created_time timestamptz,
    last_refresh_time timestamptz,
    pushup_time timestamptz,
    valid_to_time timestamptz,
    is_active boolean,
    status text,

    raw_params jsonb not null default '[]'::jsonb,
    param_values jsonb not null default '{}'::jsonb,
    raw_photos jsonb not null default '[]'::jsonb,
    raw_listing jsonb not null default '{}'::jsonb,
    raw_detail jsonb,
    content_hash text not null default '',
    listing_code text generated always as ('UYS-' || lpad(olx_id::text, 10, '0')) stored,

    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    detail_fetched_at timestamptz,
    updated_at timestamptz not null default now(),
    deal_type text generated always as (
        case
            when position('/prodazha' in lower(source_category_path)) > 0 then 'sale'
            when position('/obmen' in lower(source_category_path)) > 0 then 'exchange'
            when position('/arenda' in lower(source_category_path)) > 0
                or position('/posutochno_pochasovo' in lower(source_category_path)) > 0 then 'rent'
            else null
        end
    ) stored,
    room_count integer generated always as (
        case
            when (param_values -> 'number_of_rooms' ->> 'normalizedValue') ~ '^[0-9]+$'
                then (param_values -> 'number_of_rooms' ->> 'normalizedValue')::integer
            else null
        end
    ) stored,
    phone_number text
);

create index if not exists idx_olx_listing_raw_category on olx_listing_raw(source_category_path);
create index if not exists idx_olx_listing_raw_city on olx_listing_raw(city_name);
create index if not exists idx_olx_listing_raw_district on olx_listing_raw(district_name);
create index if not exists idx_olx_listing_raw_region on olx_listing_raw(region_name);
create index if not exists idx_olx_listing_raw_deal_type on olx_listing_raw(deal_type);
create index if not exists idx_olx_listing_raw_room_count on olx_listing_raw(room_count);
create index if not exists idx_olx_listing_raw_price_value on olx_listing_raw(price_value);
create unique index if not exists idx_olx_listing_raw_listing_code on olx_listing_raw(listing_code);
create index if not exists idx_olx_listing_raw_recent_sort on olx_listing_raw(
    coalesce(last_refresh_time, created_time, last_seen_at) desc
);
create index if not exists idx_olx_listing_raw_deal_room_district_recent on olx_listing_raw(
    deal_type,
    room_count,
    district_name,
    coalesce(last_refresh_time, created_time, last_seen_at) desc
);
create index if not exists idx_olx_listing_raw_title_trgm on olx_listing_raw using gin(title gin_trgm_ops);
create index if not exists idx_olx_listing_raw_city_trgm on olx_listing_raw using gin(city_name gin_trgm_ops);
create index if not exists idx_olx_listing_raw_district_trgm on olx_listing_raw using gin(district_name gin_trgm_ops);
