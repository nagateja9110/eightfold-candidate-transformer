"""Validates a projected output dict against the OutputConfig that produced it.

Runs as a final safety net before output is returned/written: confirms
required fields are present, types match, and every populated value can be
traced back to a provenance entry on the source CanonicalProfile (so nothing
in the output was invented during projection).
"""

from __future__ import annotations

import re

from models.schemas import CanonicalProfile, OutputConfig

_BASE_FIELD_RE = re.compile(r"^[a-zA-Z0-9_]+")

# Structural identifiers that may be synthesized (no source actually provided them)
# rather than extracted, so they're exempt from the provenance cross-check.
_PROVENANCE_EXEMPT_FIELDS = {"candidate_id"}

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "string[]": lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
    "number[]": lambda v: isinstance(v, list) and all(isinstance(i, (int, float)) and not isinstance(i, bool) for i in v),
    "object": lambda v: isinstance(v, (dict, list)),
}


def _base_field_name(path: str) -> str:
    """Extracts the leading canonical field name from a path like 'emails[0]' or 'links.github'."""
    match = _BASE_FIELD_RE.match(path)
    return match.group(0) if match else path


def _is_empty(value: object) -> bool:
    """True for None, [], {}, or an object/dict whose every value is itself empty.

    An empty container means "no data available" (e.g. education=[], links with
    every sub-field null) — not a populated value that needs provenance backing.
    """
    if value is None:
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    if isinstance(value, dict):
        return all(_is_empty(v) for v in value.values())
    return False


def validate(profile: CanonicalProfile, config: OutputConfig, result: dict) -> tuple[bool, list[str]]:
    """Validates a projected result dict. Returns (is_valid, errors)."""
    errors: list[str] = []
    provenance_fields = {p.field for p in profile.provenance}

    for field in config.fields:
        present = field.path in result
        value = result.get(field.path)

        if field.required and (not present or _is_empty(value)):
            errors.append(f"Required field '{field.path}' is missing")
            continue

        if not present or _is_empty(value):
            continue

        check = _TYPE_CHECKS.get(field.type)
        if check is not None and not check(value):
            errors.append(f"Field '{field.path}' does not match type '{field.type}' (got {value!r})")

        base_field = _base_field_name(field.from_ or field.path)
        if base_field not in _PROVENANCE_EXEMPT_FIELDS and base_field not in provenance_fields:
            errors.append(
                f"Field '{field.path}' has a value but no provenance entry for '{base_field}' "
                "— possible invented data"
            )

    return len(errors) == 0, errors
