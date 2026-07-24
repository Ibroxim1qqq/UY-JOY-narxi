from __future__ import annotations

import unittest

from uyjoy_etl.web_repository import ListingRepository, canonical_district_value


class _QueryCaptureContext:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.sql = ""
        self.params: dict[str, object] = {}
        self.row = row or {}

    def __enter__(self) -> "_QueryCaptureContext":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, params: dict[str, object] | None = None) -> "_QueryCaptureContext":
        self.sql = sql
        self.params = params or {}
        return self

    def fetchone(self) -> dict[str, object]:
        return self.row


class _FakeDatabase:
    def __init__(self, connection: _QueryCaptureContext) -> None:
        self.connection = connection

    def connect(self) -> "_QueryCaptureContext":
        return self.connection


class WebRepositoryTest(unittest.TestCase):
    def test_canonical_district_accepts_cyrillic_alias(self) -> None:
        self.assertEqual(canonical_district_value("Юнусабадский район"), "Yunusobod")

    def test_market_context_uses_bi_view_and_30_day_window(self) -> None:
        row = {
            "listing_count": 5,
            "median_price_uzs": 900_000_000,
            "median_unit_price_uzs": 15_000_000,
        }
        capture = _QueryCaptureContext(row)
        repository = ListingRepository(_FakeDatabase(capture))  # type: ignore[arg-type]

        context = repository.get_apartment_valuation_market_context("Chilonzor")

        self.assertEqual(context["listing_count"], 5)
        self.assertEqual(context["district"], "Chilonzor")
        self.assertIn("bi_tashkent_sale_market", capture.sql)
        self.assertIn("interval '30 days'", capture.sql)
        self.assertIn("property_segment = 'Kvartira'", capture.sql)
        self.assertEqual(capture.params["district"], "Chilonzor")

    def test_stats_counts_core_listing_tables(self) -> None:
        capture = _QueryCaptureContext({"total_listings": 12, "sale_apartment_listings": 7})
        repository = ListingRepository(_FakeDatabase(capture))  # type: ignore[arg-type]

        stats = repository.get_stats()

        self.assertEqual(stats["total_listings"], 12)
        self.assertEqual(stats["sale_apartment_listings"], 7)
        self.assertIn("from real_estate_listings", capture.sql)


if __name__ == "__main__":
    unittest.main()
