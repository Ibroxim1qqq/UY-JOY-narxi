from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from psycopg.types.json import Jsonb

from uyjoy_etl.db import Database


@dataclass(frozen=True)
class TelegramCleanSummary:
    rows_seen: int
    rows_upserted: int


@dataclass(frozen=True)
class AddressParts:
    city_name: str | None
    district_name: str | None
    neighborhood: str | None


TASHKENT_CITY_DISTRICTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Bektemir", ("bektemir", "бектемир")),
    ("Chilonzor", ("chilonzor", "чилонзор")),
    ("Mirobod", ("mirobod", "миробод")),
    ("Mirzo Ulugbek", ("mirzo ulug", "mirzo ulug'bek", "мирзо улуг", "мирзо улуғ")),
    ("Olmazor", ("olmazor", "олмазор")),
    ("Sergeli", ("sergeli", "сергели")),
    ("Shayxontohur", ("shayxontohur", "shayhontohur", "shayxontoxur", "шайхонтохур", "шайхонтоҳур")),
    ("Uchtepa", ("uchtepa", "учтепа")),
    ("Yakkasaroy", ("yakkasaroy", "яккасарой")),
    ("Yashnobod", ("yashnobod", "яшнобод")),
    ("Yunusobod", ("yunusobod", "юнусобод")),
    ("Yangihayot", ("yangihayot", "янгихаёт", "янгиҳаёт")),
)

TASHKENT_REGION_DISTRICTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Angren", ("angren", "ангрен")),
    ("Bekobod", ("bekobod", "бекобод")),
    ("Bostanliq", ("bo'stonliq", "bostonliq", "бўстонлиқ", "бустонлик")),
    ("Chinoz", ("chinoz", "чиноз")),
    ("Ohangaron", ("ohangaron", "охангарон", "оҳангарон")),
    ("Oqqorgon", ("oqqorgon", "oqqo'rg'on", "оққўрғон", "оккургон")),
    ("Orta Chirchiq", ("o'rta chirchiq", "orta chirchiq", "ўрта чирчиқ", "урта чирчик")),
    ("Parkent", ("parkent", "паркент")),
    ("Piskent", ("piskent", "пискент")),
    ("Qibray", ("qibray", "қибрай", "кибрай")),
    ("Quyi Chirchiq", ("quyi chirchiq", "қуйи чирчиқ", "куйи чирчик")),
    ("Yuqori Chirchiq", ("yuqori chirchiq", "юқори чирчиқ", "юкори чирчик")),
    ("Chirchiq", ("chirchiq", "чирчиқ", "чирчик")),
    ("Toshkent tumani", ("toshkent tumani", "тошкент тумани")),
    ("Yangiyol", ("yangiyo'l", "yangiyol", "янгийўл", "янгийул")),
    ("Zangiota", ("zangiota", "зангиота")),
)


def clean_telegram_real_estate(database: Database) -> TelegramCleanSummary:
    """Telegram raw postlardan real-estate analytics uchun struktura chiqaradi."""

    with database.connect() as conn:
        rows = conn.execute(
            """
            select
                channel_id,
                message_id,
                channel_username,
                channel_title,
                post_url,
                posted_at,
                text,
                views,
                forwards,
                replies_count,
                has_media
            from telegram_posts
            where coalesce(text, '') <> ''
            """
        ).fetchall()

        records = [
            {**record, "extraction_raw": Jsonb(record["extraction_raw"])}
            for record in (extract_real_estate_fields(dict(row)) for row in rows)
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """
                insert into telegram_real_estate_posts (
                    channel_id, message_id, channel_username, channel_title, post_url,
                    posted_at, source_text, is_sold, property_type, deal_type,
                    address, city_name, district_name, neighborhood, landmark,
                    price_display, price_value, price_currency,
                    room_count, floor_number, total_floors, area_m2, land_sotix,
                    repair_state, has_media, views, forwards, replies_count,
                    has_contact_phone, extraction_raw, updated_at
                )
                values (
                    %(channel_id)s, %(message_id)s, %(channel_username)s, %(channel_title)s, %(post_url)s,
                    %(posted_at)s, %(source_text)s, %(is_sold)s, %(property_type)s, %(deal_type)s,
                    %(address)s, %(city_name)s, %(district_name)s, %(neighborhood)s, %(landmark)s,
                    %(price_display)s, %(price_value)s, %(price_currency)s,
                    %(room_count)s, %(floor_number)s, %(total_floors)s, %(area_m2)s, %(land_sotix)s,
                    %(repair_state)s, %(has_media)s, %(views)s, %(forwards)s, %(replies_count)s,
                    %(has_contact_phone)s, %(extraction_raw)s, now()
                )
                on conflict (channel_id, message_id) do update
                set channel_username = excluded.channel_username,
                    channel_title = excluded.channel_title,
                    post_url = excluded.post_url,
                    posted_at = excluded.posted_at,
                    source_text = excluded.source_text,
                    is_sold = excluded.is_sold,
                    property_type = excluded.property_type,
                    deal_type = excluded.deal_type,
                    address = excluded.address,
                    city_name = excluded.city_name,
                    district_name = excluded.district_name,
                    neighborhood = excluded.neighborhood,
                    landmark = excluded.landmark,
                    price_display = excluded.price_display,
                    price_value = excluded.price_value,
                    price_currency = excluded.price_currency,
                    room_count = excluded.room_count,
                    floor_number = excluded.floor_number,
                    total_floors = excluded.total_floors,
                    area_m2 = excluded.area_m2,
                    land_sotix = excluded.land_sotix,
                    repair_state = excluded.repair_state,
                    has_media = excluded.has_media,
                    views = excluded.views,
                    forwards = excluded.forwards,
                    replies_count = excluded.replies_count,
                    has_contact_phone = excluded.has_contact_phone,
                    extraction_raw = excluded.extraction_raw,
                    updated_at = now()
                """,
                records,
            )
        conn.commit()

    return TelegramCleanSummary(rows_seen=len(rows), rows_upserted=len(records))


def extract_real_estate_fields(row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("text") or ""
    clean_text = _normalize_text(text)
    price_display, price_value, price_currency = _extract_price(clean_text)
    address = _extract_labeled_value(clean_text, ("Манзил", "Manzil", "Адрес", "Адреси"))
    address = address or _extract_address_fallback(clean_text)
    address_parts = _extract_address_parts(address=address, full_text=clean_text)

    return {
        "channel_id": row["channel_id"],
        "message_id": row["message_id"],
        "channel_username": row.get("channel_username"),
        "channel_title": row.get("channel_title"),
        "post_url": row.get("post_url"),
        "posted_at": row.get("posted_at"),
        "source_text": text,
        "is_sold": _is_sold(clean_text),
        "property_type": _property_type(clean_text),
        "deal_type": _deal_type(clean_text),
        "address": address,
        "city_name": address_parts.city_name,
        "district_name": address_parts.district_name,
        "neighborhood": address_parts.neighborhood,
        "landmark": _extract_labeled_value(clean_text, ("Ориентир", "Oриентир", "Mo'ljal", "Мўлжал", "Ориентир")),
        "price_display": price_display,
        "price_value": price_value,
        "price_currency": price_currency,
        "room_count": _extract_rooms(clean_text),
        "floor_number": _extract_floor(clean_text),
        "total_floors": _extract_total_floors(clean_text),
        "area_m2": _extract_area_m2(clean_text),
        "land_sotix": _extract_land_sotix(clean_text),
        "repair_state": _extract_repair(clean_text),
        "has_media": row.get("has_media"),
        "views": row.get("views"),
        "forwards": row.get("forwards"),
        "replies_count": row.get("replies_count"),
        "has_contact_phone": _has_phone(clean_text),
        "extraction_raw": {
            "parser": "telegram_real_estate_regex_v2",
            "normalized_text": clean_text,
        },
    }


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").replace("\r", " ").split())


def _is_sold(text: str) -> bool:
    lowered = text.lower()
    return "#сотилди" in lowered or "сотилди" in lowered or "sotildi" in lowered


def _property_type(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("квартира", "#квартира", "xonadon", "хонадон")):
        return "apartment"
    if any(token in lowered for token in ("коттедж", "#коттедж", "cottage")):
        return "cottage"
    if any(token in lowered for token in ("участка", "yer", "ер ", "сотих")):
        return "land_or_house"
    if any(token in lowered for token in ("ҳовли", "ховли", "уй ", "#уй", "дом ")):
        return "house"
    return None


def _deal_type(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("ижара", "аренда", "ijara")):
        return "rent"
    if any(token in lowered for token in ("сотилади", "сотув", "sotiladi", "sotuv", "продается")):
        return "sale"
    if _is_sold(text):
        return "sale"
    return None


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    stop = (
        r"(?= 📍| 👁| 🔷| 🔶| ✅| 📊| 🏬| 📄| 🏦| 📞| 💬| 🔥| ⚡| 💦| "
        r"Нархи|Narxi|Цена|Тел|Майдони|Квадратураси|Ремонти|$)"
    )
    match = re.search(rf"(?:{label_pattern})\s*[:：]\s*(.*?){stop}", text, flags=re.IGNORECASE)
    if not match:
        return None
    return _clean_value(match.group(1))


def _extract_price(text: str) -> tuple[str | None, Decimal | None, str | None]:
    patterns = (
        r"(?:Нархи|Narxi|Цена)\s*[:：]\s*([^📞➖\n]+?)(?= Келиш| келиш| 📞| ➖|$)",
        r"(\d[\d\s.,]*\s*(?:сўм|сум|so'm|usd|\$))",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            display = _clean_value(match.group(1))
            if display and not re.search(r"\d", display):
                continue
            currency = _currency_from_text(display)
            return display, _decimal_from_text(display), currency
    return None, None, None


def _currency_from_text(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    if "сўм" in lowered or "сум" in lowered or "so'm" in lowered:
        return "UZS"
    if "$" in lowered or "usd" in lowered:
        return "USD"
    return None


def _decimal_from_text(value: str | None) -> Decimal | None:
    if not value:
        return None
    match = re.search(r"\d[\d\s.,]*", value)
    if not match:
        return None
    normalized = match.group(0).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _extract_rooms(text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*(?:та\s*)?(?:хона|xona|xона|комнат|ком\.?)", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _extract_floor(text: str) -> int | None:
    patterns = (
        r"(\d{1,2})\s*[-–]?\s*қават(?:да)?(?!ли)",
        r"(\d{1,2})\s*[-–]?\s*этаж(?:да)?(?!н)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_total_floors(text: str) -> int | None:
    patterns = (
        r"(\d{1,2})\s*қаватли",
        r"(\d{1,2})\s*этажн",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_area_m2(text: str) -> Decimal | None:
    patterns = (
        r"(?:Квадратураси|Майдони|Maydoni|Площадь)\s*[:：]?\s*([\d.,]+)\s*(?:м²|м2|кв\.?\s*м|m2)",
        r"([\d.,]+)\s*(?:м²|м2|кв\.?\s*м|m2)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _decimal_from_text(match.group(1))
    return None


def _extract_land_sotix(text: str) -> Decimal | None:
    match = re.search(r"([\d.,]+)\s*(?:сотих|соток|sotix|сот)", text, flags=re.IGNORECASE)
    return _decimal_from_text(match.group(1)) if match else None


def _extract_repair(text: str) -> str | None:
    return _extract_labeled_value(text, ("Ремонти", "Remonti", "Ремонт"))


def _extract_address_fallback(text: str) -> str | None:
    patterns = (
        r"(Тошкент[^#📊📞✅🔷🔶]{5,120})",
        r"((?:Юнусобод|Олмазор|Чилонзор|Мирзо|Яшнобод|Сергели|Яккасарой|Қибрай|Янгийўл|Келес)[^#📊📞✅🔷🔶]{5,120})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_value(match.group(1))
    return None


def _extract_address_parts(address: str | None, full_text: str) -> AddressParts:
    """Telegram address matnini analitika uchun shahar/tuman/qismga ajratadi."""

    text = _normalize_location_text(" ".join(part for part in (address, full_text) if part))
    if not text:
        return AddressParts(city_name=None, district_name=None, neighborhood=None)

    district_name, district_group = _find_district(text)
    city_name = _city_from_location_text(text, district_group)
    neighborhood = _extract_neighborhood(address, district_name)

    return AddressParts(
        city_name=city_name,
        district_name=district_name,
        neighborhood=neighborhood,
    )


def _find_district(text: str) -> tuple[str | None, str | None]:
    for district_name, aliases in TASHKENT_CITY_DISTRICTS:
        if _contains_alias(text, aliases):
            return district_name, "tashkent_city"

    for district_name, aliases in TASHKENT_REGION_DISTRICTS:
        if _contains_alias(text, aliases):
            return district_name, "tashkent_region"

    return None, None


def _city_from_location_text(text: str, district_group: str | None) -> str | None:
    if district_group == "tashkent_city":
        return "Toshkent shahri"
    if district_group == "tashkent_region":
        return "Toshkent viloyati"

    if _contains_alias(text, ("toshkent viloyati", "тошкент вилояти", "ташкентская область")):
        return "Toshkent viloyati"
    if _contains_alias(text, ("toshkent", "тошкент", "ташкент")):
        return "Toshkent shahri"
    if _contains_alias(text, ("samarqand", "самарқанд", "самарканд")):
        return "Samarqand"
    if _contains_alias(text, ("buxoro", "бухоро", "бухара")):
        return "Buxoro"
    if _contains_alias(text, ("andijon", "андижон", "андижан")):
        return "Andijon"
    if _contains_alias(text, ("namangan", "наманган")):
        return "Namangan"
    if _contains_alias(text, ("farg'ona", "fargona", "фарғона", "фергана")):
        return "Fargona"

    return None


def _extract_neighborhood(address: str | None, district_name: str | None) -> str | None:
    if not address:
        return None

    parts = [_clean_value(part) for part in re.split(r"[,;|]", address)]
    candidates = [part for part in parts if part and not _is_location_header(part, district_name)]
    if not candidates:
        return None

    candidate = re.sub(
        r"\b(?:ko'chasi|кўчаси|кучаси|улица|массив|мавзеси)\b",
        "",
        candidates[0],
        flags=re.IGNORECASE,
    )
    return _clean_value(candidate)


def _is_location_header(value: str, district_name: str | None) -> bool:
    text = _normalize_location_text(value)
    header_tokens = (
        "toshkent",
        "тошкент",
        "ташкент",
        "viloyati",
        "вилояти",
        "shahri",
        "шаҳри",
        "шахри",
        "tumani",
        "тумани",
        "район",
    )
    if any(token in text for token in header_tokens):
        return True

    if district_name:
        district_aliases = _aliases_for_district(district_name)
        if any(text == _normalize_location_text(alias) for alias in district_aliases):
            return True

    return False


def _aliases_for_district(district_name: str) -> tuple[str, ...]:
    for name, aliases in TASHKENT_CITY_DISTRICTS + TASHKENT_REGION_DISTRICTS:
        if name == district_name:
            return aliases
    return (district_name.lower(),)


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    return any(_normalize_location_text(alias) in text for alias in aliases)


def _normalize_location_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.casefold()
    replacements = {
        "ў": "у",
        "ғ": "г",
        "қ": "к",
        "ҳ": "х",
        "ʼ": "'",
        "`": "'",
        "’": "'",
    }
    for source, target in replacements.items():
        lowered = lowered.replace(source, target)
    return " ".join(lowered.split())


def _has_phone(text: str) -> bool:
    return re.search(r"(?:\+?998|998)?[\s\-()]?\d{2}[\s\-()]?\d{3}[\s\-()]?\d{2}[\s\-()]?\d{2}", text) is not None


def _clean_value(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip(" -–—:;,.")
    return clean or None
