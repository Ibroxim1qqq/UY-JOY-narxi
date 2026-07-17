from __future__ import annotations

import unittest
from decimal import Decimal

from uyjoy_etl.web_repository import ListingFilters, ListingRepository, MarketInsightFilters, parse_decimal


class _QueryCapture:
    def __init__(self) -> None:
        self.sql = ""

    def execute(self, sql: str, params: dict[str, object]) -> "_QueryCapture":
        self.sql = sql
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return []


class WebRepositoryTest(unittest.TestCase):
    def test_parse_decimal_accepts_space_grouping(self) -> None:
        self.assertEqual(parse_decimal("1 250 000"), Decimal("1250000"))

    def test_parse_decimal_accepts_comma_decimal_separator(self) -> None:
        self.assertEqual(parse_decimal("12,5"), Decimal("12.5"))

    def test_parse_decimal_returns_none_for_invalid_value(self) -> None:
        self.assertIsNone(parse_decimal("narx"))

    def test_build_where_clause_accepts_dashboard_filters(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        where_sql, params = repository._build_where_clause(
            ListingFilters(
                deal_type="sale",
                district="Юнусабадский район",
                rooms="2",
            )
        )

        self.assertIn("deal_type = %(deal_type)s", where_sql)
        self.assertIn("quality_status", where_sql)
        self.assertIn("district_name = %(district)s", where_sql)
        self.assertIn("room_count = %(rooms)s", where_sql)
        self.assertEqual(params["deal_type"], "sale")
        self.assertEqual(params["district"], "Юнусабадский район")
        self.assertEqual(params["rooms"], 2)

    def test_build_where_clause_supports_seven_plus_rooms(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        where_sql, params = repository._build_where_clause(ListingFilters(rooms="7plus"))

        self.assertIn("room_count >= 7", where_sql)
        self.assertIn("quality_status", where_sql)
        self.assertNotIn("rooms", params)

    def test_build_where_clause_hides_suspicious_by_default(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        where_sql, params = repository._build_where_clause(ListingFilters())

        self.assertIn("quality_status", where_sql)
        self.assertEqual(params, {})

    def test_build_where_clause_filters_category_prefix(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        where_sql, params = repository._build_where_clause(
            ListingFilters(category="nedvizhimost/kvartiry/prodazha")
        )

        self.assertIn("source_category like %(category_prefix)s", where_sql)
        self.assertEqual(params["category"], "nedvizhimost/kvartiry/prodazha")
        self.assertEqual(params["category_prefix"], "nedvizhimost/kvartiry/prodazha/%")

    def test_build_where_clause_filters_source(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        where_sql, params = repository._build_where_clause(ListingFilters(source="telegram"))

        self.assertIn("source = %(source)s", where_sql)
        self.assertEqual(params["source"], "telegram")

    def test_market_auto_metric_prefers_rent_price_then_apartment_m2(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        rent_trend = repository._market_trend_sql(MarketInsightFilters(deal_type="rent", metric="auto"))
        apartment_trend = repository._market_trend_sql(
            MarketInsightFilters(property_type="apartment", metric="auto")
        )

        self.assertEqual(rent_trend["value_expression"], "price_value")
        self.assertIn("area_m2", apartment_trend["extra_predicate"])

    def test_market_trend_query_scores_listing_level_outliers(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]
        capture = _QueryCapture()

        repository._query_market_trend_rows(
            capture,
            "where (quality_status is null or quality_status = 'ok')",
            {},
            MarketInsightFilters(currency_code="UZS", days=60),
            repository._market_trend_sql(MarketInsightFilters(metric="avg_price_m2")),
        )

        self.assertIn("segment_stats", capture.sql)
        self.assertIn("percentile_cont(0.25)", capture.sql)
        self.assertIn("is_listing_anomaly", capture.sql)
        self.assertIn("room_key", capture.sql)


if __name__ == "__main__":
    unittest.main()
