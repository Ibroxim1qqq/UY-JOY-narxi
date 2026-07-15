from __future__ import annotations

import unittest

from uyjoy_etl.contact_import import contact_record_from_row


class ContactImportTest(unittest.TestCase):
    def test_contact_record_from_row_matches_by_olx_id(self) -> None:
        record = contact_record_from_row(
            {"olx_id": "65095280", "phone": "+998901234567", "contact_name": "Ali"},
            source="authorized_test",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["olx_id"], 65095280)
        self.assertEqual(record["contact_phone"], "+998901234567")
        self.assertEqual(record["contact_name"], "Ali")
        self.assertEqual(record["contact_source"], "authorized_test")

    def test_contact_record_from_row_matches_by_url(self) -> None:
        record = contact_record_from_row(
            {
                "listing_url": "https://www.olx.uz/d/obyavlenie/test-ID123.html",
                "nomer": "+998991112233",
            },
            source="authorized_test",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertIsNone(record["olx_id"])
        self.assertEqual(record["contact_phone"], "+998991112233")

    def test_contact_record_from_row_skips_missing_phone(self) -> None:
        self.assertIsNone(contact_record_from_row({"olx_id": "1"}, source="authorized_test"))


if __name__ == "__main__":
    unittest.main()
