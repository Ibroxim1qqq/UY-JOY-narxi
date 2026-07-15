from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from uyjoy_etl.config import AppConfig
from uyjoy_etl.http_client import OlxHttpClient
from uyjoy_etl.olx_parser import parse_listing_page
from uyjoy_etl.url_builder import append_query_params, build_listing_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceInspection:
    """Bitta listing source bo'yicha pagination va facet holati."""

    listing_path: str
    url: str
    ads_count: int
    total_pages: int
    total_elements: int
    visible_elements: int
    facets: dict[str, list[dict[str, Any]]]


@dataclass(frozen=True)
class DiscoveredSource:
    """Scraping uchun tayyorlangan source URL path."""

    path: str
    visible_elements: int
    total_pages: int
    split_level: int


def inspect_listing_source(config: AppConfig, listing_path: str) -> SourceInspection:
    """OLX source pathni ochib, qaysi facetlar borligini ko'rsatish uchun o'qiydi."""

    client = OlxHttpClient(config.olx)
    url = build_listing_url(config.olx.base_url, listing_path, page=1)
    result = client.get(url)
    if not result.ok or not result.text:
        raise RuntimeError(f"Source olinmadi: status={result.status_code}, url={url}")

    page = parse_listing_page(result.text)
    listing = page.state["listing"]["listing"]
    raw_facets = (listing.get("metaData") or {}).get("facets") or {}
    facets = raw_facets if isinstance(raw_facets, dict) else {}

    return SourceInspection(
        listing_path=listing_path,
        url=url,
        ads_count=len(page.ads),
        total_pages=page.total_pages,
        total_elements=page.total_elements,
        visible_elements=page.visible_elements,
        facets=facets,
    )


def discover_sources(
    config: AppConfig,
    root_paths: tuple[str, ...],
    max_visible_per_source: int = 1000,
    max_depth: int = 4,
    include_room_market_splits: bool = False,
) -> list[DiscoveredSource]:
    """Katta OLX kategoriyalarni kichik source URLlarga bo'lib chiqadi."""

    client = OlxHttpClient(config.olx)
    discovered: list[DiscoveredSource] = []
    seen: set[str] = set()

    for root_path in root_paths:
        _discover_one(
            config=config,
            client=client,
            path=root_path,
            discovered=discovered,
            seen=seen,
            max_visible_per_source=max_visible_per_source,
            max_depth=max_depth,
            depth=0,
            include_room_market_splits=include_room_market_splits,
        )

    discovered.sort(key=lambda item: item.visible_elements, reverse=True)
    return discovered


def _discover_one(
    config: AppConfig,
    client: OlxHttpClient,
    path: str,
    discovered: list[DiscoveredSource],
    seen: set[str],
    max_visible_per_source: int,
    max_depth: int,
    depth: int,
    include_room_market_splits: bool,
) -> None:
    normalized_path = path.strip()
    if not normalized_path or normalized_path in seen:
        return
    seen.add(normalized_path)

    try:
        inspection = _inspect_with_client(config, client, normalized_path)
    except RuntimeError as exc:
        logger.warning("Source discovery skip qilindi | path=%s | error=%s", normalized_path, exc)
        return
    if inspection.visible_elements == 0:
        return

    facet_items = _facet_items(inspection.facets)
    if facet_items and depth < max_depth:
        for item in facet_items:
            url = item.get("url")
            if url:
                _discover_one(
                    config=config,
                    client=client,
                    path=url,
                    discovered=discovered,
                    seen=seen,
                    max_visible_per_source=max_visible_per_source,
                    max_depth=max_depth,
                    depth=depth + 1,
                    include_room_market_splits=include_room_market_splits,
                )
        return

    if (
        include_room_market_splits
        and inspection.visible_elements > max_visible_per_source
        and depth < max_depth + 2
    ):
        split_paths = _room_market_split_paths(normalized_path)
        for split_path in split_paths:
            _discover_one(
                config=config,
                client=client,
                path=split_path,
                discovered=discovered,
                seen=seen,
                max_visible_per_source=max_visible_per_source,
                max_depth=max_depth,
                depth=depth + 1,
                include_room_market_splits=False,
            )
        return

    discovered.append(
        DiscoveredSource(
            path=normalized_path,
            visible_elements=inspection.visible_elements,
            total_pages=inspection.total_pages,
            split_level=depth,
        )
    )


def _inspect_with_client(config: AppConfig, client: OlxHttpClient, listing_path: str) -> SourceInspection:
    url = build_listing_url(config.olx.base_url, listing_path, page=1)
    result = client.get(url)
    if not result.ok or not result.text:
        raise RuntimeError(f"Source olinmadi: status={result.status_code}, url={url}")

    page = parse_listing_page(result.text)
    listing = page.state["listing"]["listing"]
    raw_facets = (listing.get("metaData") or {}).get("facets") or {}
    facets = raw_facets if isinstance(raw_facets, dict) else {}

    return SourceInspection(
        listing_path=listing_path,
        url=url,
        ads_count=len(page.ads),
        total_pages=page.total_pages,
        total_elements=page.total_elements,
        visible_elements=page.visible_elements,
        facets=facets,
    )


def _facet_items(facets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    priority = ("district", "city", "region")
    for facet_name in priority:
        items = facets.get(facet_name)
        if items:
            return items
    return []


def _room_market_split_paths(path: str) -> list[str]:
    paths: list[str] = []
    market_values = ("primary", "secondary")
    for rooms in range(1, 8):
        for market in market_values:
            paths.append(
                append_query_params(
                    path,
                    {
                        "search[filter_float_number_of_rooms:from]": rooms,
                        "search[filter_float_number_of_rooms:to]": rooms,
                        "search[filter_enum_type_of_market][0]": market,
                    },
                )
            )
    return paths
