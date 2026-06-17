from __future__ import annotations

import re
import unicodedata

SHPK_CANONICAL_LEGAL_FORM = "SHPK"
SHA_CANONICAL_LEGAL_FORM = "SHA"
QKB_SHPK_LEGAL_FORM_VALUE = "Shoqeri me pergjegjesi te kufizuar"
QKB_SHA_LEGAL_FORM_VALUE = "Shoqeri aksionare"

_SHPK_LONG_FORM = "SHOQERI ME PERGJEGJESI TE KUFIZUAR"
_SHA_LONG_FORM = "SHOQERI AKSIONARE"


def canonicalize_qkb_legal_form(value: str | None) -> str | None:
    """Return a stable canonical legal-form value without mutating the raw source value."""
    normalized = normalize_qkb_legal_form_text(value)
    if normalized is None:
        return None

    compact = re.sub(r"[^A-Z0-9]+", "", normalized)
    if compact == SHPK_CANONICAL_LEGAL_FORM or normalized == _SHPK_LONG_FORM:
        return SHPK_CANONICAL_LEGAL_FORM
    if compact == SHA_CANONICAL_LEGAL_FORM or normalized == _SHA_LONG_FORM:
        return SHA_CANONICAL_LEGAL_FORM

    return normalized


def resolve_qkb_legal_form_filter(value: str | None) -> str | None:
    if value is None:
        return None

    raw_value = value.strip()
    if not raw_value:
        return None

    canonical = canonicalize_qkb_legal_form(raw_value)
    if canonical == SHPK_CANONICAL_LEGAL_FORM:
        return QKB_SHPK_LEGAL_FORM_VALUE
    if canonical == SHA_CANONICAL_LEGAL_FORM:
        return QKB_SHA_LEGAL_FORM_VALUE

    return raw_value


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
