from __future__ import annotations

import os
import pickle
import secrets
import warnings
from datetime import datetime

from fastapi import Body, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from uyjoy_etl.config import load_config
from uyjoy_etl.db import Database
from uyjoy_etl.valuation import (
    MODEL_PATH,
    ApartmentValuationService,
    ValuationInputError,
    ValuationModelError,
    build_apartment_valuation_response,
    parse_apartment_valuation_payload,
)
from uyjoy_etl.web_repository import ListingRepository


PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(PACKAGE_DIR, "templates")
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")

config = load_config()
database = Database(config.database)
repository = ListingRepository(database)
apartment_valuation_service = ApartmentValuationService()

app = FastAPI(title="UY-JOY ML Valuation")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
security = HTTPBasic(auto_error=False)


def _require_dashboard_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    username = os.getenv("DASHBOARD_USERNAME", "").strip()
    password = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not username and not password:
        return

    if not credentials or not _credentials_match(credentials, username, password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Dashboard login yoki parol noto'g'ri",
            headers={"WWW-Authenticate": "Basic"},
        )


def _credentials_match(
    credentials: HTTPBasicCredentials,
    expected_username: str,
    expected_password: str,
) -> bool:
    return secrets.compare_digest(credentials.username, expected_username) and secrets.compare_digest(
        credentials.password,
        expected_password,
    )


@app.get("/", response_class=HTMLResponse)
@app.get("/new-dashboard", response_class=HTMLResponse)
def valuation_home(
    request: Request,
    _: None = Depends(_require_dashboard_auth),
) -> HTMLResponse:
    return templates.TemplateResponse("new_dashboard.html", {"request": request})


@app.post("/api/apartment-valuation")
def apartment_valuation_api(
    payload: dict[str, object] = Body(...),
    _: None = Depends(_require_dashboard_auth),
) -> dict[str, object]:
    try:
        valuation_input = parse_apartment_valuation_payload(payload)
    except ValuationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        prediction = apartment_valuation_service.predict(valuation_input)
        market_context = repository.get_apartment_valuation_market_context(
            valuation_input.district,
            valuation_input.currency,
        )
        return build_apartment_valuation_response(valuation_input, prediction, market_context)
    except ValuationModelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database yoki model xatosi: {exc}") from exc


@app.get("/health")
def health() -> dict[str, object]:
    try:
        ping = database.ping()
        stats = repository.get_stats()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database health xatosi: {exc}") from exc

    return {
        "status": "ok",
        "database": ping["database"],
        "database_host": config.database.host,
        "database_user": ping["user"],
        "total_listings": stats["total_listings"],
        "sale_apartment_listings": stats["sale_apartment_listings"],
        "model": _model_status(),
    }


def _model_status() -> dict[str, object]:
    if not MODEL_PATH.exists():
        return {"available": False, "path": str(MODEL_PATH)}

    status_payload: dict[str, object] = {
        "available": True,
        "path": str(MODEL_PATH),
        "size_bytes": MODEL_PATH.stat().st_size,
        "modified_at": datetime.fromtimestamp(MODEL_PATH.stat().st_mtime).isoformat(timespec="seconds"),
    }
    try:
        with MODEL_PATH.open("rb") as file:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")
                payload = pickle.load(file)
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        training_summary = metadata.get("training_summary", {}) if isinstance(metadata, dict) else {}
        status_payload.update(
            {
                "trained_at": metadata.get("trained_at"),
                "training_window_days": metadata.get("training_window_days"),
                "rows_used": training_summary.get("rows_used"),
                "mape_percent": training_summary.get("mape_percent"),
            }
        )
    except Exception as exc:
        status_payload.update({"available": False, "error": str(exc)})
    return status_payload
