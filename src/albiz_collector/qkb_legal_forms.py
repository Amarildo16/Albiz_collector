from __future__ import annotations

import re
import unicodedata

SHPK_CANONICAL_LEGAL_FORM = "SHPK"

_SHPK_LONG_FORM = "SHOQERI ME PERGJEGJESI TE KUFIZUAR"


def canonicalize_qkb_legal_form(value: str | None) -> str | None:
    """Return a stable canonical legal-form value without mutating the raw source value."""
    normalized = normalize_qkb_legal_form_text(value)
    if normalized is None:
        return None

    compact = re.sub(r"[^A-Z0-9]+", "", normalized)
    if compact == SHPK_CANONICAL_LEGAL_FORM or normalized == _SHPK_LONG_FORM:
        return SHPK_CANONICAL_LEGAL_FORM

    return normalized


def normalize_qkb_legal_form_text(value: str | None) -> str | None:
    if value is None:
        return None

    accentless = _strip_accents(value)
    upper = accentless.upper()
    normalized = re.sub(r"[^A-Z0-9]+", " ", upper).strip()
    return normalized or None


def is_qkb_shpk_legal_form(value: str | None) -> bool:
    return canonicalize_qkb_legal_form(value) == SHPK_CANONICAL_LEGAL_FORM


def _strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(character for character in decomposed if not unicodedata.combining(character))
