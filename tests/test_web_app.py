from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from uyjoy_etl.web_app import _credentials_match, _require_dashboard_auth, apartment_valuation_api, app
from uyjoy_etl.valuation import ApartmentPrediction, ValuationModelError


class WebAppAuthTest(unittest.TestCase):
    def test_credentials_match_expected_values(self) -> None:
        credentials = HTTPBasicCredentials(username="admin", password="secret")

        self.assertTrue(_credentials_match(credentials, "admin", "secret"))
        self.assertFalse(_credentials_match(credentials, "admin", "wrong"))

    def test_auth_is_disabled_when_credentials_are_not_configured(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(_require_dashboard_auth(None))


class CoreValuationRouteTest(unittest.TestCase):
    def test_only_core_web_routes_exist(self) -> None:
        paths = {route.path for route in app.routes}
        template_path = Path(__file__).resolve().parents[1] / "src" / "uyjoy_etl" / "templates" / "new_dashboard.html"

        self.assertIn("/", paths)
        self.assertIn("/new-dashboard", paths)
        self.assertIn("/api/apartment-valuation", paths)
        self.assertIn("/health", paths)
        self.assertTrue(template_path.exists())
        self.assertNotIn("/listings", paths)
        self.assertNotIn("/analytics", paths)
        self.assertNotIn("/market-dashboard", paths)
        self.assertNotIn("/api/new-dashboard", paths)
        self.assertNotIn("/api/powerbi/listings.csv", paths)
        self.assertNotIn("/api/looker/listings_lite.csv", paths)

    def test_apartment_valuation_api_returns_prediction_contract(self) -> None:
        payload = {
            "district": "Yunusobod",
            "rooms": 2,
            "area_m2": 58,
            "floor_number": 4,
            "total_floors": 9,
            "currency": "UZS",
        }
        with patch("uyjoy_etl.web_app.apartment_valuation_service") as service, patch(
            "uyjoy_etl.web_app.repository"
        ) as repository:
            service.predict.return_value = ApartmentPrediction(
                price_uzs=1_200_000_000,
                price_usd=99_228.92,
                unit_price_uzs=20_689_655.17,
                unit_price_usd=1_710.84,
                warnings=(),
            )
            repository.get_apartment_valuation_market_context.return_value = {
                "district": "Yunusobod",
                "listing_count": 12,
                "district_median_price_uzs": 1_000_000_000,
                "district_unit_price_uzs": 17_000_000,
            }

            data = apartment_valuation_api(payload)

        self.assertIn("prediction", data)
        self.assertIn("market_context", data)
        self.assertEqual(data["prediction"]["price_uzs"], 1_200_000_000)
        self.assertEqual(data["market_context"]["difference_display"], "+20.0%")

    def test_apartment_valuation_api_rejects_invalid_floor(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            apartment_valuation_api(
                {
                    "district": "Yunusobod",
                    "rooms": 2,
                    "area_m2": 58,
                    "floor_number": 10,
                    "total_floors": 9,
                    "currency": "UZS",
                }
            )

        self.assertEqual(raised.exception.status_code, 422)

    def test_apartment_valuation_api_model_error_is_503(self) -> None:
        with patch("uyjoy_etl.web_app.apartment_valuation_service") as service:
            service.predict.side_effect = ValuationModelError("model missing")
            with self.assertRaises(HTTPException) as raised:
                apartment_valuation_api(
                    {
                        "district": "Yunusobod",
                        "rooms": 2,
                        "area_m2": 58,
                        "floor_number": 4,
                        "total_floors": 9,
                        "currency": "UZS",
                    }
                )

        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
