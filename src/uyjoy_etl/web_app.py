from __future__ import annotations

import csv
import io
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from uyjoy_etl.config import load_config
from uyjoy_etl.db import Database
from uyjoy_etl.web_repository import (
    ListingFilters,
    ListingRepository,
    MarketInsightFilters,
    is_missing_table_error,
    parse_decimal,
)

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"

config = load_config()
database = Database(config.database)
repository = ListingRepository(database)

app = FastAPI(title="UY-JOY Data Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
security = HTTPBasic(auto_error=False)


def _require_dashboard_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    """Productionda dashboardni basic auth bilan himoya qiladi."""

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
def dashboard(
    request: Request,
    _: None = Depends(_require_dashboard_auth),
    q: str = "",
    source: str = "",
    category: str = "",
    deal_type: str = "",
    city: str = "",
    district: str = "",
    rooms: str = "",
    price_min: str = "",
    price_max: str = "",
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    filters = ListingFilters(
        q=q.strip(),
        source=source.strip(),
        category=category.strip(),
        deal_type=deal_type.strip(),
        city=city.strip(),
        district=district.strip(),
        rooms=rooms.strip(),
        price_min=parse_decimal(price_min),
        price_max=parse_decimal(price_max),
        page=page,
    )

    try:
        result = repository.search(filters)
        facets = repository.get_facets()
        stats = repository.get_stats()
        admin_overview = repository.get_admin_overview()
        error_message = None
    except Exception as exc:
        result = None
        facets = {"deal_types": [], "sources": [], "categories": [], "cities": [], "districts": [], "rooms": []}
        stats = {}
        admin_overview = _empty_admin_overview()
        error_message = _friendly_error(exc)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "filters": {
                "q": q,
                "source": source,
                "category": category,
                "deal_type": deal_type,
                "city": city,
                "district": district,
                "rooms": rooms,
                "price_min": price_min,
                "price_max": price_max,
            },
            "result": result,
            "facets": facets,
            "stats": stats,
            "admin": admin_overview,
            "error_message": error_message,
            "prev_url": _page_url(request, page - 1) if result and page > 1 else None,
            "next_url": _page_url(request, page + 1)
            if result and page < result.total_pages
            else None,
        },
    )


@app.get("/analytics", response_class=HTMLResponse)
def analytics(
    request: Request,
    _: None = Depends(_require_dashboard_auth),
    deal_type: str = "",
    property_type: str = "",
    city: str = "",
    district: str = "",
    rooms: str = "",
    currency_code: str = "USD",
    metric: str = "auto",
    days: int = Query(default=60, ge=14, le=180),
) -> HTMLResponse:
    filters = MarketInsightFilters(
        deal_type=deal_type.strip(),
        property_type=property_type.strip(),
        city=city.strip(),
        district=district.strip(),
        rooms=rooms.strip(),
        currency_code=currency_code.strip().upper() or "USD",
        metric=metric.strip(),
        days=days,
    )
    try:
        insights = repository.get_market_insights(filters)
        error_message = None
    except Exception as exc:
        insights = _empty_market_insights()
        error_message = _friendly_error(exc)

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "insights": insights,
            "filters": filters,
            "error_message": error_message,
        },
    )


@app.get("/market-dashboard", response_class=HTMLResponse)
def market_dashboard(
    request: Request,
    _: None = Depends(_require_dashboard_auth),
    deal_type: str = "",
    property_type: str = "",
    city: str = "",
    district: str = "",
    rooms: str = "",
    currency_code: str = "USD",
    metric: str = "auto",
    days: int = Query(default=60, ge=14, le=180),
) -> HTMLResponse:
    filters = MarketInsightFilters(
        deal_type=deal_type.strip(),
        property_type=property_type.strip(),
        city=city.strip(),
        district=district.strip(),
        rooms=rooms.strip(),
        currency_code=currency_code.strip().upper() or "USD",
        metric=metric.strip(),
        days=days,
    )
    try:
        insights = repository.get_market_insights(filters)
        error_message = None
    except Exception as exc:
        insights = _empty_market_insights()
        error_message = _friendly_error(exc)

    return templates.TemplateResponse(
        "market_dashboard.html",
        {
            "request": request,
            "insights": insights,
            "filters": filters,
            "error_message": error_message,
        },
    )


@app.get("/listing/{listing_id}", response_class=HTMLResponse)
def listing_detail(
    request: Request,
    listing_id: int,
    _: None = Depends(_require_dashboard_auth),
) -> HTMLResponse:
    try:
        listing = repository.get_listing(listing_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_friendly_error(exc)) from exc

    if not listing:
        raise HTTPException(status_code=404, detail="E'lon topilmadi")

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "listing": listing,
        },
    )


@app.get("/health")
def health() -> dict[str, object]:
    ping = database.ping()
    stats = repository.get_stats()
    return {
        "status": "ok",
        "database": ping["database"],
        "database_host": config.database.host,
        "database_user": ping["user"],
        "total_listings": stats.get("total_listings", 0),
    }


@app.get("/api/powerbi/listings.csv")
def powerbi_listings_csv(_: None = Depends(_require_dashboard_auth)) -> StreamingResponse:
    """Power BI uchun CSV export: Postgres SSL muammosini chetlab o'tadigan endpoint."""

    rows = repository.iter_powerbi_rows()
    headers = [
        "id",
        "source",
        "source_label",
        "source_listing_id",
        "listing_code",
        "source_url",
        "title",
        "category_label",
        "source_category",
        "deal_type",
        "price_value",
        "currency_code",
        "is_price_negotiable",
        "city_name",
        "district_name",
        "region_name",
        "room_count",
        "total_area",
        "land_area",
        "floor",
        "total_floors",
        "seller_type",
        "is_business",
        "created_time",
        "last_refresh_time",
        "last_seen_at",
    ]

    def generate_csv() -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return buffer.getvalue()

    return StreamingResponse(
        iter([generate_csv()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="uyjoy_powerbi_listings.csv"'},
    )


def _page_url(request: Request, page: int) -> str:
    params = dict(request.query_params)
    params["page"] = str(page)
    return f"{request.url.path}?{urlencode(params)}"


def _friendly_error(exc: Exception) -> str:
    if is_missing_table_error(exc):
        return "Database schema hali yaratilmagan. Avval migration ishlating."
    return f"Databasega ulanish yoki query bajarishda xato: {exc}"


def _empty_admin_overview() -> dict[str, object]:
    return {
        "olx": {},
        "telegram": {},
        "fetch": {},
        "daily_flow": [],
        "sources": [],
        "cities": [],
        "quality_reasons": [],
        "recent_runs": [],
    }


def _empty_market_insights() -> dict[str, object]:
    return {
        "filters": MarketInsightFilters(),
        "facets": {
            "deal_types": [],
            "property_types": [],
            "currencies": [],
            "cities": [],
            "districts": [],
            "rooms": [],
            "sources": [],
        },
        "summary": {},
        "source_mix": [],
        "deal_mix": [],
        "property_mix": [],
        "top_cities": [],
        "top_districts": [],
        "room_mix": [],
        "area_bands": [],
        "usd_price_bands": [],
        "price_summary": [],
        "daily_supply": [],
        "price_trend": {
            "metric_label": "",
            "currency_code": "",
            "points": [],
            "polyline": "",
            "path": "",
            "moving_average_polyline": "",
            "moving_average_path": "",
            "latest_display": "-",
            "average_display": "-",
            "moving_average_latest_display": "-",
            "average_y": None,
            "y_min_display": "-",
            "y_max_display": "-",
            "y_min_short": "-",
            "y_max_short": "-",
            "anomaly_total": 0,
            "width": 760,
            "height": 280,
        },
        "segment_trends": [],
        "map": {"points": [], "center_lat": 41.2995, "center_lon": 69.2401, "zoom": 11},
        "sale_apartment_m2_trend": {
            "metric_label": "",
            "currency_code": "",
            "points": [],
            "polyline": "",
            "path": "",
            "moving_average_polyline": "",
            "moving_average_path": "",
            "latest_display": "-",
            "average_display": "-",
            "moving_average_latest_display": "-",
            "average_y": None,
            "y_min_display": "-",
            "y_max_display": "-",
            "y_min_short": "-",
            "y_max_short": "-",
            "anomaly_total": 0,
            "width": 760,
            "height": 280,
        },
    }
