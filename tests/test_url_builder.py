from __future__ import annotations

import unittest

from uyjoy_etl.url_builder import append_query_params, build_listing_url


class UrlBuilderTest(unittest.TestCase):
    def test_builds_first_page_for_plain_path(self) -> None:
        url = build_listing_url(
            "https://www.olx.uz",
            "nedvizhimost/kvartiry/prodazha",
            page=1,
        )

        self.assertEqual(url, "https://www.olx.uz/nedvizhimost/kvartiry/prodazha/")

    def test_adds_page_to_plain_path(self) -> None:
        url = build_listing_url(
            "https://www.olx.uz",
            "nedvizhimost/kvartiry/prodazha",
            page=3,
        )

        self.assertEqual(url, "https://www.olx.uz/nedvizhimost/kvartiry/prodazha/?page=3")

    def test_preserves_district_query_and_replaces_page(self) -> None:
        url = build_listing_url(
            "https://www.olx.uz",
            "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=12&page=1",
            page=2,
        )

        self.assertEqual(
            url,
            "https://www.olx.uz/nedvizhimost/kvartiry/prodazha/tashkent/"
            "?search%5Bdistrict_id%5D=12&page=2",
        )

    def test_append_query_params_preserves_existing_query(self) -> None:
        path = append_query_params(
            "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=12",
            {
                "search[filter_float_number_of_rooms:from]": 2,
                "search[filter_float_number_of_rooms:to]": 2,
            },
        )

        self.assertEqual(
            path,
            "/nedvizhimost/kvartiry/prodazha/tashkent"
            "?search%5Bdistrict_id%5D=12"
            "&search%5Bfilter_float_number_of_rooms%3Afrom%5D=2"
            "&search%5Bfilter_float_number_of_rooms%3Ato%5D=2",
        )


if __name__ == "__main__":
    unittest.main()
