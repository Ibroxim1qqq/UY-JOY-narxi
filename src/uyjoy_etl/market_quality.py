from __future__ import annotations

from decimal import Decimal


QUALITY_USD_TO_UZS_RATE = Decimal("12093.35")

SUSPICIOUS_CASES = (
    "Sotuv narxi noreal: umumiy narx juda past yoki juda baland.",
    "Ijara narxi noreal: oylik narx juda past yoki juda baland.",
    "Kvartira sotuvda m2 narxi $150 dan past yoki $5 000 dan baland.",
    "Kvartira ijarada m2 narxi $0.5 dan past yoki $100 dan baland.",
    "Hovli sotuvda sotix narxi $500 dan past yoki $300 000 dan baland.",
    "Xona soni noreal: kvartira 1-10 xona, hovli 1-20 xona oralig'ida bo'lishi kerak.",
    "Kvartira maydoni noreal: 12-500 m2 oralig'idan tashqarida.",
    "Xona va maydon mos emas: masalan 1 xonali kvartira 80 m2 dan katta bo'lmasligi kerak.",
    "Hovli maydoni yoki yer sotixi noreal: uy maydoni 15-2000 m2, yer 0.5-500 sotix oralig'ida.",
    "Qavat xato: qavat 1-50 oralig'ida va jami qavatdan katta bo'lmasligi kerak.",
    "Matn juda bo'sh yoki test/demo e'lon bo'lsa, analitikadan chiqariladi.",
)


def market_quality_reasons_sql(
    *,
    price_uzs_expr: str,
    deal_type_expr: str = "deal_type",
    property_type_expr: str = "property_type",
    price_value_expr: str = "price_value",
    currency_code_expr: str = "currency_code",
    room_count_expr: str = "room_count",
    area_m2_expr: str = "area_m2",
    land_sotix_expr: str = "land_sotix",
    floor_number_expr: str = "floor_number",
    total_floors_expr: str = "total_floors",
) -> str:
    """Bozor statistikasiga qo'shilmasligi kerak bo'lgan noreal case'lar."""

    deal_sql = f"lower(coalesce({deal_type_expr}, ''))"
    property_sql = f"lower(coalesce({property_type_expr}, ''))"
    currency_sql = f"upper(coalesce({currency_code_expr}, ''))"
    is_sale = f"{deal_sql} = 'sale'"
    is_rent = f"{deal_sql} = 'rent'"
    is_apartment = f"{property_sql} = 'apartment'"
    is_house = f"{property_sql} = 'house'"
    return f"""
        array_remove(array[
            case
                when {price_value_expr} is not null
                 and {price_value_expr} <= 0
                    then 'non_positive_price'
            end,
            case
                when {price_value_expr} is not null
                 and nullif({currency_code_expr}, '') is not null
                 and {currency_sql} not in ('USD', 'UZS', 'SUM')
                    then 'unsupported_currency'
            end,
            case
                when {is_sale}
                 and {price_uzs_expr} is not null
                 and {price_uzs_expr} > 0
                 and {price_uzs_expr} < {_usd("3000")}
                    then 'sale_price_too_low'
            end,
            case
                when {is_apartment}
                 and {is_sale}
                 and {price_uzs_expr} is not null
                 and {price_uzs_expr} > {_usd("3000000")}
                    then 'sale_apartment_total_price_too_high'
            end,
            case
                when {is_house}
                 and {is_sale}
                 and {price_uzs_expr} is not null
                 and {price_uzs_expr} > {_usd("10000000")}
                    then 'sale_house_total_price_too_high'
            end,
            case
                when {is_apartment}
                 and {is_rent}
                 and {price_uzs_expr} is not null
                 and ({price_uzs_expr} < {_usd("20")} or {price_uzs_expr} > {_usd("20000")})
                    then 'rent_apartment_total_price_outlier'
            end,
            case
                when {is_house}
                 and {is_rent}
                 and {price_uzs_expr} is not null
                 and ({price_uzs_expr} < {_usd("30")} or {price_uzs_expr} > {_usd("50000")})
                    then 'rent_house_total_price_outlier'
            end,
            case
                when {room_count_expr} is not null
                 and (
                    {room_count_expr} <= 0
                    or ({is_apartment} and {room_count_expr} > 10)
                    or ({is_house} and {room_count_expr} > 20)
                    or {room_count_expr} > 30
                 )
                    then 'room_count_outlier'
            end,
            case
                when {is_apartment}
                 and {area_m2_expr} is not null
                 and ({area_m2_expr} < 12 or {area_m2_expr} > 500)
                    then 'apartment_area_outlier'
            end,
            case
                when {is_apartment}
                 and {room_count_expr} = 1
                 and {area_m2_expr} is not null
                 and {area_m2_expr} > 80
                    then 'apartment_one_room_area_too_large'
            end,
            case
                when {is_apartment}
                 and {room_count_expr} = 2
                 and {area_m2_expr} is not null
                 and ({area_m2_expr} < 20 or {area_m2_expr} > 140)
                    then 'apartment_two_room_area_outlier'
            end,
            case
                when {is_apartment}
                 and {room_count_expr} = 3
                 and {area_m2_expr} is not null
                 and ({area_m2_expr} < 30 or {area_m2_expr} > 220)
                    then 'apartment_three_room_area_outlier'
            end,
            case
                when {is_apartment}
                 and {room_count_expr} = 4
                 and {area_m2_expr} is not null
                 and ({area_m2_expr} < 40 or {area_m2_expr} > 320)
                    then 'apartment_four_room_area_outlier'
            end,
            case
                when {is_apartment}
                 and {room_count_expr} >= 5
                 and {area_m2_expr} is not null
                 and ({area_m2_expr} < 50 or {area_m2_expr} > 500)
                    then 'apartment_five_plus_room_area_outlier'
            end,
            case
                when {is_house}
                 and {area_m2_expr} is not null
                 and ({area_m2_expr} < 15 or {area_m2_expr} > 2000)
                    then 'house_area_outlier'
            end,
            case
                when {is_house}
                 and {land_sotix_expr} is not null
                 and ({land_sotix_expr} < 0.5 or {land_sotix_expr} > 500)
                    then 'house_land_sotix_outlier'
            end,
            case
                when {is_apartment}
                 and {is_sale}
                 and {price_uzs_expr} is not null
                 and {area_m2_expr} is not null
                 and {area_m2_expr} > 0
                 and {price_uzs_expr} / nullif({area_m2_expr}, 0) < {_usd("150")}
                    then 'sale_apartment_unit_price_too_low'
            end,
            case
                when {is_apartment}
                 and {is_sale}
                 and {price_uzs_expr} is not null
                 and {area_m2_expr} is not null
                 and {area_m2_expr} > 0
                 and {price_uzs_expr} / nullif({area_m2_expr}, 0) > {_usd("5000")}
                    then 'sale_apartment_unit_price_too_high'
            end,
            case
                when {is_apartment}
                 and {is_rent}
                 and {price_uzs_expr} is not null
                 and {area_m2_expr} is not null
                 and {area_m2_expr} > 0
                 and {price_uzs_expr} / nullif({area_m2_expr}, 0) < {_usd("0.5")}
                    then 'rent_apartment_unit_price_too_low'
            end,
            case
                when {is_apartment}
                 and {is_rent}
                 and {price_uzs_expr} is not null
                 and {area_m2_expr} is not null
                 and {area_m2_expr} > 0
                 and {price_uzs_expr} / nullif({area_m2_expr}, 0) > {_usd("100")}
                    then 'rent_apartment_unit_price_too_high'
            end,
            case
                when {is_house}
                 and {is_sale}
                 and {price_uzs_expr} is not null
                 and {land_sotix_expr} is not null
                 and {land_sotix_expr} > 0
                 and {price_uzs_expr} / nullif({land_sotix_expr}, 0) < {_usd("500")}
                    then 'sale_house_unit_price_too_low'
            end,
            case
                when {is_house}
                 and {is_sale}
                 and {price_uzs_expr} is not null
                 and {land_sotix_expr} is not null
                 and {land_sotix_expr} > 0
                 and {price_uzs_expr} / nullif({land_sotix_expr}, 0) > {_usd("300000")}
                    then 'sale_house_unit_price_too_high'
            end,
            case
                when {floor_number_expr} is not null
                 and ({floor_number_expr} <= 0 or {floor_number_expr} > 50)
                    then 'floor_number_outlier'
            end,
            case
                when {total_floors_expr} is not null
                 and ({total_floors_expr} <= 0 or {total_floors_expr} > 50)
                    then 'total_floors_outlier'
            end,
            case
                when {floor_number_expr} is not null
                 and {total_floors_expr} is not null
                 and {floor_number_expr} > {total_floors_expr}
                    then 'floor_greater_than_total_floors'
            end
        ], null)
    """


def market_quality_passes_sql(**kwargs: str) -> str:
    reasons_sql = market_quality_reasons_sql(**kwargs)
    return f"coalesce(array_length({reasons_sql}, 1), 0) = 0"


def _usd(amount: str) -> str:
    return format(Decimal(amount) * QUALITY_USD_TO_UZS_RATE, "f")
