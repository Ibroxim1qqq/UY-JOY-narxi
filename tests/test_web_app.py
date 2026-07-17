from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.security import HTTPBasicCredentials

from uyjoy_etl.web_app import _credentials_match, _require_dashboard_auth, app


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


if __name__ == "__main__":
    unittest.main()
