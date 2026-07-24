from __future__ import annotations

import unittest

from uyjoy_etl.market_quality import SUSPICIOUS_CASES, market_quality_passes_sql, market_quality_reasons_sql


class MarketQualityTest(unittest.TestCase):
    def test_quality_cases_document_core_unrealistic_rules(self) -> None:
        joined = "\n".join(SUSPICIOUS_CASES)

        self.assertIn("1 xonali kvartira 80 m2", joined)
        self.assertIn("$5 000", joined)
        self.assertIn("sotix narxi", joined)

    def test_market_quality_sql_contains_apartment_sale_thresholds(self) -> None:
        sql = market_quality_reasons_sql(price_uzs_expr="price_uzs")

        self.assertIn("apartment_one_room_area_too_large", sql)
        self.assertIn("sale_apartment_unit_price_too_high", sql)
        self.assertIn("60466750.00", sql)
        self.assertIn("floor_greater_than_total_floors", sql)

    def test_market_quality_pass_clause_uses_empty_reason_array(self) -> None:
        sql = market_quality_passes_sql(price_uzs_expr="price_uzs")

        self.assertIn("coalesce(array_length", sql)
        self.assertIn("= 0", sql)


if __name__ == "__main__":
    unittest.main()
