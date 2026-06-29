"""Projection layer: reshapes a CanonicalProfile into a custom output dict per OutputConfig.

Keeps the internal canonical record completely separate from any one output
shape — the same CanonicalProfile can be projected through any number of
configs without re-running extraction/merge.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from models.schemas import CanonicalProfile, ConfigField, OutputConfig
from pipeline.normalizers import normalize_phone, normalize_skill

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"^([a-zA-Z0-9_]+)(\[(\d*)\])?$")

_NORMALIZERS = {
    "E164": normalize_phone,
    "canonical": normalize_skill,
}


class ProjectionError(Exception):
    """Raised when a required field is missing, or on_missing='error' and a field is missing."""


def _parse_token(token: str) -> tuple[str, str | int | None]:
    match = _TOKEN_RE.match(token)
    if not match:
        raise ProjectionError(f"Invalid path token: {token!r}")
    name, bracket, idx = match.groups()
    if bracket is None:
        return name, None
    if idx == "":
        return name, "map"
    return name, int(idx)


def _resolve_tokens(current: Any, tokens: list[str]) -> Any:
    if not tokens or current is None:
        return current

    name, accessor = _parse_token(tokens[0])
    rest = tokens[1:]

    if not isinstance(current, dict):
        return None
    value = current.get(name)

    if accessor is None:
        return _resolve_tokens(value, rest)

    if accessor == "map":
        if not isinstance(value, list):
            return None
        return [_resolve_tokens(item, rest) for item in value]

    if not isinstance(value, list) or not (0 <= accessor < len(value)):
        return None
    return _resolve_tokens(value[accessor], rest)


def resolve_path(data: dict, path: str) -> Any:
    """Resolve a dotted path (with optional [N] index or [] map) against a dict tree."""
    return _resolve_tokens(data, path.split("."))


def _apply_normalize(value: Any, normalize: str | None) -> Any:
    if normalize is None or value is None:
        return value
    func = _NORMALIZERS.get(normalize)
    if func is None:
        return value
    if isinstance(value, list):
        return [func(v) for v in value]
    return func(value)


def _coerce_type(value: Any, field_type: str, path: str) -> Any:
    """Coerce value to field_type where safe (e.g. numeric string -> number); raises
    ProjectionError when the value genuinely doesn't match the declared shape."""
    if value is None:
        return None

    if field_type == "string":
        return value if isinstance(value, str) else str(value)

    if field_type == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ProjectionError(f"Field '{path}': expected number, got {value!r}")

    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        raise ProjectionError(f"Field '{path}': expected boolean, got {value!r}")

    if field_type in ("string[]", "number[]"):
        if not isinstance(value, list):
            raise ProjectionError(f"Field '{path}': expected {field_type}, got {value!r}")
        elem_type = "number" if field_type == "number[]" else "string"
        return [_coerce_type(v, elem_type, path) for v in value]

    return value


def _project_field(profile_data: dict, field: ConfigField, on_missing: str) -> tuple[bool, Any]:
    """Returns (should_include, value) for one config field."""
    source_path = field.from_ or field.path
    value = resolve_path(profile_data, source_path)
    value = _apply_normalize(value, field.normalize)
    value = _coerce_type(value, field.type, field.path)

    if value is None:
        if field.required or on_missing == "error":
            raise ProjectionError(f"Required field '{field.path}' is missing")
        if on_missing == "omit":
            return False, None
        return True, None

    return True, value


def _validate_config(config: OutputConfig) -> None:
    """Rejects configs with duplicate output paths.

    Each field's "from" only ever reads from the canonical profile, never from
    another output field, so a true circular reference between fields can't
    arise in this architecture. A duplicate output path is the closest real
    misconfiguration — two fields would silently overwrite each other — so we
    raise rather than let one clobber the other.
    """
    seen: set[str] = set()
    for field in config.fields:
        if field.path in seen:
            raise ProjectionError(f"Duplicate output path '{field.path}' in config")
        seen.add(field.path)


def project(profile: CanonicalProfile, config: OutputConfig) -> dict[str, Any]:
    """Reshape a CanonicalProfile into the dict described by an OutputConfig."""
    _validate_config(config)
    profile_data = profile.model_dump(mode="json")
    result: dict[str, Any] = {}

    for field in config.fields:
        include, value = _project_field(profile_data, field, config.on_missing)
        if include:
            result[field.path] = value

    if config.include_confidence:
        result["overall_confidence"] = profile.overall_confidence
    if config.include_provenance:
        result["provenance"] = profile_data["provenance"]

    logger.info("Projected candidate %s -> %d output field(s)", profile.candidate_id, len(result))
    return result
