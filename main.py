#!/usr/bin/env python3
"""CLI entry point for the Multi-Source Candidate Data Transformer.

Pipeline: extract -> normalize (inside extractors/merger) -> merge -> project -> validate -> write.
A missing/garbage source is logged and skipped rather than crashing the run.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from models.schemas import OutputConfig
from pipeline.extractors import CSVExtractor, GitHubExtractor
from pipeline.merger import merge
from pipeline.projector import ProjectionError, project
from pipeline.validator import validate

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parses CLI arguments for the candidate transformer."""
    parser = argparse.ArgumentParser(description="Multi-Source Candidate Data Transformer")
    parser.add_argument("--recruiter-csv", help="Path to a recruiter CSV export")
    parser.add_argument("--github-json", help="Path to a mock GitHub API JSON file")
    parser.add_argument("--config", required=True, help="Path to the output config JSON")
    parser.add_argument("--output", required=True, help="Path to write the resulting JSON")
    return parser.parse_args(argv)


def load_config(path: str) -> OutputConfig:
    """Loads and validates an OutputConfig from a JSON file."""
    with open(path, encoding="utf-8") as f:
        return OutputConfig.model_validate(json.load(f))


def run_pipeline(recruiter_csv: str | None, github_json: str | None, config: OutputConfig) -> list[dict]:
    """Runs extract -> merge -> project -> validate for every candidate found."""
    raw_sources = []
    if recruiter_csv:
        raw_sources.extend(CSVExtractor().extract(recruiter_csv))
    if github_json:
        raw_sources.extend(GitHubExtractor().extract(github_json))

    profiles = merge(raw_sources)

    results = []
    for profile in profiles:
        try:
            result = project(profile, config)
        except ProjectionError as exc:
            logger.warning("Skipping candidate %s: %s", profile.candidate_id, exc)
            continue

        is_valid, errors = validate(profile, config, result)
        if not is_valid:
            logger.warning("Validation errors for candidate %s: %s", profile.candidate_id, errors)

        results.append(result)

    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code (0 success, 1 failure)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args(argv)

    if not args.recruiter_csv and not args.github_json:
        logger.error("At least one of --recruiter-csv or --github-json must be provided")
        return 1

    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("Failed to load config %s: %s", args.config, exc)
        return 1

    try:
        results = run_pipeline(args.recruiter_csv, args.github_json, config)
    except Exception as exc:  # noqa: BLE001 - last-resort guard: a bad run must exit cleanly, not crash
        logger.error("Pipeline failed unexpectedly: %s", exc)
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    logger.info("Wrote %d profile(s) to %s", len(results), output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
