from __future__ import annotations

import unittest

from uyjoy_etl.category_catalog import category_by_path, category_for_source_path, default_category_paths


class CategoryCatalogTest(unittest.TestCase):
    def test_default_categories_include_all_real_estate_leaf_paths(self) -> None:
        paths = set(default_category_paths())

        self.assertIn("nedvizhimost/kvartiry/prodazha", paths)
        self.assertIn("nedvizhimost/doma/prodazha", paths)
        self.assertIn("nedvizhimost/zemlja/prodazha", paths)
        self.assertIn("nedvizhimost/kommercheskie-pomeshcheniya/arenda", paths)
        self.assertIn("nedvizhimost/posutochno_pochasovo/sanatorii", paths)

    def test_category_by_path_matches_exact_path(self) -> None:
        category = category_by_path("/nedvizhimost/kvartiry/prodazha/")

        self.assertIsNotNone(category)
        self.assertEqual(category.name, "Kvartira sotish")

    def test_category_for_source_path_matches_city_and_query_source(self) -> None:
        category = category_for_source_path(
            "/nedvizhimost/kvartiry/prodazha/tashkent?search%5Bdistrict_id%5D=12"
        )

        self.assertIsNotNone(category)
        self.assertEqual(category.path, "nedvizhimost/kvartiry/prodazha")


if __name__ == "__main__":
    unittest.main()
