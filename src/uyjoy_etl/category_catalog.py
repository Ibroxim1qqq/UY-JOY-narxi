from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryDefinition:
    """OLX real-estate category uchun bizga kerakli statik metadata."""

    name: str
    path: str
    olx_category_id: int
    property_group: str
    deal_type: str


DEFAULT_REAL_ESTATE_CATEGORIES: tuple[CategoryDefinition, ...] = (
    CategoryDefinition(
        name="Kvartira sotish",
        path="nedvizhimost/kvartiry/prodazha",
        olx_category_id=13,
        property_group="apartment",
        deal_type="sale",
    ),
    CategoryDefinition(
        name="Kvartira uzoq muddatli ijara",
        path="nedvizhimost/kvartiry/arenda-dolgosrochnaya",
        olx_category_id=1147,
        property_group="apartment",
        deal_type="rent_long",
    ),
    CategoryDefinition(
        name="Kvartira almashuv",
        path="nedvizhimost/kvartiry/obmen",
        olx_category_id=1513,
        property_group="apartment",
        deal_type="exchange",
    ),
    CategoryDefinition(
        name="Uy / hovli sotish",
        path="nedvizhimost/doma/prodazha",
        olx_category_id=18,
        property_group="house",
        deal_type="sale",
    ),
    CategoryDefinition(
        name="Uy / hovli uzoq muddatli ijara",
        path="nedvizhimost/doma/arenda-dolgosrochnaya",
        olx_category_id=330,
        property_group="house",
        deal_type="rent_long",
    ),
    CategoryDefinition(
        name="Uy / hovli almashuv",
        path="nedvizhimost/doma/obmen",
        olx_category_id=1517,
        property_group="house",
        deal_type="exchange",
    ),
    CategoryDefinition(
        name="Yer sotish",
        path="nedvizhimost/zemlja/prodazha",
        olx_category_id=10,
        property_group="land",
        deal_type="sale",
    ),
    CategoryDefinition(
        name="Yer ijara",
        path="nedvizhimost/zemlja/arenda",
        olx_category_id=1533,
        property_group="land",
        deal_type="rent",
    ),
    CategoryDefinition(
        name="Garaj / parking sotish",
        path="nedvizhimost/garazhi-stoyanki/prodazha",
        olx_category_id=21,
        property_group="garage",
        deal_type="sale",
    ),
    CategoryDefinition(
        name="Garaj / parking ijara",
        path="nedvizhimost/garazhi-stoyanki/arenda",
        olx_category_id=28,
        property_group="garage",
        deal_type="rent",
    ),
    CategoryDefinition(
        name="Tijorat joylari sotish",
        path="nedvizhimost/kommercheskie-pomeshcheniya/prodazha",
        olx_category_id=14,
        property_group="commercial",
        deal_type="sale",
    ),
    CategoryDefinition(
        name="Tijorat joylari ijara",
        path="nedvizhimost/kommercheskie-pomeshcheniya/arenda",
        olx_category_id=11,
        property_group="commercial",
        deal_type="rent",
    ),
    CategoryDefinition(
        name="Hostel sutkalik ijara",
        path="nedvizhimost/posutochno_pochasovo/hostel",
        olx_category_id=1564,
        property_group="hostel",
        deal_type="rent_daily",
    ),
    CategoryDefinition(
        name="Mehmonxona / hotel sutkalik ijara",
        path="nedvizhimost/posutochno_pochasovo/oteli",
        olx_category_id=1565,
        property_group="hotel",
        deal_type="rent_daily",
    ),
    CategoryDefinition(
        name="Kvartira sutkalik ijara",
        path="nedvizhimost/posutochno_pochasovo/kvartira",
        olx_category_id=1566,
        property_group="apartment",
        deal_type="rent_daily",
    ),
    CategoryDefinition(
        name="Dacha / kottej sutkalik ijara",
        path="nedvizhimost/posutochno_pochasovo/dachi",
        olx_category_id=1567,
        property_group="house",
        deal_type="rent_daily",
    ),
    CategoryDefinition(
        name="Sanatoriy / dam olish uyi sutkalik ijara",
        path="nedvizhimost/posutochno_pochasovo/sanatorii",
        olx_category_id=1568,
        property_group="sanatorium",
        deal_type="rent_daily",
    ),
)


def default_category_paths() -> tuple[str, ...]:
    return tuple(category.path for category in DEFAULT_REAL_ESTATE_CATEGORIES)


def category_by_path(path: str) -> CategoryDefinition | None:
    normalized_path = _normalize_source_path(path)
    for category in DEFAULT_REAL_ESTATE_CATEGORIES:
        if category.path == normalized_path:
            return category
    return None


def category_for_source_path(path: str | None) -> CategoryDefinition | None:
    """Source URL city/district/query bilan kelganda ham asosiy categoryni topadi."""

    if not path:
        return None

    normalized_path = _normalize_source_path(path)
    for category in sorted(DEFAULT_REAL_ESTATE_CATEGORIES, key=lambda item: len(item.path), reverse=True):
        if normalized_path == category.path or normalized_path.startswith(category.path + "/"):
            return category
    return None


def _normalize_source_path(path: str) -> str:
    """OLX pathni label lookup uchun bir xil formatga keltiradi."""

    return path.strip().split("?", 1)[0].strip("/")
