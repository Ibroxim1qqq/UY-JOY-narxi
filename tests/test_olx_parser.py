from __future__ import annotations

import json
import unittest

from uyjoy_etl.olx_parser import build_db_record, parse_detail_page, parse_listing_page


def wrap_prerendered_state(state: dict) -> str:
    """Test uchun OLXdagi kabi double-encoded JS string yasaydi."""

    json_text = json.dumps(state, ensure_ascii=False)
    js_string = json.dumps(json_text, ensure_ascii=False)
    return f"<html><script>window.__PRERENDERED_STATE__= {js_string};</script></html>"


class OlxParserTest(unittest.TestCase):
    def test_parse_listing_page_reads_ads_and_pagination(self) -> None:
        html = wrap_prerendered_state(
            {
                "listing": {
                    "listing": {
                        "pageNumber": 0,
                        "totalPages": 25,
                        "totalElements": 1000,
                        "visibleElements": 59214,
                        "ads": [sample_ad()],
                    }
                }
            }
        )

        page = parse_listing_page(html)

        self.assertEqual(page.total_pages, 25)
        self.assertEqual(page.visible_elements, 59214)
        self.assertEqual(page.ads[0]["id"], 123)

    def test_parse_detail_page_reads_ad_payload(self) -> None:
        html = wrap_prerendered_state({"ad": {"ad": sample_ad()}})

        ad = parse_detail_page(html)

        self.assertEqual(ad["id"], 123)
        self.assertEqual(ad["title"], "Test kvartira")

    def test_build_db_record_keeps_raw_and_flattens_params(self) -> None:
        record = build_db_record(
            listing_ad=sample_ad(),
            source_category_path="nedvizhimost/kvartiry/prodazha",
            source_page=1,
            detail_ad=None,
        )

        self.assertEqual(record["olx_id"], 123)
        self.assertEqual(record["price_value"], 85000)
        self.assertEqual(record["city_name"], "Ташкент")
        self.assertEqual(record["param_values"]["total_area"]["normalizedValue"], "72")
        self.assertEqual(record["raw_listing"]["id"], 123)
        self.assertEqual(record["contact_phone"], "+998901234567")
        self.assertEqual(record["contact_source"], "olx_payload")


def sample_ad() -> dict:
    return {
        "id": 123,
        "title": "Test kvartira",
        "description": "Raw description",
        "category": {"id": 13, "type": "real_estate"},
        "url": "https://www.olx.uz/d/obyavlenie/test-ID123.html",
        "createdTime": "2026-07-13T10:00:00+05:00",
        "lastRefreshTime": "2026-07-13T11:00:00+05:00",
        "pushupTime": "2026-07-13T11:00:00+05:00",
        "validToTime": "2026-08-13T10:00:00+05:00",
        "isActive": True,
        "status": "active",
        "isBusiness": False,
        "price": {
            "displayValue": "85 000 у.е.",
            "regularPrice": {
                "value": 85000,
                "currencyCode": "UYE",
                "currencySymbol": "у.е.",
                "negotiable": True,
            },
        },
        "location": {
            "cityName": "Ташкент",
            "districtName": "Юнусабадский район",
            "regionName": "Ташкентская область",
            "pathName": "Ташкентская область, Ташкент, Юнусабадский район",
        },
        "map": {"lat": 41.3, "lon": 69.2},
        "params": [
            {
                "key": "number_of_rooms",
                "name": "Количество комнат",
                "type": "input",
                "value": "3",
                "normalizedValue": "3",
            },
            {
                "key": "total_area",
                "name": "Общая площадь",
                "type": "input",
                "value": "72 м²",
                "normalizedValue": "72",
            },
        ],
        "photos": ["https://example.com/photo.jpg"],
        "user": {"id": 777, "name": "Ali"},
        "contact": {"name": "Ali", "phone": "+998901234567"},
    }


if __name__ == "__main__":
    unittest.main()
