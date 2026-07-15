from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

PRERENDERED_STATE_RE = re.compile(
    r"window\.__PRERENDERED_STATE__\s*=\s*\"((?:\\.|[^\"\\])*)\"\s*;",
    re.DOTALL,
)


class OlxParseError(RuntimeError):
    """OLX sahifasidan kutilgan JSON topilmasa yoki o'qilmasa ko'tariladi."""


@dataclass(frozen=True)
class ListingPage:
    page_number: int
    total_pages: int
    total_elements: int
    visible_elements: int
    ads: list[dict[str, Any]]
    state: dict[str, Any]


def parse_prerendered_state(html: str) -> dict[str, Any]:
    """HTML ichidagi `window.__PRERENDERED_STATE__` JSONini Python dictga aylantiradi."""

    match = PRERENDERED_STATE_RE.search(html)
    if not match:
        raise OlxParseError("window.__PRERENDERED_STATE__ topilmadi")

    try:
        encoded_json = '"' + match.group(1) + '"'
        json_text = json.loads(encoded_json)
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise OlxParseError(f"OLX prerendered JSON parse bo'lmadi: {exc}") from exc


def parse_listing_page(html: str) -> ListingPage:
    """Listing sahifadan e'lonlar ro'yxatini va pagination ma'lumotlarini oladi."""

    state = parse_prerendered_state(html)
    listing = state.get("listing", {}).get("listing")
    if not isinstance(listing, dict):
        raise OlxParseError("Listing JSON ichida listing.listing topilmadi")

    ads = listing.get("ads") or []
    if not isinstance(ads, list):
        raise OlxParseError("Listing JSON ichida ads ro'yxat emas")

    return ListingPage(
        page_number=int(listing.get("pageNumber") or 0),
        total_pages=int(listing.get("totalPages") or 0),
        total_elements=int(listing.get("totalElements") or 0),
        visible_elements=int(listing.get("visibleElements") or 0),
        ads=ads,
        state=state,
    )


def parse_detail_page(html: str) -> dict[str, Any]:
    """E'lon detail sahifasidan public raw ad JSONini qaytaradi."""

    state = parse_prerendered_state(html)
    ad = state.get("ad", {}).get("ad")
    if not isinstance(ad, dict):
        raise OlxParseError("Detail JSON ichida ad.ad topilmadi")
    return ad


def build_content_hash(listing_ad: dict[str, Any], detail_ad: dict[str, Any] | None) -> str:
    """Raw JSON o'zgargan-o'zgarmaganini bilish uchun stabil hash hisoblaydi."""

    payload = {
        "listing": listing_ad,
        "detail": detail_ad,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_datetime(value: str | None) -> datetime | None:
    """OLX ISO datetime matnini Postgresga mos datetime obyektiga aylantiradi."""

    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Datetime parse bo'lmadi: %s", value)
        return None


def get_price_fields(ad: dict[str, Any]) -> dict[str, Any]:
    """Raw price JSONidan qulay ustunlar uchun minimal maydonlarni ajratadi."""

    price = ad.get("price") or {}
    regular_price = price.get("regularPrice") or {}
    return {
        "price_display": price.get("displayValue"),
        "price_value": regular_price.get("value"),
        "currency_code": regular_price.get("currencyCode"),
        "is_price_negotiable": regular_price.get("negotiable"),
    }


def get_location_fields(ad: dict[str, Any]) -> dict[str, Any]:
    """Raw location/map JSONidan city, region, district va koordinatalarni ajratadi."""

    location = ad.get("location") or {}
    map_data = ad.get("map") or {}
    return {
        "city_name": location.get("cityName"),
        "district_name": location.get("districtName"),
        "region_name": location.get("regionName"),
        "location_path": location.get("pathName"),
        "latitude": map_data.get("lat"),
        "longitude": map_data.get("lon"),
    }


def get_seller_fields(ad: dict[str, Any]) -> dict[str, Any]:
    """Raw user JSONidan seller haqida public maydonlarni ajratadi."""

    user = ad.get("user") or {}
    return {
        "seller_id": user.get("id"),
        "seller_name": user.get("name") or (ad.get("contact") or {}).get("name"),
        "seller_type": user.get("sellerType"),
        "is_business": ad.get("isBusiness"),
    }


def get_contact_fields(ad: dict[str, Any]) -> dict[str, Any]:
    """Ruxsatli feed/listing JSON ichida contact kelsa, uni alohida ustunlarga ajratadi."""

    contact = ad.get("contact") or {}
    phone = (
        contact.get("phone")
        or contact.get("phoneNumber")
        or contact.get("phone_number")
        or contact.get("mobile")
    )
    phones = contact.get("phones")
    if not phone and isinstance(phones, list) and phones:
        phone = phones[0]

    return {
        "contact_phone": str(phone).strip() if phone else None,
        "contact_name": contact.get("name"),
        "contact_source": "olx_payload" if phone else None,
        "contact_raw": contact if phone else {},
        "has_contact": bool(phone),
    }


def build_param_values(ad: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """OLX params ro'yxatini key bo'yicha map qiladi; qiymatlar hali clean qilinmaydi."""

    params = ad.get("params") or []
    param_values: dict[str, dict[str, Any]] = {}
    for param in params:
        key = param.get("key")
        if not key:
            continue
        param_values[key] = {
            "name": param.get("name"),
            "type": param.get("type"),
            "value": param.get("value"),
            "normalizedValue": param.get("normalizedValue"),
        }
    return param_values


def build_db_record(
    listing_ad: dict[str, Any],
    source_category_path: str,
    source_page: int,
    detail_ad: dict[str, Any] | None,
) -> dict[str, Any]:
    """Raw listing/detail JSONlarni Postgres upsert uchun bitta recordga yig'adi."""

    ad_for_columns = detail_ad or listing_ad
    price_fields = get_price_fields(ad_for_columns)
    location_fields = get_location_fields(ad_for_columns)
    seller_fields = get_seller_fields(ad_for_columns)
    contact_fields = get_contact_fields(ad_for_columns)

    return {
        "olx_id": ad_for_columns.get("id") or listing_ad.get("id"),
        "listing_url": ad_for_columns.get("url") or listing_ad.get("url"),
        "source_category_path": source_category_path,
        "source_page": source_page,
        "category_id": (ad_for_columns.get("category") or {}).get("id"),
        "category_type": (ad_for_columns.get("category") or {}).get("type"),
        "title": ad_for_columns.get("title"),
        "description": ad_for_columns.get("description"),
        **price_fields,
        **location_fields,
        **seller_fields,
        **contact_fields,
        "created_time": parse_datetime(ad_for_columns.get("createdTime")),
        "last_refresh_time": parse_datetime(ad_for_columns.get("lastRefreshTime")),
        "pushup_time": parse_datetime(ad_for_columns.get("pushupTime")),
        "valid_to_time": parse_datetime(ad_for_columns.get("validToTime")),
        "is_active": ad_for_columns.get("isActive"),
        "status": ad_for_columns.get("status"),
        "raw_params": ad_for_columns.get("params") or [],
        "param_values": build_param_values(ad_for_columns),
        "raw_photos": ad_for_columns.get("photos") or [],
        "raw_listing": listing_ad,
        "raw_detail": detail_ad,
        "content_hash": build_content_hash(listing_ad, detail_ad),
        "has_detail": detail_ad is not None,
    }
