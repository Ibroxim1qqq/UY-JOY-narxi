from __future__ import annotations

import math
import pickle
import warnings
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from uyjoy_etl.web_repository import USD_TO_UZS_RATE


MODEL_PATH = Path(__file__).resolve().parent / "models" / "apartment_model.pkl"
# Legacy pickles returned an uncalibrated unit-price score, not total UZS.
# New model files store unit_price_scale=1.0 in metadata.
MODEL_UNIT_PRICE_SCALE = 5.3649


class ValuationInputError(ValueError):
    """Foydalanuvchi kiritgan baholash parametrlari yaroqsiz."""


class ValuationModelError(RuntimeError):
    """Model yuklanmadi yoki yaroqli prognoz qaytarmadi."""


@dataclass(frozen=True)
class ApartmentValuationInput:
    district: str
    rooms: int
    area_m2: float
    floor_number: int
    total_floors: int
    currency: str = "UZS"


@dataclass(frozen=True)
class ApartmentModelBundle:
    model: Any
    columns: tuple[str, ...]
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ApartmentPrediction:
    price_uzs: float
    price_usd: float
    unit_price_uzs: float
    unit_price_usd: float
    warnings: tuple[str, ...]


DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "Bektemir": (
        "Bektemir",
        "Bektemir tumani",
        "\u0411\u0435\u043a\u0442\u0435\u043c\u0438\u0440\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Chilonzor": (
        "Chilonzor",
        "Chilonzor tumani",
        "\u0427\u0438\u043b\u0430\u043d\u0437\u0430\u0440\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
        "\u0427\u0438\u043b\u043e\u043d\u0437\u043e\u0440 \u0442\u0443\u043c\u0430\u043d\u0438",
    ),
    "Mirobod": (
        "Mirobod",
        "Mirobod tumani",
        "\u041c\u0438\u0440\u0430\u0431\u0430\u0434",
        "\u041c\u0438\u0440\u0430\u0431\u0430\u0434\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Mirzo Ulug'bek": (
        "Mirzo Ulugbek",
        "Mirzo Ulug'bek",
        "Mirzo Ulugbek tumani",
        "\u041c\u0438\u0440\u0437\u043e-\u0423\u043b\u0443\u0433\u0431\u0435\u043a\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
        "\u041c\u0438\u0440\u0437\u043e \u0423\u043b\u0443\u0493\u0431\u0435\u043a \u0442\u0443\u043c\u0430\u043d\u0438",
    ),
    "Olmazor": (
        "Olmazor",
        "Olmazor tumani",
        "\u0410\u043b\u043c\u0430\u0437\u0430\u0440\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Sergeli": (
        "Sergeli",
        "Sergeli tumani",
        "\u0421\u0435\u0440\u0433\u0435\u043b\u0438 \u0442\u0443\u043c\u0430\u043d\u0438",
        "\u0421\u0435\u0440\u0433\u0435\u043b\u0438\u0439\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Shayxontohur": (
        "Shayxontohur",
        "Shayxontohur tumani",
        "\u0428\u0430\u0439\u0445\u0430\u043d\u0442\u0430\u0445\u0443\u0440\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Uchtepa": (
        "Uchtepa",
        "Uchtepa tumani",
        "\u0423\u0447\u0442\u0435\u043f\u0430",
        "\u0423\u0447\u0442\u0435\u043f\u0438\u043d\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Yakkasaroy": (
        "Yakkasaroy",
        "Yakkasaroy tumani",
        "\u042f\u043a\u043a\u0430\u0441\u0430\u0440\u0430\u0439\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Yangihayot": (
        "Yangihayot",
        "Yangihayot tumani",
        "\u042f\u043d\u0433\u0438\u0445\u0430\u0451\u0442 \u0442\u0443\u043c\u0430\u043d\u0438",
        "\u042f\u043d\u0433\u0438\u0445\u0430\u0435\u0442 9-\u043a\u0432\u0430\u0440\u0442\u0430\u043b\u0434\u0430",
    ),
    "Yashnobod": (
        "Yashnobod",
        "Yashnobod tumani",
        "\u042f\u0448\u043d\u043e\u0431\u043e\u0434 \u0442\u0443\u043c\u0430\u043d\u0438",
        "\u042f\u0448\u043d\u0430\u0431\u0430\u0434\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
    "Yunusobod": (
        "Yunusobod",
        "Yunusobod tumani",
        "\u042e\u043d\u0443\u0441\u0430\u0431\u0430\u0434\u0441\u043a\u0438\u0439 \u0440\u0430\u0439\u043e\u043d",
    ),
}


def parse_apartment_valuation_payload(payload: Mapping[str, Any]) -> ApartmentValuationInput:
    district = str(payload.get("district") or "").strip()
    if not district:
        raise ValuationInputError("Tuman tanlang")

    rooms = _int_field(payload, "rooms", "Xona soni")
    area_m2 = _float_field(payload, "area_m2", "Maydon")
    floor_number = _int_field(payload, "floor_number", "Qavat")
    total_floors = _int_field(payload, "total_floors", "Jami qavat")
    currency = str(payload.get("currency") or "UZS").strip().upper()

    if not 1 <= rooms <= 10:
        raise ValuationInputError("Xona soni 1 dan 10 gacha bo'lishi kerak")
    if not 12 <= area_m2 <= 500:
        raise ValuationInputError("Maydon 12 m2 dan 500 m2 gacha bo'lishi kerak")
    if not 1 <= floor_number <= 50:
        raise ValuationInputError("Qavat 1 dan 50 gacha bo'lishi kerak")
    if not 1 <= total_floors <= 50:
        raise ValuationInputError("Jami qavat 1 dan 50 gacha bo'lishi kerak")
    if floor_number > total_floors:
        raise ValuationInputError("Qavat jami qavatdan katta bo'lmasligi kerak")
    if currency not in {"UZS", "USD"}:
        raise ValuationInputError("Valyuta UZS yoki USD bo'lishi kerak")

    return ApartmentValuationInput(
        district=district,
        rooms=rooms,
        area_m2=area_m2,
        floor_number=floor_number,
        total_floors=total_floors,
        currency=currency,
    )


def district_aliases_for_model(district: str) -> list[str]:
    raw = district.strip()
    candidates = [raw]
    raw_key = _alias_key(raw)
    for canonical, aliases in DISTRICT_ALIASES.items():
        alias_keys = {_alias_key(item) for item in (canonical, *aliases)}
        if raw_key in alias_keys:
            candidates.extend([canonical, *aliases])
            break
    return _unique(candidates)


def build_apartment_valuation_response(
    request: ApartmentValuationInput,
    prediction: ApartmentPrediction,
    market_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    market_context = market_context or {}
    median_price_uzs = _optional_float(market_context.get("district_median_price_uzs"))
    median_unit_uzs = _optional_float(market_context.get("district_unit_price_uzs"))
    difference_percent = None
    if median_price_uzs and median_price_uzs > 0:
        difference_percent = ((prediction.price_uzs - median_price_uzs) / median_price_uzs) * 100
    response_warnings = list(prediction.warnings)
    if difference_percent is not None and (difference_percent <= -90 or difference_percent >= 300):
        response_warnings.append("Model natijasi tuman medianidan juda uzoq; model target scale'i tekshirilishi kerak")

    return {
        "prediction": {
            "price_uzs": round(prediction.price_uzs, 2),
            "price_usd": round(prediction.price_usd, 2),
            "price_display": _display_money_from_uzs(prediction.price_uzs, request.currency),
            "unit_price_uzs": round(prediction.unit_price_uzs, 2),
            "unit_price_display": _display_money_from_uzs(
                prediction.unit_price_uzs,
                request.currency,
                suffix=" / m2",
            ),
        },
        "market_context": {
            "district": market_context.get("district") or request.district,
            "listing_count": int(market_context.get("listing_count") or 0),
            "district_median_price_uzs": median_price_uzs,
            "district_median_price_display": _display_money_from_uzs(median_price_uzs, request.currency),
            "district_unit_price_uzs": median_unit_uzs,
            "district_unit_price_display": _display_money_from_uzs(median_unit_uzs, request.currency, suffix=" / m2"),
            "difference_percent": round(difference_percent, 2) if difference_percent is not None else None,
            "difference_display": _format_percent(difference_percent),
            "tone": _difference_tone(difference_percent),
        },
        "warnings": response_warnings,
    }


class ApartmentValuationService:
    def __init__(self, model_path: Path = MODEL_PATH, bundle: ApartmentModelBundle | None = None) -> None:
        self._model_path = model_path
        self._bundle = bundle

    def predict(self, request: ApartmentValuationInput) -> ApartmentPrediction:
        bundle = self._load_bundle()
        feature_values, warnings = self._feature_values(bundle.columns, request)

        try:
            import numpy as np
        except ImportError as exc:
            raise ValuationModelError("Model uchun numpy o'rnatilmagan") from exc

        try:
            raw_prediction = bundle.model.predict(np.asarray([feature_values], dtype=float))[0]
        except Exception as exc:
            raise ValuationModelError(f"Model prognoz qila olmadi: {exc}") from exc

        unit_price_score = _optional_float(raw_prediction)
        if unit_price_score is None or not math.isfinite(unit_price_score):
            raise ValuationModelError("Model yaroqli narx qaytarmadi")

        if self._target_transform(bundle) == "log1p":
            unit_price_score = math.expm1(unit_price_score)

        unit_price_uzs = unit_price_score * self._unit_price_scale(bundle)
        if not math.isfinite(unit_price_uzs) or unit_price_uzs <= 0:
            raise ValuationModelError("Model yaroqli narx qaytarmadi")

        price_uzs = unit_price_uzs * request.area_m2

        return ApartmentPrediction(
            price_uzs=price_uzs,
            price_usd=price_uzs / float(USD_TO_UZS_RATE),
            unit_price_uzs=unit_price_uzs,
            unit_price_usd=unit_price_uzs / float(USD_TO_UZS_RATE),
            warnings=tuple(warnings),
        )

    def _load_bundle(self) -> ApartmentModelBundle:
        if self._bundle is not None:
            return self._bundle
        if not self._model_path.exists():
            raise ValuationModelError("Kvartira baholash modeli topilmadi")

        try:
            with self._model_path.open("rb") as file:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")
                    payload = pickle.load(file)
        except Exception as exc:
            raise ValuationModelError(f"Kvartira baholash modeli yuklanmadi: {exc}") from exc

        if not isinstance(payload, dict) or "model" not in payload or "columns" not in payload:
            raise ValuationModelError("Model faylida `model` va `columns` kalitlari bo'lishi kerak")

        columns = tuple(str(column) for column in payload["columns"])
        if not columns:
            raise ValuationModelError("Model ustunlari bo'sh")

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else None

        self._bundle = ApartmentModelBundle(model=payload["model"], columns=columns, metadata=metadata)
        return self._bundle

    def _feature_values(
        self,
        columns: tuple[str, ...],
        request: ApartmentValuationInput,
    ) -> tuple[list[float], list[str]]:
        values = [0.0] * len(columns)
        column_index = {column: index for index, column in enumerate(columns)}
        numeric_values = {
            "room_count": float(request.rooms),
            "area_m2": float(request.area_m2),
            "floor_number": float(request.floor_number),
            "total_floors": float(request.total_floors),
            "floor_ratio": float(request.floor_number) / float(request.total_floors),
            "area_per_room": float(request.area_m2) / float(request.rooms),
            "log_area_m2": math.log1p(float(request.area_m2)),
            "rooms_area_interaction": float(request.rooms) * float(request.area_m2),
            "is_first_floor": 1.0 if request.floor_number == 1 else 0.0,
            "is_last_floor": 1.0 if request.floor_number == request.total_floors else 0.0,
            "is_low_floor": 1.0 if request.floor_number <= 2 else 0.0,
            "is_upper_floor": 1.0 if request.floor_number / request.total_floors >= 0.7 else 0.0,
            "is_small_area": 1.0 if request.area_m2 < 45 else 0.0,
            "is_large_area": 1.0 if request.area_m2 >= 100 else 0.0,
        }
        for column, value in numeric_values.items():
            if column in column_index:
                values[column_index[column]] = value
        room_column = f"room_{request.rooms}"
        if room_column in column_index:
            values[column_index[room_column]] = 1.0

        warnings: list[str] = []
        district_column = self._match_district_column(columns, request.district)
        if district_column:
            values[column_index[district_column]] = 1.0
            district_room_column = self._match_district_room_column(columns, request.district, request.rooms)
            if district_room_column:
                values[column_index[district_room_column]] = 1.0
        else:
            warnings.append("Bu tuman modelda alohida ustun sifatida topilmadi; umumiy baho qaytarildi")
        return values, warnings

    def _match_district_column(self, columns: tuple[str, ...], district: str) -> str | None:
        aliases = district_aliases_for_model(district)
        exact_columns = set(columns)
        for alias in aliases:
            candidate = f"district_{alias}"
            if candidate in exact_columns:
                return candidate

        normalized_to_column = {
            _alias_key(column.removeprefix("district_")): column
            for column in columns
            if column.startswith("district_")
        }
        for alias in aliases:
            column = normalized_to_column.get(_alias_key(alias))
            if column:
                return column
        return None

    def _match_district_room_column(
        self,
        columns: tuple[str, ...],
        district: str,
        rooms: int,
    ) -> str | None:
        aliases = district_aliases_for_model(district)
        exact_columns = set(columns)
        for alias in aliases:
            candidate = f"district_room_{alias}_{rooms}"
            if candidate in exact_columns:
                return candidate

        normalized_to_column = {}
        suffix = f"_{rooms}"
        for column in columns:
            if not column.startswith("district_room_") or not column.endswith(suffix):
                continue
            district_part = column.removeprefix("district_room_")[: -len(suffix)]
            normalized_to_column[_alias_key(district_part)] = column
        for alias in aliases:
            column = normalized_to_column.get(_alias_key(alias))
            if column:
                return column
        return None

    def _unit_price_scale(self, bundle: ApartmentModelBundle) -> float:
        metadata = bundle.metadata or {}
        if "unit_price_scale" in metadata:
            scale = _optional_float(metadata.get("unit_price_scale"))
            if scale and scale > 0:
                return scale
        return MODEL_UNIT_PRICE_SCALE

    def _target_transform(self, bundle: ApartmentModelBundle) -> str:
        metadata = bundle.metadata or {}
        return str(metadata.get("target_transform") or "none").strip().lower()


def _int_field(payload: Mapping[str, Any], key: str, label: str) -> int:
    value = payload.get(key)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValuationInputError(f"{label} butun son bo'lishi kerak") from None


def _float_field(payload: Mapping[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise ValuationInputError(f"{label} raqam bo'lishi kerak") from None
    return float(number)


def _alias_key(value: str) -> str:
    return value.strip().lower().replace("'", "").replace("\u2019", "").replace("-", " ")


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item:
            continue
        key = _alias_key(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_money_from_uzs(value: Any, currency: str, suffix: str = "") -> str:
    amount = _optional_float(value)
    if amount is None:
        return "-"
    if currency == "USD":
        return f"${amount / float(USD_TO_UZS_RATE):,.0f}{suffix}"
    return f"{_format_uzs_compact(amount)}{suffix}"


def _format_uzs_compact(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000_000:
        return f"{sign}{amount / 1_000_000_000:.1f} mlrd so'm"
    if amount >= 1_000_000:
        return f"{sign}{amount / 1_000_000:.1f} mln so'm"
    if amount >= 1_000:
        return f"{sign}{amount / 1_000:.0f} ming so'm"
    return f"{sign}{amount:,.0f} so'm"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _difference_tone(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value <= -5:
        return "success"
    if value >= 5:
        return "warning"
    return "neutral"
