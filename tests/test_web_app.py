from __future__ import annotations

from datetime import date
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.security import HTTPBasicCredentials

from uyjoy_etl.web_app import _credentials_match, _parse_optional_date, _require_dashboard_auth, app
from uyjoy_etl.web_repository import ListingRepository, MarketInsightFilters


class WebAppAuthTest(unittest.TestCase):
    def test_credentials_match_expected_values(self) -> None:
        credentials = HTTPBasicCredentials(username="admin", password="secret")

        self.assertTrue(_credentials_match(credentials, "admin", "secret"))
        self.assertFalse(_credentials_match(credentials, "admin", "wrong"))

    def test_auth_is_disabled_when_credentials_are_not_configured(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(_require_dashboard_auth(None))


class MarketDashboardRouteTest(unittest.TestCase):
    def test_market_dashboard_route_and_template_exist(self) -> None:
        paths = {route.path for route in app.routes}
        template_path = Path(__file__).resolve().parents[1] / "src" / "uyjoy_etl" / "templates" / "market_dashboard.html"

        self.assertIn("/market-dashboard", paths)
        self.assertTrue(template_path.exists())

    def test_empty_query_date_is_accepted_as_none(self) -> None:
        self.assertIsNone(_parse_optional_date(""))
        self.assertEqual(_parse_optional_date("2026-07-17"), date(2026, 7, 17))

    def test_market_line_chart_points_include_daily_bar_and_tooltip_values(self) -> None:
        repository = ListingRepository(None)  # type: ignore[arg-type]
        rows = [
            {"label": "15.07", "avg_value": 1000, "listing_count": 4, "anomaly_count": 0},
            {"label": "16.07", "avg_value": 1800, "listing_count": 7, "anomaly_count": 1},
            {"label": "17.07", "avg_value": 1400, "listing_count": 5, "anomaly_count": 0},
        ]

        chart = repository._prepare_line_chart(
            rows,
            MarketInsightFilters(currency_code="UZS"),
            "O'rtacha narx",
        )

        self.assertEqual(chart["points"][1]["display"], "1,800 so'm")
        self.assertEqual(chart["points"][1]["count"], 7)
        self.assertGreater(chart["points"][1]["bar_height"], 0)
        self.assertGreater(chart["points"][1]["bar_width"], 0)
        self.assertEqual(chart["y_mid_short"], "1k so'm")

    def test_market_currency_is_forced_to_uzs(self) -> None:
        repository = ListingRepository(None)  # type: ignore[arg-type]
        filters = MarketInsightFilters(
            currency_code="USD",
            rooms="2",
            price_min=100,
            area_max=90,
        )
        currency_facets = [
            {"value": "USD", "count": 500, "day_count": 60},
            {"value": "UZS", "count": 120, "day_count": 60},
        ]

        normalized = repository._normalize_market_filters(filters)
        updated = repository._with_available_currency(filters, currency_facets)

        self.assertEqual(normalized.currency_code, "UZS")
        self.assertEqual(updated.currency_code, "UZS")
        self.assertEqual(updated.rooms, "2")
        self.assertEqual(updated.price_min, 100)
        self.assertEqual(updated.area_max, 90)
        self.assertEqual(updated.chart_mode, "avg7")

        daily = repository._normalize_market_filters(MarketInsightFilters(chart_mode="daily"))
        self.assertEqual(daily.chart_mode, "daily")

    def test_market_period_filters_support_all_relative_and_fixed_ranges(self) -> None:
        repository = ListingRepository(None)  # type: ignore[arg-type]

        default_filters = repository._normalize_market_filters(MarketInsightFilters())
        self.assertEqual(default_filters.period_mode, "all")
        self.assertEqual(default_filters.period_label, "Umumiy")

        fixed_filters = repository._normalize_market_filters(
            MarketInsightFilters(
                period_mode="fixed",
                date_from=date(2026, 7, 20),
                date_to=date(2026, 7, 10),
            )
        )
        self.assertEqual(fixed_filters.date_from, date(2026, 7, 10))
        self.assertEqual(fixed_filters.date_to, date(2026, 7, 20))

        where_sql, params = repository._build_market_where_clause(
            MarketInsightFilters(period_mode="relative", days=30)
        )
        self.assertIn("market_days", params)
        self.assertIn("coalesce(posted_at", where_sql)

    def test_tashkent_district_names_are_normalized_for_geojson_join(self) -> None:
        repository = ListingRepository(None)  # type: ignore[arg-type]

        self.assertEqual(repository._tashkent_district_key("Мирзо-Улугбекский район"), "mirzo_ulugbek")
        self.assertEqual(repository._tashkent_district_key("Сергелийский район"), "sergeli")
        self.assertEqual(repository._tashkent_district_key("Yunusobod district"), "yunusobod")
        self.assertEqual(repository._tashkent_district_key("Olmazor tumani"), "olmazor")


if __name__ == "__main__":
    unittest.main()
