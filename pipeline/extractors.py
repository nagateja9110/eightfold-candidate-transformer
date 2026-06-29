"""Source extractors: turn raw files into lists of RawSource envelopes.

Extractors never raise on bad input — a missing file or malformed row is
logged and skipped so one bad source can't take down the whole run.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from models.schemas import RawSource, SourceType

logger = logging.getLogger(__name__)

CSV_TRUST_SCORE = 0.8
GITHUB_TRUST_SCORE = 0.6

# Maps recruiter CSV column names -> internal field names.
CSV_COLUMN_MAP = {
    "candidate_id": "candidate_id",
    "name": "name",
    "email": "email",
    "phone": "phone",
    "current_company": "current_company",
    "title": "title",
    "location": "location",
}

GITHUB_FIELDS = ["name", "email", "bio", "location", "company", "blog", "languages"]


class CSVExtractor:
    """Extracts recruiter CSV rows into RawSource envelopes."""

    def extract(self, path: str | Path) -> list[RawSource]:
        path = Path(path)
        if not path.exists():
            logger.warning("CSV source not found, skipping: %s", path)
            return []

        sources: list[RawSource] = []
        try:
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for line_no, row in enumerate(reader, start=2):
                    record = self._parse_row(row, line_no)
                    if record is not None:
                        sources.append(
                            RawSource(
                                source_type=SourceType.RECRUITER_CSV,
                                raw_data=record,
                                trust_score=CSV_TRUST_SCORE,
                            )
                        )
        except (csv.Error, OSError, UnicodeDecodeError) as exc:
            logger.warning("Failed to read CSV %s: %s", path, exc)
            return []

        logger.info("Extracted %d record(s) from CSV %s", len(sources), path)
        return sources

    def _parse_row(self, row: dict[str, str | None], line_no: int) -> dict | None:
        if not row.get("candidate_id"):
            logger.warning("CSV row %d missing candidate_id, skipping", line_no)
            return None

        record: dict[str, str | None] = {}
        for csv_col, internal_field in CSV_COLUMN_MAP.items():
            value = row.get(csv_col)
            value = value.strip() if isinstance(value, str) else value
            record[internal_field] = value if value else None
        return record


class GitHubExtractor:
    """Extracts mock GitHub API responses (candidate_id -> profile dict) into RawSource envelopes."""

    def extract(self, path: str | Path) -> list[RawSource]:
        path = Path(path)
        if not path.exists():
            logger.warning("GitHub source not found, skipping: %s", path)
            return []

        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            logger.warning("Failed to read GitHub source %s: %s", path, exc)
            return []

        if not isinstance(data, dict):
            logger.warning("GitHub source %s is not a JSON object, skipping", path)
            return []

        sources: list[RawSource] = []
        for candidate_id, profile in data.items():
            record = self._parse_profile(candidate_id, profile)
            if record is not None:
                sources.append(
                    RawSource(
                        source_type=SourceType.GITHUB_API,
                        raw_data=record,
                        trust_score=GITHUB_TRUST_SCORE,
                    )
                )

        logger.info("Extracted %d profile(s) from GitHub source %s", len(sources), path)
        return sources

    def _parse_profile(self, candidate_id: str, profile: object) -> dict | None:
        if not isinstance(profile, dict):
            logger.warning("GitHub profile for %s is not an object, skipping", candidate_id)
            return None

        record: dict = {"candidate_id": candidate_id}
        for field in GITHUB_FIELDS:
            value = profile.get(field)
            if isinstance(value, str):
                value = value.strip() or None
            record[field] = value
        return record
