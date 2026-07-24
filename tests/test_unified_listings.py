from __future__ import annotations

import unittest

from uyjoy_etl import unified_listings


class UnifiedListingsSqlTest(unittest.TestCase):
    def test_olx_house_plot_is_mapped_to_land_sotix(self) -> None:
        sql = unified_listings._OLX_INSERT_SQL

        self.assertIn("param_values -> 'plot'", sql)
        self.assertIn("param_values -> 'land_area'", sql)
        self.assertLess(
            sql.index("param_values -> 'plot'"),
            sql.index("param_values -> 'land_area'"),
        )

    def test_refresh_merges_clean_listings_without_truncating_existing_rows(self) -> None:
        self.assertNotIn("truncate table real_estate_listings", unified_listings._OLX_INSERT_SQL.lower())
        self.assertNotIn("truncate table real_estate_listings", unified_listings._TELEGRAM_INSERT_SQL.lower())
        self.assertIn("on conflict (source, source_listing_id) do update", unified_listings._OLX_INSERT_SQL)
        self.assertIn("on conflict (source, source_listing_id) do update", unified_listings._TELEGRAM_INSERT_SQL)

    def test_refresh_function_does_not_clear_clean_table(self) -> None:
        database = _FakeDatabase()

        summary = unified_listings.refresh_unified_listings(database)  # type: ignore[arg-type]

        self.assertEqual(summary.total_rows, 7)
        self.assertFalse(
            any("truncate table real_estate_listings" in sql.lower() for sql in database.connection.statements)
        )


class _FakeDatabase:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def connect(self) -> "_FakeConnection":
        return self.connection


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str) -> "_FakeResult":
        self.statements.append(sql)
        return _FakeResult()

    def commit(self) -> None:
        return None


class _FakeResult:
    def fetchone(self) -> dict[str, int]:
        return {"total_rows": 7, "olx_rows": 4, "telegram_rows": 3}


if __name__ == "__main__":
    unittest.main()
