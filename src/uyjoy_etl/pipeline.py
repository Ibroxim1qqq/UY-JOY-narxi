from __future__ import annotations

import logging

from uyjoy_etl.config import AppConfig
from uyjoy_etl.db import Database
from uyjoy_etl.http_client import OlxHttpClient
from uyjoy_etl.olx_parser import (
    OlxParseError,
    build_db_record,
    parse_detail_page,
    parse_listing_page,
)
from uyjoy_etl.url_builder import build_listing_url

logger = logging.getLogger(__name__)


class OlxRawPipeline:
    """OLX public listing/detail sahifalaridan raw data olib Postgresga yozadi."""

    def __init__(self, config: AppConfig, database: Database) -> None:
        self._config = config
        self._database = database
        self._client = OlxHttpClient(config.olx)

    def run(
        self,
        category_paths: tuple[str, ...] | None = None,
        max_pages_per_category: int | None = None,
        fetch_details: bool | None = None,
    ) -> None:
        categories = category_paths or self._config.olx.category_paths
        max_pages = max_pages_per_category or self._config.olx.max_pages_per_category
        should_fetch_details = (
            self._config.olx.fetch_details if fetch_details is None else fetch_details
        )

        run_id = self._database.start_run(
            source="olx.uz",
            categories=categories,
            max_pages_per_category=max_pages,
        )

        try:
            for category_path in categories:
                self._scrape_category(
                    run_id=run_id,
                    category_path=category_path,
                    max_pages=max_pages,
                    fetch_details=should_fetch_details,
                )
            self._database.finish_run(run_id, "success")
        except Exception as exc:
            logger.exception("ETL run xato bilan tugadi | run_id=%s", run_id)
            self._database.finish_run(run_id, "failed", str(exc))
            raise

    def _scrape_category(
        self,
        run_id: str,
        category_path: str,
        max_pages: int,
        fetch_details: bool,
    ) -> None:
        logger.info(
            "Kategoriya boshlandi | category=%s | max_pages=%s | fetch_details=%s",
            category_path,
            max_pages,
            fetch_details,
        )

        for page in range(1, max_pages + 1):
            page_url = self._build_listing_url(category_path, page)
            fetch_result = self._client.get(page_url)
            self._database.log_fetch(
                run_id=run_id,
                url=fetch_result.url,
                http_status=fetch_result.status_code,
                elapsed_ms=fetch_result.elapsed_ms,
                ok=fetch_result.ok,
                error_message=fetch_result.error_message,
            )

            if not fetch_result.ok or not fetch_result.text:
                logger.warning("Listing page olinmadi | category=%s | page=%s", category_path, page)
                continue

            try:
                listing_page = parse_listing_page(fetch_result.text)
            except OlxParseError as exc:
                logger.warning(
                    "Listing page parse bo'lmadi | category=%s | page=%s | error=%s",
                    category_path,
                    page,
                    exc,
                )
                continue

            self._database.increment_run_counters(
                run_id,
                pages_processed=1,
                listings_seen=len(listing_page.ads),
            )
            logger.info(
                "Listing page parse bo'ldi | category=%s | page=%s | ads=%s | total_pages=%s",
                category_path,
                page,
                len(listing_page.ads),
                listing_page.total_pages,
            )

            for listing_ad in listing_page.ads:
                self._process_ad(
                    run_id=run_id,
                    category_path=category_path,
                    source_page=page,
                    listing_ad=listing_ad,
                    fetch_details=fetch_details,
                )

            if page >= listing_page.total_pages:
                logger.info(
                    "Kategoriya oxirgi sahifaga yetdi | category=%s | page=%s",
                    category_path,
                    page,
                )
                break

        logger.info("Kategoriya tugadi | category=%s", category_path)

    def _process_ad(
        self,
        run_id: str,
        category_path: str,
        source_page: int,
        listing_ad: dict,
        fetch_details: bool,
    ) -> None:
        detail_ad = None
        detail_url = listing_ad.get("url")
        olx_id = listing_ad.get("id")

        if fetch_details and detail_url:
            detail_fetch = self._client.get(detail_url)
            self._database.log_fetch(
                run_id=run_id,
                url=detail_fetch.url,
                http_status=detail_fetch.status_code,
                elapsed_ms=detail_fetch.elapsed_ms,
                ok=detail_fetch.ok,
                error_message=detail_fetch.error_message,
            )
            if detail_fetch.ok and detail_fetch.text:
                try:
                    detail_ad = parse_detail_page(detail_fetch.text)
                    self._database.increment_run_counters(run_id, detail_pages_fetched=1)
                    logger.info("Detail parse bo'ldi | olx_id=%s | url=%s", olx_id, detail_url)
                except OlxParseError as exc:
                    logger.warning(
                        "Detail parse bo'lmadi | olx_id=%s | url=%s | error=%s",
                        olx_id,
                        detail_url,
                        exc,
                    )

        record = build_db_record(
            listing_ad=listing_ad,
            source_category_path=category_path,
            source_page=source_page,
            detail_ad=detail_ad,
        )
        action = self._database.upsert_listing(record)
        self._database.increment_run_counters(
            run_id,
            rows_inserted=1 if action == "inserted" else 0,
            rows_updated=1 if action == "updated" else 0,
        )

    def _build_listing_url(self, category_path: str, page: int) -> str:
        return build_listing_url(self._config.olx.base_url, category_path, page)
