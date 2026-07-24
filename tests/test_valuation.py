from __future__ import annotations

import unittest
from pathlib import Path

from uyjoy_etl.valuation import (
    ApartmentModelBundle,
    ApartmentValuationInput,
    ApartmentValuationService,
    MODEL_UNIT_PRICE_SCALE,
    ValuationInputError,
    ValuationModelError,
    district_aliases_for_model,
    build_apartment_valuation_response,
    parse_apartment_valuation_payload,
)


class ApartmentValuationTest(unittest.TestCase):
    def test_parse_payload_rejects_invalid_values(self) -> None:
        valid = {
            "district": "Yunusobod",
            "rooms": 2,
            "area_m2": 58,
            "floor_number": 4,
            "total_floors": 9,
            "currency": "UZS",
        }

        with self.assertRaises(ValuationInputError):
            parse_apartment_valuation_payload({**valid, "area_m2": 8})
        with self.assertRaises(ValuationInputError):
            parse_apartment_valuation_payload({**valid, "rooms": 11})
        with self.assertRaises(ValuationInputError):
            parse_apartment_valuation_payload({**valid, "floor_number": 10, "total_floors": 9})
        with self.assertRaises(ValuationInputError):
            parse_apartment_valuation_payload({**valid, "currency": "EUR"})

    def test_feature_builder_fills_numeric_columns_and_district_alias(self) -> None:
        model = _FakeModel(2_000_000)
        columns = (
            "room_count",
            "area_m2",
            "floor_number",
            "total_floors",
            "area_per_room",
            "room_2",
            "district_room_Yunusobod_2",
            "district_\u042e\u043d\u0443\u0441\u0430\u0431\u0430\u0434\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
        )
        service = ApartmentValuationService(bundle=ApartmentModelBundle(model=model, columns=columns))

        prediction = service.predict(
            ApartmentValuationInput(
                district="Yunusobod",
                rooms=2,
                area_m2=58,
                floor_number=4,
                total_floors=9,
            )
        )

        self.assertEqual(model.last_values[0][:4], [2.0, 58.0, 4.0, 9.0])
        self.assertAlmostEqual(model.last_values[0][4], 29.0)
        self.assertEqual(model.last_values[0][5], 1.0)
        self.assertEqual(model.last_values[0][6], 1.0)
        self.assertEqual(model.last_values[0][7], 1.0)
        self.assertAlmostEqual(prediction.unit_price_uzs, 2_000_000 * MODEL_UNIT_PRICE_SCALE)
        self.assertAlmostEqual(prediction.price_uzs, 2_000_000 * MODEL_UNIT_PRICE_SCALE * 58)
        self.assertEqual(prediction.warnings, ())

    def test_unknown_district_warns_but_predicts(self) -> None:
        model = _FakeModel(1_800_000)
        service = ApartmentValuationService(
            bundle=ApartmentModelBundle(
                model=model,
                columns=("room_count", "area_m2", "floor_number", "total_floors", "district_Test"),
            )
        )

        prediction = service.predict(
            ApartmentValuationInput(
                district="Notanish tuman",
                rooms=1,
                area_m2=35,
                floor_number=2,
                total_floors=5,
            )
        )

        self.assertAlmostEqual(prediction.price_uzs, 1_800_000 * MODEL_UNIT_PRICE_SCALE * 35)
        self.assertTrue(prediction.warnings)
        self.assertEqual(model.last_values[0][-1], 0.0)

    def test_missing_model_path_raises_friendly_error(self) -> None:
        service = ApartmentValuationService(model_path=Path("missing-apartment-model.pkl"))

        with self.assertRaises(ValuationModelError):
            service.predict(
                ApartmentValuationInput(
                    district="Yunusobod",
                    rooms=2,
                    area_m2=58,
                    floor_number=4,
                    total_floors=9,
                )
            )

    def test_district_aliases_include_cyrillic_model_name(self) -> None:
        aliases = district_aliases_for_model("Yunusobod")

        self.assertIn(
            "\u042e\u043d\u0443\u0441\u0430\u0431\u0430\u0434\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
            aliases,
        )

    def test_response_uses_calibrated_total_without_scale_warning(self) -> None:
        service = ApartmentValuationService(
            bundle=ApartmentModelBundle(
                model=_FakeModel(2_591_901.25),
                columns=("room_count", "area_m2", "floor_number", "total_floors", "district_Yunusobod"),
            )
        )
        request = ApartmentValuationInput(
            district="Yunusobod",
            rooms=2,
            area_m2=58,
            floor_number=4,
            total_floors=9,
        )
        prediction = service.predict(request)

        response = build_apartment_valuation_response(
            request,
            prediction,
            {
                "district": "Yunusobod",
                "listing_count": 543,
                "district_median_price_uzs": 886_344_100,
                "district_unit_price_uzs": 15_784_210,
            },
        )

        self.assertAlmostEqual(
            response["prediction"]["price_uzs"],
            2_591_901.25 * MODEL_UNIT_PRICE_SCALE * 58,
            places=2,
        )
        self.assertNotIn("target scale", " ".join(response["warnings"]))


class _FakeModel:
    def __init__(self, prediction: float) -> None:
        self.prediction = prediction
        self.last_values: list[list[float]] = []

    def predict(self, values) -> list[float]:
        self.last_values = values.tolist()
        return [self.prediction]


if __name__ == "__main__":
    unittest.main()
