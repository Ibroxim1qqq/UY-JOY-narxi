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
        house_sale_trend = repository._market_trend_sql(
            MarketInsightFilters(deal_type="sale", property_type="house", metric="auto")
        )

        self.assertIn("currency_code = 'USD'", rent_trend["value_expression"])
        self.assertIn("12093.35", rent_trend["value_expression"])
        self.assertIn("area_m2", apartment_trend["extra_predicate"])
        self.assertIn("area_m2 >= 10", apartment_trend["extra_predicate"])
        self.assertIn("area_m2 <= 1000", apartment_trend["extra_predicate"])
        self.assertIn("land_sotix", house_sale_trend["extra_predicate"])
        self.assertEqual(house_sale_trend["label"], "O'rtacha sotix narxi")

    def test_market_trend_query_converts_prices_and_keeps_daily_counts(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]
        capture = _QueryCapture()

        repository._query_market_trend_rows(
            capture,
            "where (quality_status is null or quality_status = 'ok')",
            {},
            MarketInsightFilters(currency_code="UZS", days=60),
            repository._market_trend_sql(MarketInsightFilters(metric="avg_price_m2")),
        )

        self.assertIn("currency_code = 'USD'", capture.sql)
        self.assertIn("12093.35", capture.sql)
        self.assertIn("listing_count", capture.sql)
        self.assertNotIn("currency_code = %(currency_code)s", capture.sql)

    def test_market_where_clause_applies_price_and_area_filters(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        where_sql, params = repository._build_market_where_clause(
            MarketInsightFilters(
                price_min=Decimal("100000000"),
                price_max=Decimal("500000000"),
                area_min=Decimal("40"),
                area_max=Decimal("90"),
            )
        )

        self.assertIn("currency_code = 'USD'", where_sql)
        self.assertIn("market_price_min", params)
        self.assertIn("market_price_max", params)
        self.assertIn("area_m2 >= %(market_area_min)s", where_sql)
        self.assertIn("area_m2 <= %(market_area_max)s", where_sql)

    def test_smooth_svg_path_uses_curves_for_three_or_more_points(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        path = repository._smooth_svg_path([(70, 120), (120, 90), (170, 130)])

        self.assertTrue(path.startswith("M 70 120"))
        self.assertIn(" C ", path)

    def test_format_trend_money_supports_sotix_suffix(self) -> None:
        repository = ListingRepository(database=None)  # type: ignore[arg-type]

        self.assertEqual(
            repository._format_trend_money(1234567, "UZS", "O'rtacha sotix narxi"),
            "1,234,567 so'm / sotix",
        )

if __name__ == "__main__":
    unittest.main()
