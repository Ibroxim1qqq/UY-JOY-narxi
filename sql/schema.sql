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
    source_page integer not null,
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
    raw_listing jsonb not null,
    raw_detail jsonb,
    content_hash text not null,
    quality_status text not null default 'ok',
    quality_reasons jsonb not null default '[]'::jsonb,
    quality_checked_at timestamptz,
    listing_code text generated always as ('UYS-' || lpad(olx_id::text, 10, '0')) stored,

    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    detail_fetched_at timestamptz,
    updated_at timestamptz not null default now()
);

alter table olx_listing_raw add column if not exists category_id bigint;
alter table olx_listing_raw add column if not exists category_type text;
alter table olx_listing_raw add column if not exists param_values jsonb not null default '{}'::jsonb;
alter table olx_listing_raw add column if not exists contact_phone text;
alter table olx_listing_raw add column if not exists contact_name text;
alter table olx_listing_raw add column if not exists contact_source text;
alter table olx_listing_raw add column if not exists contact_raw jsonb not null default '{}'::jsonb;
alter table olx_listing_raw add column if not exists contact_imported_at timestamptz;
alter table olx_listing_raw add column if not exists contact_updated_at timestamptz;
alter table olx_listing_raw add column if not exists quality_status text not null default 'ok';
alter table olx_listing_raw add column if not exists quality_reasons jsonb not null default '[]'::jsonb;
alter table olx_listing_raw add column if not exists quality_checked_at timestamptz;
alter table olx_listing_raw add column if not exists listing_code text generated always as (
    'UYS-' || lpad(olx_id::text, 10, '0')
) stored;
do $$
declare
    current_deal_type_expr text;
begin
    select pg_get_expr(def.adbin, def.adrelid)
    into current_deal_type_expr
    from pg_attribute attr
    join pg_attrdef def
        on def.adrelid = attr.attrelid
       and def.adnum = attr.attnum
    where attr.attrelid = 'olx_listing_raw'::regclass
      and attr.attname = 'deal_type'
      and attr.attisdropped = false;

    if current_deal_type_expr is null
       or current_deal_type_expr not like '%posutochno_pochasovo%'
       or current_deal_type_expr not like '%obmen%' then
        alter table olx_listing_raw drop column if exists deal_type;
        alter table olx_listing_raw add column deal_type text generated always as (
            case
                when position('/prodazha' in lower(source_category_path)) > 0 then 'sale'
                when position('/obmen' in lower(source_category_path)) > 0 then 'exchange'
                when position('/arenda' in lower(source_category_path)) > 0
                    or position('/posutochno_pochasovo' in lower(source_category_path)) > 0 then 'rent'
                else null
            end
        ) stored;
    end if;
end $$;
alter table olx_listing_raw add column if not exists room_count integer generated always as (
    case
        when (param_values -> 'number_of_rooms' ->> 'normalizedValue') ~ '^[0-9]+$'
            then (param_values -> 'number_of_rooms' ->> 'normalizedValue')::integer
        else null
    end
) stored;

create index if not exists idx_olx_listing_raw_category on olx_listing_raw(source_category_path);
create index if not exists idx_olx_listing_raw_city on olx_listing_raw(city_name);
create index if not exists idx_olx_listing_raw_district on olx_listing_raw(district_name);
create index if not exists idx_olx_listing_raw_region on olx_listing_raw(region_name);
create index if not exists idx_olx_listing_raw_deal_type on olx_listing_raw(deal_type);
create index if not exists idx_olx_listing_raw_room_count on olx_listing_raw(room_count);
create index if not exists idx_olx_listing_raw_price_value on olx_listing_raw(price_value);
create index if not exists idx_olx_listing_raw_quality_status on olx_listing_raw(quality_status);
create index if not exists idx_olx_listing_raw_contact_phone on olx_listing_raw(contact_phone);
create unique index if not exists idx_olx_listing_raw_listing_code on olx_listing_raw(listing_code);
create index if not exists idx_olx_listing_raw_created_time on olx_listing_raw(created_time);
create index if not exists idx_olx_listing_raw_last_seen_at on olx_listing_raw(last_seen_at);
create index if not exists idx_olx_listing_raw_recent_sort on olx_listing_raw(
    coalesce(last_refresh_time, created_time, last_seen_at) desc
);
create index if not exists idx_olx_listing_raw_deal_room_district_recent on olx_listing_raw(
    deal_type,
    room_count,
    district_name,
    coalesce(last_refresh_time, created_time, last_seen_at) desc
);
create index if not exists idx_olx_listing_raw_raw_params_gin on olx_listing_raw using gin(raw_params);
create index if not exists idx_olx_listing_raw_param_values_gin on olx_listing_raw using gin(param_values);
create index if not exists idx_olx_listing_raw_raw_listing_gin on olx_listing_raw using gin(raw_listing);
create index if not exists idx_olx_listing_raw_title_trgm on olx_listing_raw using gin(title gin_trgm_ops);
create index if not exists idx_olx_listing_raw_description_trgm on olx_listing_raw using gin(description gin_trgm_ops);
create index if not exists idx_olx_listing_raw_city_trgm on olx_listing_raw using gin(city_name gin_trgm_ops);
create index if not exists idx_olx_listing_raw_district_trgm on olx_listing_raw using gin(district_name gin_trgm_ops);
create index if not exists idx_olx_listing_raw_region_trgm on olx_listing_raw using gin(region_name gin_trgm_ops);
create index if not exists idx_olx_listing_raw_url_trgm on olx_listing_raw using gin(listing_url gin_trgm_ops);
alter table olx_listing_raw add column if not exists phone_number text;
create index if not exists idx_olx_listing_raw_phone_number on olx_listing_raw(phone_number);
create index if not exists idx_olx_listing_raw_contact_phone_trgm on olx_listing_raw using gin(contact_phone gin_trgm_ops);
create index if not exists idx_olx_listing_raw_listing_code_trgm on olx_listing_raw using gin(listing_code gin_trgm_ops);

create table if not exists telegram_channels (
    channel_id bigint primary key,
    username text,
    title text,
    channel_url text,
    raw_channel jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    last_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists telegram_posts (
    id bigserial primary key,
    channel_id bigint not null references telegram_channels(channel_id) on delete cascade,
    message_id bigint not null,
    channel_username text,
    channel_title text,
    post_url text,
    posted_at timestamptz,
    text text,
    views integer,
    forwards integer,
    replies_count integer,
    has_media boolean not null default false,
    media_type text,
    raw_message jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (channel_id, message_id)
);

create index if not exists idx_telegram_channels_username on telegram_channels(username);
create index if not exists idx_telegram_posts_channel on telegram_posts(channel_id);
create index if not exists idx_telegram_posts_posted_at on telegram_posts(posted_at);
create index if not exists idx_telegram_posts_post_url on telegram_posts(post_url);
create index if not exists idx_telegram_posts_text_trgm on telegram_posts using gin(text gin_trgm_ops);

create table if not exists telegram_real_estate_posts (
    id bigserial primary key,
    channel_id bigint not null,
    message_id bigint not null,
    channel_username text,
    channel_title text,
    post_url text,
    posted_at timestamptz,
    source_text text,
    is_sold boolean not null default false,
    property_type text,
    deal_type text,
    address text,
    city_name text,
    district_name text,
    neighborhood text,
    landmark text,
    price_display text,
    price_value numeric,
    price_currency text,
    room_count integer,
    floor_number integer,
    total_floors integer,
    area_m2 numeric,
    land_sotix numeric,
    repair_state text,
    has_media boolean,
    views integer,
    forwards integer,
    replies_count integer,
    has_contact_phone boolean not null default false,
    quality_status text not null default 'ok',
    quality_reasons jsonb not null default '[]'::jsonb,
    quality_checked_at timestamptz,
    extraction_raw jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now(),
    unique (channel_id, message_id)
);

alter table telegram_real_estate_posts add column if not exists city_name text;
alter table telegram_real_estate_posts add column if not exists district_name text;
alter table telegram_real_estate_posts add column if not exists neighborhood text;
alter table telegram_real_estate_posts add column if not exists quality_status text not null default 'ok';
alter table telegram_real_estate_posts add column if not exists quality_reasons jsonb not null default '[]'::jsonb;
alter table telegram_real_estate_posts add column if not exists quality_checked_at timestamptz;

create index if not exists idx_tg_re_posts_channel on telegram_real_estate_posts(channel_id);
create index if not exists idx_tg_re_posts_property_type on telegram_real_estate_posts(property_type);
create index if not exists idx_tg_re_posts_deal_type on telegram_real_estate_posts(deal_type);
create index if not exists idx_tg_re_posts_price on telegram_real_estate_posts(price_value);
create index if not exists idx_tg_re_posts_rooms on telegram_real_estate_posts(room_count);
create index if not exists idx_tg_re_posts_area on telegram_real_estate_posts(area_m2);
create index if not exists idx_tg_re_posts_land on telegram_real_estate_posts(land_sotix);
create index if not exists idx_tg_re_posts_quality_status on telegram_real_estate_posts(quality_status);
create index if not exists idx_tg_re_posts_city on telegram_real_estate_posts(city_name);
create index if not exists idx_tg_re_posts_district on telegram_real_estate_posts(district_name);
create index if not exists idx_tg_re_posts_address_trgm on telegram_real_estate_posts using gin(address gin_trgm_ops);
create index if not exists idx_tg_re_posts_neighborhood_trgm on telegram_real_estate_posts using gin(neighborhood gin_trgm_ops);
create index if not exists idx_tg_re_posts_text_trgm on telegram_real_estate_posts using gin(source_text gin_trgm_ops);

drop view if exists telegram_real_estate_flat;

create or replace view telegram_real_estate_flat as
select
    id,
    channel_username as kanal,
    channel_title as kanal_nomi,
    post_url as post_ssilka,
    posted_at as joylangan_vaqt,
    property_type as uy_turi,
    deal_type as savdo_turi,
    address as adress,
    city_name as shahar,
    district_name as tuman,
    neighborhood as mahalla,
    landmark as moljal,
    price_display as narx_matn,
    price_value as narx,
    price_currency as valyuta,
    room_count as xona_soni,
    floor_number as qavat,
    total_floors as jami_qavat,
    area_m2 as maydon_m2,
    land_sotix as yer_sotix,
    repair_state as remont,
    is_sold as sotilganmi,
    has_media as rasmi_bormi,
    views as korishlar_soni,
    forwards as ulashishlar_soni,
    replies_count as javoblar_soni,
    has_contact_phone as kontakt_bormi,
    quality_status,
    quality_reasons,
    quality_checked_at,
    source_text as asl_matn,
    updated_at as yangilangan_vaqt
from telegram_real_estate_posts;
