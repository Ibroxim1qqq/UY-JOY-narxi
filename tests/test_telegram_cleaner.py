from __future__ import annotations

import unittest

from uyjoy_etl.telegram_cleaner import extract_real_estate_fields


class TelegramCleanerTest(unittest.TestCase):
    def test_splits_tashkent_city_address(self) -> None:
        row = _row(
            "Манзил: Олмазор тумани, Олмазор Ситида "
            "Нархи: 500$ 2 хона 62 м2"
        )

        record = extract_real_estate_fields(row)

        self.assertEqual(record["city_name"], "Toshkent shahri")
        self.assertEqual(record["district_name"], "Olmazor")
        self.assertEqual(record["neighborhood"], "Олмазор Ситида")

    def test_splits_tashkent_region_address(self) -> None:
        row = _row(
            "Манзил: Тошкент вилояти, Ўрта Чирчиқ тумани, "
            "Учхоз Ёшлик кўчаси, 4-уй, 11-хонадон. Нархи: 532.000.000 сўм"
        )

        record = extract_real_estate_fields(row)

        self.assertEqual(record["city_name"], "Toshkent viloyati")
        self.assertEqual(record["district_name"], "Orta Chirchiq")
        self.assertEqual(record["neighborhood"], "Учхоз Ёшлик")

    def test_splits_latin_address(self) -> None:
        row = _row("Manzil: Yunusobod tumani, 7-kvartal. Narxi: 85000$")

        record = extract_real_estate_fields(row)

        self.assertEqual(record["city_name"], "Toshkent shahri")
        self.assertEqual(record["district_name"], "Yunusobod")
        self.assertEqual(record["neighborhood"], "7-kvartal")

    def test_prefers_sum_currency_when_display_has_approx_usd(self) -> None:
        row = _row("Манзил: Олмазор тумани. Нархи: 1.830.000.000 сўм (≈150.000$)")

        record = extract_real_estate_fields(row)

        self.assertEqual(record["price_currency"], "UZS")
        self.assertEqual(str(record["price_value"]), "1830000000")


def _row(text: str) -> dict[str, object]:
    return {
        "channel_id": 1,
        "message_id": 1,
        "channel_username": "test",
        "channel_title": "Test",
        "post_url": "https://t.me/test/1",
        "posted_at": None,
        "text": text,
        "views": 1,
        "forwards": 0,
        "replies_count": 0,
        "has_media": False,
    }


if __name__ == "__main__":
    unittest.main()
