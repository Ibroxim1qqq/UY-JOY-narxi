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


if __name__ == "__main__":
    unittest.main()
