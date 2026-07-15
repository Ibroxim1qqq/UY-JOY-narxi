from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uyjoy_etl.db import Database


PHONE_COLUMNS = ("contact_phone", "phone", "phone_number", "mobile", "nomer")
NAME_COLUMNS = ("contact_name", "name", "seller_name", "ism")
OLX_ID_COLUMNS = ("olx_id", "id", "ad_id", "listing_id")
URL_COLUMNS = ("listing_url", "url", "olx_url")


@dataclass(frozen=True)
class ContactImportSummary:
    """Contact import natijasini qisqa hisoblab beradi."""

    rows_seen: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0


def import_contacts_csv(database: Database, csv_path: Path, source: str) -> ContactImportSummary:
    """Ruxsatli CSV/export ichidagi contactlarni e'lonlarga ulaydi."""

    rows_seen = 0
    rows_updated = 0
    rows_skipped = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows_seen += 1
            record = contact_record_from_row(row, source=source)
            if not record:
                rows_skipped += 1
                continue
            if database.update_listing_contact(record):
                rows_updated += 1
            else:
                rows_skipped += 1

    return ContactImportSummary(
        rows_seen=rows_seen,
        rows_updated=rows_updated,
        rows_skipped=rows_skipped,
    )


def contact_record_from_row(row: dict[str, str | None], source: str) -> dict[str, Any] | None:
    """CSV rowni DB update uchun normal dictga aylantiradi."""

    phone = _first_value(row, PHONE_COLUMNS)
    if not phone:
        return None

    olx_id_text = _first_value(row, OLX_ID_COLUMNS)
    listing_url = _first_value(row, URL_COLUMNS)
    if not olx_id_text and not listing_url:
        return None

    olx_id = int(olx_id_text) if olx_id_text and olx_id_text.isdigit() else None
    return {
        "olx_id": olx_id,
        "listing_url": listing_url,
        "contact_phone": phone,
        "contact_name": _first_value(row, NAME_COLUMNS),
        "contact_source": source,
        "contact_raw": {key: value for key, value in row.items() if value not in (None, "")},
    }


def _first_value(row: dict[str, str | None], columns: tuple[str, ...]) -> str | None:
    for column in columns:
        value = row.get(column)
        if value:
            clean_value = value.strip()
            if clean_value:
                return clean_value
    return None
