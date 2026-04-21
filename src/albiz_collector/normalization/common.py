from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Any


def compact_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def parse_date_value(value: Any) -> date | None:
    cleaned = compact_text(value)
    if cleaned is None:
        return None

    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_decimal_value(value: Any) -> Decimal | None:
    cleaned = compact_text(value)
    if cleaned is None:
        return None

    normalized = cleaned.replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def parse_yes_no_flag(value: Any) -> bool | None:
    cleaned = compact_text(value)
    if cleaned is None:
        return None

    normalized = cleaned.lower()
    if normalized in {"po", "yes", "true"}:
        return True
    if normalized in {"jo", "no", "false"}:
        return False
    return None


def coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return parse_yes_no_flag(value)