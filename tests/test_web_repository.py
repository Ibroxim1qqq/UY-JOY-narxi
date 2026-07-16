from __future__ import annotations

import unittest
from decimal import Decimal

from uyjoy_etl.web_repository import ListingFilters, ListingRepository, parse_decimal


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


if __name__ == "__main__":
    unittest.main()
