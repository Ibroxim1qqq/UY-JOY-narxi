create or replace view public.bi_tashkent_sale_market as
with loc as (
    select
        convert_from(decode('d0a2d0b0d188d0bad0b5d0bdd182', 'hex'), 'UTF8') as c_tashkent,
        convert_from(decode('d091d0b5d0bad182d0b5d0bcd0b8d180d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_bektemir,
        convert_from(decode('d0a7d0b8d0bbd0b0d0bdd0b7d0b0d180d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_chilonzor,
        convert_from(decode('d09cd0b8d180d0b0d0b1d0b0d0b4d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_mirobod,
        convert_from(decode('d09cd0b8d180d0b7d0be2dd0a3d0bbd183d0b3d0b1d0b5d0bad181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_mirzo_ulugbek,
        convert_from(decode('d090d0bbd0bcd0b0d0b7d0b0d180d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_olmazor,
        convert_from(decode('d0a1d0b5d180d0b3d0b5d0bbd0b8d0b9d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_sergeli,
        convert_from(decode('d0a8d0b0d0b9d185d0b0d0bdd182d0b0d185d183d180d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_shayxontohur,
        convert_from(decode('d0a3d187d182d0b5d0bfd0b8d0bdd181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_uchtepa,
        convert_from(decode('d0afd0bad0bad0b0d181d0b0d180d0b0d0b9d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_yakkasaroy,
        convert_from(decode('d0afd188d0bdd0b0d0b1d0b0d0b4d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_yashnobod,
        convert_from(decode('d0aed0bdd183d181d0b0d0b1d0b0d0b4d181d0bad0b8d0b920d180d0b0d0b9d0bed0bd', 'hex'), 'UTF8') as d_yunusobod
)
select
    l.id,
    l.listing_code,
    l.source,
    l.source_url,
    l.source_name,
    l.title,
    l.description,
    l.property_type,
    case
        when l.property_type = 'apartment' then 'Kvartira'
        when l.property_type in ('house', 'cottage') then 'Hovli/Kottej'
        when l.property_type = 'land_or_house' then 'Yer yoki hovli'
        when l.property_type is null or l.property_type = '' then 'Noma''lum'
        else l.property_type
    end as property_segment,
    l.deal_type,
    l.city_name,
    'Toshkent shahri' as toshkent_scope,
    case
        when nullif(l.district_name, '') is null then 'Noma''lum'
        when l.district_name = loc.d_bektemir then 'Bektemir'
        when l.district_name = loc.d_chilonzor then 'Chilonzor'
        when l.district_name = loc.d_mirobod then 'Mirobod'
        when l.district_name = loc.d_mirzo_ulugbek then 'Mirzo Ulugbek'
        when l.district_name = loc.d_olmazor then 'Olmazor'
        when l.district_name = loc.d_sergeli then 'Sergeli'
        when l.district_name = loc.d_shayxontohur then 'Shayxontohur'
        when l.district_name = loc.d_uchtepa then 'Uchtepa'
        when l.district_name = loc.d_yakkasaroy then 'Yakkasaroy'
        when l.district_name = loc.d_yashnobod then 'Yashnobod'
        when l.district_name = loc.d_yunusobod then 'Yunusobod'
        else coalesce(nullif(l.district_name, ''), 'Noma''lum')
    end as district_name,
    l.region_name,
    l.neighborhood,
    l.address,
    l.room_count,
    case
        when l.room_count is null then 'Noma''lum'
        when l.room_count >= 8 then '8+'
        else l.room_count::text
    end as room_bucket,
    l.floor_number,
    l.total_floors,
    l.area_m2,
    case
        when l.area_m2 >= 10 and l.area_m2 <= 1000 then l.area_m2
        else null::numeric
    end as valid_area_m2,
    case
        when l.area_m2 is null then 'Noma''lum'
        when l.area_m2 < 10 or l.area_m2 > 1000 then 'Outlier'
        when l.area_m2 < 50 then '<50 m2'
        when l.area_m2 < 75 then '50-75 m2'
        when l.area_m2 < 100 then '75-100 m2'
        when l.area_m2 < 150 then '100-150 m2'
        when l.area_m2 < 250 then '150-250 m2'
        else '250+ m2'
    end as area_bucket,
    l.land_sotix,
    case
        when l.land_sotix >= 0.5 and l.land_sotix <= 100 then l.land_sotix
        else null::numeric
    end as valid_land_sotix,
    case
        when l.land_sotix is null then 'Noma''lum'
        when l.land_sotix < 0.5 or l.land_sotix > 100 then 'Outlier'
        when l.land_sotix < 2 then '<2 sotix'
        when l.land_sotix < 4 then '2-4 sotix'
        when l.land_sotix < 6 then '4-6 sotix'
        when l.land_sotix < 10 then '6-10 sotix'
        when l.land_sotix < 20 then '10-20 sotix'
        else '20+ sotix'
    end as land_bucket,
    l.price_value,
    l.currency_code,
    case
        when l.currency_code in ('UZS', 'SUM')
         and l.price_value >= 10000000
         and l.price_value <= 100000000000
            then l.price_value
        when l.currency_code = 'USD'
         and l.price_value * 12093.35 >= 10000000
         and l.price_value * 12093.35 <= 100000000000
            then l.price_value * 12093.35
        else null::numeric
    end as valid_price_uzs,
    case
        when l.currency_code in ('UZS', 'SUM')
         and l.price_value >= 10000000
         and l.price_value <= 100000000000
         and l.area_m2 >= 10
         and l.area_m2 <= 1000
            then l.price_value / nullif(l.area_m2, 0)
        when l.currency_code = 'USD'
         and l.price_value * 12093.35 >= 10000000
         and l.price_value * 12093.35 <= 100000000000
         and l.area_m2 >= 10
         and l.area_m2 <= 1000
            then (l.price_value * 12093.35) / nullif(l.area_m2, 0)
        else null::numeric
    end as price_m2_uzs,
    case
        when l.currency_code in ('UZS', 'SUM')
         and l.price_value >= 10000000
         and l.price_value <= 100000000000
         and l.land_sotix >= 0.5
         and l.land_sotix <= 100
            then l.price_value / nullif(l.land_sotix, 0)
        when l.currency_code = 'USD'
         and l.price_value * 12093.35 >= 10000000
         and l.price_value * 12093.35 <= 100000000000
         and l.land_sotix >= 0.5
         and l.land_sotix <= 100
            then (l.price_value * 12093.35) / nullif(l.land_sotix, 0)
        else null::numeric
    end as price_sotix_uzs,
    case
        when l.currency_code not in ('UZS', 'SUM', 'USD') then 'Non-UZS'
        when l.price_value is null then 'Narx yo''q'
        when (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) < 10000000
          or (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
          ) > 100000000000
            then 'Narx outlier'
        else 'Valid narx'
    end as price_quality,
    case
        when l.price_value is null then 'Noma''lum'
        when (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) < 500000000 then '<500M'
        when (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) < 1000000000 then '500M-1B'
        when (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) < 2000000000 then '1B-2B'
        when (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) < 5000000000 then '2B-5B'
        else '5B+'
    end as price_bucket,
    case
        when (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) >= 10000000
         and (
            case
                when l.currency_code = 'USD' then l.price_value * 12093.35
                else l.price_value
            end
        ) <= 100000000000
         and l.area_m2 >= 10
         and l.area_m2 <= 1000
            then
                case
                    when (
                        case
                            when l.currency_code = 'USD' then l.price_value * 12093.35
                            else l.price_value
                        end
                    ) / nullif(l.area_m2, 0) < 8000000 then '<8M/m2'
                    when (
                        case
                            when l.currency_code = 'USD' then l.price_value * 12093.35
                            else l.price_value
                        end
                    ) / nullif(l.area_m2, 0) < 12000000 then '8-12M/m2'
                    when (
                        case
                            when l.currency_code = 'USD' then l.price_value * 12093.35
                            else l.price_value
                        end
                    ) / nullif(l.area_m2, 0) < 16000000 then '12-16M/m2'
                    when (
                        case
                            when l.currency_code = 'USD' then l.price_value * 12093.35
                            else l.price_value
                        end
                    ) / nullif(l.area_m2, 0) < 25000000 then '16-25M/m2'
                    else '25M+/m2'
                end
        else 'Noma''lum'
    end as price_m2_bucket,
    l.seller_type,
    l.has_media,
    l.views,
    l.quality_status,
    l.posted_at,
    date_trunc('month', l.posted_at)::date as posted_month,
    l.first_seen_at,
    l.last_seen_at,
    l.updated_at
from public.real_estate_listings l
cross join loc
where l.deal_type = 'sale'
  and (
      l.city_name = loc.c_tashkent
      or lower(coalesce(l.city_name, '')) in ('toshkent', 'tashkent', 'toshkent shahri', 'tashkent city')
      or lower(coalesce(l.city_name, '')) like '%toshkent shahri%'
      or lower(coalesce(l.city_name, '')) like '%tashkent city%'
  );
