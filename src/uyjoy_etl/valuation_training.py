from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from uyjoy_etl.db import Database
from uyjoy_etl.valuation import MODEL_PATH


@dataclass(frozen=True)
class ValuationTrainingSummary:
    model_path: str
    training_window_days: int
    rows_loaded: int
    rows_used: int
    train_rows: int
    test_rows: int
    district_count: int
    min_model_date: str
    max_model_date: str
    target_transform: str
    target_median_uzs_m2: float
    mae_uzs_m2: float
    mape_percent: float
    baseline_mape_percent: float
    r2_score: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def train_apartment_valuation_model(
    database: Database,
    model_path: Path = MODEL_PATH,
    min_rows: int = 500,
    training_window_days: int = 30,
) -> ValuationTrainingSummary:
    rows = _load_training_rows(database, training_window_days)
    prepared_rows = _prepare_rows(rows)
    if len(prepared_rows) < min_rows:
        raise RuntimeError(f"Model train uchun data kam: {len(prepared_rows)} rows, minimum {min_rows}")

    districts = tuple(sorted({str(row["district"]) for row in prepared_rows}))
    room_counts = tuple(sorted({int(row["room_count"]) for row in prepared_rows}))
    columns = (
        "room_count",
        "area_m2",
        "floor_number",
        "total_floors",
        "floor_ratio",
        "area_per_room",
        "log_area_m2",
        "rooms_area_interaction",
        "is_first_floor",
        "is_last_floor",
        "is_low_floor",
        "is_upper_floor",
        "is_small_area",
        "is_large_area",
        *(f"room_{room_count}" for room_count in room_counts),
        *(f"district_{district}" for district in districts),
        *(f"district_room_{district}_{room_count}" for district in districts for room_count in room_counts),
    )
    x = np.asarray([_feature_vector(row, columns) for row in prepared_rows], dtype=float)
    y_actual = np.asarray([float(row["unit_price_uzs"]) for row in prepared_rows], dtype=float)
    y_train_target = np.log1p(y_actual)

    x_train, x_test, y_train, _y_test_target, _y_train_actual, y_test_actual = train_test_split(
        x,
        y_train_target,
        y_actual,
        test_size=0.2,
        random_state=42,
    )

    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=760,
        learning_rate=0.025,
        max_depth=4,
        min_child_weight=6,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=2.0,
        reg_alpha=0.08,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    predictions = np.clip(np.expm1(model.predict(x_test)), 1, None)
    baseline_prediction = np.full_like(y_test_actual, np.median(y_actual), dtype=float)
    min_model_date = min(row["model_date"] for row in prepared_rows)
    max_model_date = max(row["model_date"] for row in prepared_rows)

    summary = ValuationTrainingSummary(
        model_path=str(model_path),
        training_window_days=training_window_days,
        rows_loaded=len(rows),
        rows_used=len(prepared_rows),
        train_rows=len(x_train),
        test_rows=len(x_test),
        district_count=len(districts),
        min_model_date=str(min_model_date),
        max_model_date=str(max_model_date),
        target_transform="log1p",
        target_median_uzs_m2=float(np.median(y_actual)),
        mae_uzs_m2=float(mean_absolute_error(y_test_actual, predictions)),
        mape_percent=float(np.mean(np.abs((y_test_actual - predictions) / y_test_actual)) * 100),
        baseline_mape_percent=float(np.mean(np.abs((y_test_actual - baseline_prediction) / y_test_actual)) * 100),
        r2_score=float(r2_score(y_test_actual, predictions)),
    )

    payload: dict[str, Any] = {
        "model": model,
        "columns": columns,
        "metadata": {
            "model_type": "xgboost.XGBRegressor",
            "source": "bi_tashkent_sale_market",
            "target": "price_m2_uzs",
            "target_transform": "log1p",
            "unit_price_scale": 1.0,
            "training_window_days": training_window_days,
            "trained_at": datetime.now(UTC).isoformat(),
            "training_summary": asdict(summary),
            "districts": districts,
            "room_counts": room_counts,
            "features": columns,
        },
    }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = model_path.with_suffix(".pkl.tmp")
    with temp_path.open("wb") as file:
        pickle.dump(payload, file)
    temp_path.replace(model_path)

    return summary


def _load_training_rows(database: Database, training_window_days: int) -> list[dict[str, Any]]:
    with database.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                """
                with base as (
                    select
                        district_name as district,
                        room_count,
                        valid_area_m2::float as area_m2,
                        floor_number,
                        total_floors,
                        price_m2_uzs::float as unit_price_uzs,
                        coalesce(posted_at, first_seen_at, updated_at)::date as model_date
                    from bi_tashkent_sale_market
                    where deal_type = 'sale'
                      and property_segment = 'Kvartira'
                      and district_name is not null
                      and district_name <> 'Noma''lum'
                      and room_count between 1 and 10
                      and valid_area_m2 between 12 and 500
                      and valid_price_uzs between 100000000 and 20000000000
                      and price_m2_uzs between 4000000 and 70000000
                      and coalesce(posted_at, first_seen_at, updated_at) >= now() - (%(training_window_days)s * interval '1 day')
                      and (quality_status is null or quality_status = 'ok')
                )
                select *
                from base
                where model_date is not null
                """,
                {"training_window_days": training_window_days},
            ).fetchall()
        ]


def _prepare_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    target_values = np.asarray([float(row["unit_price_uzs"]) for row in rows], dtype=float)
    q1, q3 = np.percentile(target_values, [25, 75])
    iqr = max(float(q3 - q1), 1.0)
    lower = max(float(q1 - 1.5 * iqr), 4_000_000.0)
    upper = min(float(q3 + 1.5 * iqr), 70_000_000.0)

    floor_values = [
        int(row["floor_number"])
        for row in rows
        if _valid_floor_pair(row.get("floor_number"), row.get("total_floors"))
    ]
    total_floor_values = [
        int(row["total_floors"])
        for row in rows
        if _valid_floor_pair(row.get("floor_number"), row.get("total_floors"))
    ]
    fallback_floor = int(np.median(floor_values)) if floor_values else 3
    fallback_total_floors = int(np.median(total_floor_values)) if total_floor_values else 7

    prepared: list[dict[str, Any]] = []
    for row in rows:
        unit_price = float(row["unit_price_uzs"])
        if unit_price < lower or unit_price > upper:
            continue

        floor_number = row.get("floor_number")
        total_floors = row.get("total_floors")
        if not _valid_floor_pair(floor_number, total_floors):
            floor_number = fallback_floor
            total_floors = max(fallback_total_floors, floor_number)

        prepared.append(
            {
                "district": str(row["district"]).strip(),
                "room_count": int(row["room_count"]),
                "area_m2": float(row["area_m2"]),
                "floor_number": int(floor_number),
                "total_floors": int(total_floors),
                "unit_price_uzs": unit_price,
                "model_date": row["model_date"],
            }
        )
    return prepared


def _valid_floor_pair(floor_number: Any, total_floors: Any) -> bool:
    try:
        floor = int(floor_number)
        total = int(total_floors)
    except (TypeError, ValueError):
        return False
    return 1 <= floor <= total <= 50


def _feature_vector(row: dict[str, Any], columns: tuple[str, ...]) -> list[float]:
    district = str(row["district"])
    room_count = int(row["room_count"])
    area_m2 = float(row["area_m2"])
    floor_number = int(row["floor_number"])
    total_floors = int(row["total_floors"])
    values = {
        "room_count": float(room_count),
        "area_m2": area_m2,
        "floor_number": float(floor_number),
        "total_floors": float(total_floors),
        "floor_ratio": float(floor_number) / float(total_floors),
        "area_per_room": area_m2 / float(room_count),
        "log_area_m2": float(np.log1p(area_m2)),
        "rooms_area_interaction": float(room_count) * area_m2,
        "is_first_floor": 1.0 if floor_number == 1 else 0.0,
        "is_last_floor": 1.0 if floor_number == total_floors else 0.0,
        "is_low_floor": 1.0 if floor_number <= 2 else 0.0,
        "is_upper_floor": 1.0 if floor_number / total_floors >= 0.7 else 0.0,
        "is_small_area": 1.0 if area_m2 < 45 else 0.0,
        "is_large_area": 1.0 if area_m2 >= 100 else 0.0,
        f"room_{room_count}": 1.0,
        f"district_{district}": 1.0,
        f"district_room_{district}_{room_count}": 1.0,
    }
    return [values.get(column, 0.0) for column in columns]
