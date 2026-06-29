"""Pure normalization functions: raw strings in, canonical values or None out.

None of these functions raise on bad input — unparseable values normalize to
None rather than being invented or left as garbage.
"""

from __future__ import annotations

import re
from datetime import datetime

import phonenumbers
from dateutil import parser as dateutil_parser

from models.schemas import Location

DEFAULT_PHONE_REGION = "US"

# Maps country names/abbreviations (case-insensitive) to ISO-3166 alpha-2 codes.
COUNTRY_MAP: dict[str, str] = {
    "usa": "US",
    "us": "US",
    "united states": "US",
    "united states of america": "US",
    "india": "IN",
    "in": "IN",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "canada": "CA",
    "germany": "DE",
    "france": "FR",
    "australia": "AU",
    "china": "CN",
    "japan": "JP",
    "singapore": "SG",
    "brazil": "BR",
    "mexico": "MX",
}

# Maps raw skill variants (lowercased) to a single canonical skill name.
SKILL_MAP: dict[str, str] = {
    "ml": "machine learning",
    "machine learning": "machine learning",
    "js": "javascript",
    "javascript": "javascript",
    "react.js": "react",
    "reactjs": "react",
    "react": "react",
    "node.js": "node.js",
    "nodejs": "node.js",
    "node": "node.js",
    "ts": "typescript",
    "typescript": "typescript",
    "python": "python",
    "py": "python",
    "go": "go",
    "golang": "go",
}


def normalize_phone(raw: str | None, default_region: str = DEFAULT_PHONE_REGION) -> str | None:
    """Normalize a raw phone string to E.164 format, or None if unparseable."""
    if not raw or not raw.strip():
        return None

    try:
        parsed = phonenumbers.parse(raw.strip(), default_region)
    except phonenumbers.NumberParseException:
        return None

    if not phonenumbers.is_valid_number(parsed):
        return None

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_name(raw: str | None) -> str | None:
    """Collapse whitespace and title-case a name; preserves initials like 'J.'."""
    if not raw or not raw.strip():
        return None

    cleaned = " ".join(raw.split())
    return cleaned.title()


def normalize_location(raw: str | None) -> Location:
    """Parse a free-text location string into city / region / country (ISO-3166 alpha-2)."""
    if not raw or not raw.strip():
        return Location()

    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return Location()

    if len(parts) == 1:
        return Location(city=parts[0])

    if len(parts) == 2:
        city, second = parts
        country_code = COUNTRY_MAP.get(second.lower())
        if country_code:
            return Location(city=city, country=country_code)
        return Location(city=city, region=second)

    city, region = parts[0], parts[1]
    country_code = COUNTRY_MAP.get(parts[-1].lower())
    return Location(city=city, region=region, country=country_code)


def normalize_skill(raw: str | None) -> str | None:
    """Map a raw skill string to its canonical lowercase name."""
    if not raw or not raw.strip():
        return None

    key = raw.strip().lower()
    return SKILL_MAP.get(key, key)


_YEAR_ONLY_RE = re.compile(r"^\d{4}$")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def normalize_date(raw: str | None) -> str | None:
    """Normalize a free-text date to YYYY-MM, or None if unparseable.

    A year-only input (e.g. "2022") has no month information; it is
    normalized to "YYYY-01" rather than left as a bare year, since the
    canonical schema requires YYYY-MM granularity.
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    if _YEAR_MONTH_RE.match(raw):
        return raw

    if _YEAR_ONLY_RE.match(raw):
        return f"{raw}-01"

    try:
        parsed = dateutil_parser.parse(raw, default=datetime(2000, 1, 1))
    except (ValueError, OverflowError, TypeError):
        return None

    return parsed.strftime("%Y-%m")


def normalize_email(raw: str | None) -> str | None:
    """Lowercase and strip an email address, or None if empty."""
    if not raw or not raw.strip():
        return None

    return raw.strip().lower()
