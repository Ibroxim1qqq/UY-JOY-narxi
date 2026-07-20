create or replace view public.looker_listings as
with prepared as (
    select
        listings.id,
        listings.source,
        listings.source_name,
        listings.source_listing_id,
        listings.listing_code,
        listings.source_url,
        listings.source_category,
        listings.title,
        left(
            regexp_replace(
                regexp_replace(coalesce(listings.description, ''), '<[^>]+>', ' ', 'g'),
                '\s+',
                ' ',
                'g'
            ),
            300
        ) as description_short,
        listings.property_type,
        case
            when listings.property_type = 'apartment' then 'Kvartira'
            when listings.property_type = 'house' then 'Hovli'
            when listings.property_type = 'land' then 'Yer'
            else 'Boshqa'
        end as property_type_label,
        listings.deal_type,
        case
            when listings.deal_type = 'sale' then 'Sotuv'
            when listings.deal_type = 'rent' then 'Ijara'
            else 'Boshqa'
        end as deal_type_label,
        concat(
            case
                when listings.property_type = 'apartment' then 'Kvartira'
                when listings.property_type = 'house' then 'Hovli'
                when listings.property_type = 'land' then 'Yer'
                else 'Boshqa'
            end,
            ' ',
            case
                when listings.deal_type = 'sale' then 'sotuv'
                when listings.deal_type = 'rent' then 'ijara'
                else 'boshqa'
            end
        ) as segment_label,
        listings.price_display,
        case
            when listings.currency_code = 'USD' then listings.price_value * 12093.35
            when listings.currency_code in ('UZS', 'SUM') then listings.price_value
            else listings.price_value
        end as price_uzs,
        listings.currency_code as original_currency,
        listings.price_value as original_price,
        listings.is_price_negotiable,
        coalesce(nullif(listings.region_name, ''), nullif(listings.city_name, ''), 'Nomalum') as region_name,
        coalesce(nullif(listings.city_name, ''), 'Nomalum') as city_name,
        coalesce(nullif(listings.district_name, ''), 'Tuman korsatilmagan') as district_name,
        listings.neighborhood,
        listings.address,
        listings.latitude,
        listings.longitude,
        listings.room_count,
        listings.area_m2,
        listings.land_sotix,
        listings.floor_number,
        listings.total_floors,
        listings.seller_type,
        listings.is_business,
        listings.has_media,
        listings.views,
        listings.quality_status,
        coalesce(listings.posted_at, listings.first_seen_at, listings.last_seen_at, listings.updated_at)::date as posted_date,
        date_trunc('week', coalesce(listings.posted_at, listings.first_seen_at, listings.last_seen_at, listings.updated_at))::date as posted_week,
        date_trunc('month', coalesce(listings.posted_at, listings.first_seen_at, listings.last_seen_at, listings.updated_at))::date as posted_month,
        listings.posted_at,
        listings.first_seen_at,
        listings.last_seen_at,
        listings.updated_at
    from public.real_estate_listings listings
    where (listings.quality_status is null or listings.quality_status = 'ok')
      and listings.price_value is not null
      and listings.price_value > 0
      and (
          nullif(listings.city_name, '') is not null
          or nullif(listings.district_name, '') is not null
          or nullif(listings.address, '') is not null
      )
      and (
          listings.property_type is distinct from 'apartment'
          or listings.room_count is not null
      )
)
select
    id,
    source,
    source_name,
    source_listing_id,
    listing_code,
    source_url,
    source_category,
    title,
    description_short,
    property_type,
    property_type_label,
    deal_type,
    deal_type_label,
    segment_label,
    price_display,
    round(price_uzs, 0) as price_uzs,
    original_currency,
    original_price,
    is_price_negotiable,
    region_name,
    city_name,
    district_name,
    neighborhood,
    address,
    latitude,
    longitude,
    room_count,
    area_m2,
    land_sotix,
    floor_number,
    total_floors,
    case
        when property_type = 'apartment'
         and area_m2 is not null
         and area_m2 >= 10
         and area_m2 <= 1000
            then price_uzs / nullif(area_m2, 0)
    end as price_per_m2_uzs,
    case
        when property_type = 'house'
         and land_sotix is not null
         and land_sotix > 0
         and land_sotix <= 1000
            then price_uzs / nullif(land_sotix, 0)
    end as price_per_sotix_uzs,
    seller_type,
    is_business,
    has_media,
    views,
    quality_status,
    posted_date,
    posted_week,
    posted_month,
    posted_at,
    first_seen_at,
    last_seen_at,
    updated_at
from prepared;
