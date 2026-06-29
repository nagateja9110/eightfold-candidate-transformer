"""Merge engine: groups raw sources into candidates and resolves field-level conflicts.

Candidate matching is intentionally identity-based (email -> phone -> name+location)
rather than relying on any source-provided candidate_id, since real-world sources
rarely share a common ID. The candidate_id on the output profile is taken from
whichever source happened to provide one, purely for display/reference.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from models.schemas import (
    CanonicalProfile,
    Education,
    Experience,
    Links,
    Location,
    Provenance,
    RawSource,
    Skill,
    SourceType,
)
from pipeline.normalizers import (
    normalize_email,
    normalize_location,
    normalize_name,
    normalize_phone,
    normalize_skill,
)

logger = logging.getLogger(__name__)

SINGLE_SOURCE_CONFIDENCE = 0.6
FULL_AGREEMENT_CONFIDENCE = 0.9
MAJORITY_CONFIDENCE = 0.7
CONFLICT_CONFIDENCE = 0.5

ScalarValue = tuple[Any, SourceType, float]


@dataclass
class _ExtractedFields:
    """A single source's contribution to a candidate, after per-source field mapping."""

    candidate_id: str | None
    full_name: str | None
    email: str | None
    phone: str | None
    location: Location
    headline: str | None
    company: str | None
    title: str | None
    skills: list[str]
    github_url: str | None
    portfolio_url: str | None
    source_type: SourceType
    trust_score: float


def _extract_csv_fields(raw: RawSource) -> _ExtractedFields:
    data = raw.raw_data
    return _ExtractedFields(
        candidate_id=data.get("candidate_id"),
        full_name=normalize_name(data.get("name")),
        email=normalize_email(data.get("email")),
        phone=normalize_phone(data.get("phone")),
        location=normalize_location(data.get("location")),
        headline=data.get("title") or None,
        company=data.get("current_company") or None,
        title=data.get("title") or None,
        skills=[],
        github_url=None,
        portfolio_url=None,
        source_type=raw.source_type,
        trust_score=raw.trust_score,
    )


def _extract_github_fields(raw: RawSource) -> _ExtractedFields:
    data = raw.raw_data
    languages = data.get("languages") or []
    skills = [s for s in (normalize_skill(lang) for lang in languages if lang) if s]
    return _ExtractedFields(
        candidate_id=data.get("candidate_id"),
        full_name=normalize_name(data.get("name")),
        email=normalize_email(data.get("email")),
        phone=None,
        location=normalize_location(data.get("location")),
        headline=data.get("bio") or None,
        company=data.get("company") or None,
        title=None,
        skills=skills,
        github_url=None,
        portfolio_url=data.get("blog") or None,
        source_type=raw.source_type,
        trust_score=raw.trust_score,
    )


_FIELD_EXTRACTORS = {
    SourceType.RECRUITER_CSV: _extract_csv_fields,
    SourceType.GITHUB_API: _extract_github_fields,
}


def _extract(raw: RawSource) -> _ExtractedFields:
    return _FIELD_EXTRACTORS[raw.source_type](raw)


def _group_by_candidate(items: list[_ExtractedFields]) -> list[list[_ExtractedFields]]:
    """Group extracted fields into candidates via email -> phone -> name+location matching."""
    groups: list[list[_ExtractedFields]] = []
    email_to_group: dict[str, int] = {}
    phone_to_group: dict[str, int] = {}

    for item in items:
        group_idx = None
        if item.email and item.email in email_to_group:
            group_idx = email_to_group[item.email]
        elif item.phone and item.phone in phone_to_group:
            group_idx = phone_to_group[item.phone]
        else:
            group_idx = _find_name_location_match(item, groups)

        if group_idx is None:
            groups.append([item])
            group_idx = len(groups) - 1
        else:
            groups[group_idx].append(item)

        if item.email:
            email_to_group[item.email] = group_idx
        if item.phone:
            phone_to_group[item.phone] = group_idx

    return groups


def _find_name_location_match(item: _ExtractedFields, groups: list[list[_ExtractedFields]]) -> int | None:
    if not item.full_name or not item.location.city:
        return None
    for idx, group in enumerate(groups):
        for other in group:
            if (
                other.full_name
                and other.location.city
                and other.full_name.lower() == item.full_name.lower()
                and other.location.city.lower() == item.location.city.lower()
            ):
                return idx
    return None


def _resolve_scalar(values: list[ScalarValue]) -> tuple[Any, float, list[SourceType]]:
    """Resolve a scalar field across sources per the 5-rule conflict policy."""
    if not values:
        return None, 0.0, []

    if len(values) == 1:
        value, source, _ = values[0]
        return value, SINGLE_SOURCE_CONFIDENCE, [source]

    counts = Counter(v for v, _, _ in values)
    if len(counts) == 1:
        winner = values[0][0]
        contributing = [s for _, s, _ in values]
        return winner, FULL_AGREEMENT_CONFIDENCE, contributing

    winner_value, winner_count = counts.most_common(1)[0]
    if winner_count > len(values) / 2:
        contributing = [s for v, s, _ in values if v == winner_value]
        return winner_value, MAJORITY_CONFIDENCE, contributing

    best = max(values, key=lambda t: t[2])
    return best[0], CONFLICT_CONFIDENCE, [best[1]]


def _union_field(values: list[str | None], sources: list[SourceType]) -> tuple[list[str], list[SourceType]]:
    """Union unique non-null values, preserving first-seen order, with contributing sources."""
    seen: dict[str, None] = {}
    contributing: list[SourceType] = []
    for value, source in zip(values, sources):
        if value and value not in seen:
            seen[value] = None
            contributing.append(source)
    return list(seen.keys()), contributing


def _merge_location(group: list[_ExtractedFields]) -> tuple[Location, float, list[SourceType]]:
    city_values = [(g.location.city, g.source_type, g.trust_score) for g in group if g.location.city]
    region_values = [(g.location.region, g.source_type, g.trust_score) for g in group if g.location.region]
    country_values = [(g.location.country, g.source_type, g.trust_score) for g in group if g.location.country]

    city, city_conf, city_sources = _resolve_scalar(city_values)
    region, region_conf, region_sources = _resolve_scalar(region_values)
    country, country_conf, country_sources = _resolve_scalar(country_values)

    confidences = [c for c in (city_conf, region_conf, country_conf) if c > 0]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    sources = list(dict.fromkeys(city_sources + region_sources + country_sources))
    return Location(city=city, region=region, country=country), overall_confidence, sources


def _merge_links(group: list[_ExtractedFields]) -> tuple[Links, list[SourceType]]:
    github_values = [(g.github_url, g.source_type, g.trust_score) for g in group if g.github_url]
    portfolio_values = [(g.portfolio_url, g.source_type, g.trust_score) for g in group if g.portfolio_url]

    github, _, github_sources = _resolve_scalar(github_values)
    portfolio, _, portfolio_sources = _resolve_scalar(portfolio_values)

    sources = list(dict.fromkeys(github_sources + portfolio_sources))
    return Links(github=github, linkedin=None, portfolio=portfolio, other=[]), sources


def _merge_skills(group: list[_ExtractedFields]) -> tuple[list[Skill], list[SourceType]]:
    """Dedupe skills by canonical name; confidence is a trust-weighted average with a
    small bonus per corroborating source, capped at 1.0."""
    occurrences: dict[str, list[tuple[SourceType, float]]] = {}
    for g in group:
        for skill_name in g.skills:
            occurrences.setdefault(skill_name, []).append((g.source_type, g.trust_score))

    skills: list[Skill] = []
    all_sources: list[SourceType] = []
    for name, occ in sorted(occurrences.items()):
        avg_trust = sum(t for _, t in occ) / len(occ)
        corroboration_bonus = 0.1 * (len(occ) - 1)
        confidence = round(min(1.0, avg_trust + corroboration_bonus), 2)
        sources = [s for s, _ in occ]
        skills.append(Skill(name=name, confidence=confidence, sources=sources))
        all_sources.extend(sources)

    return skills, list(dict.fromkeys(all_sources))


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")


def _company_key(company: str) -> str:
    """Normalizes a company string for matching only (e.g. '@acme-inc' ~ 'Acme Inc')."""
    return _NON_ALNUM_RE.sub("", company.lower())


def _merge_experience(group: list[_ExtractedFields]) -> tuple[list[Experience], list[SourceType]]:
    """Groups entries by normalized company name; no source in scope provides dates,
    so start/end/summary remain null rather than being invented."""
    by_company: dict[str, list[_ExtractedFields]] = {}
    for g in group:
        if g.company:
            by_company.setdefault(_company_key(g.company), []).append(g)

    experience: list[Experience] = []
    all_sources: list[SourceType] = []
    for entries in by_company.values():
        company_values = [(e.company, e.source_type, e.trust_score) for e in entries]
        company_display, _, _ = _resolve_scalar(company_values)

        title_values = [(e.title, e.source_type, e.trust_score) for e in entries if e.title]
        title, _, _ = _resolve_scalar(title_values)

        experience.append(Experience(company=company_display, title=title, start=None, end=None, summary=None))
        all_sources.extend(e.source_type for e in entries)

    return experience, list(dict.fromkeys(all_sources))


def _merge_group(group: list[_ExtractedFields]) -> CanonicalProfile:
    provenance: list[Provenance] = []

    def add_provenance(field_name: str, sources: list[SourceType], contributing_count: int) -> None:
        if not sources:
            return
        method = "merged" if contributing_count > 1 else "normalized"
        for source in dict.fromkeys(sources):
            provenance.append(Provenance(field=field_name, source=source, method=method))

    name_values = [(g.full_name, g.source_type, g.trust_score) for g in group if g.full_name]
    full_name, name_conf, name_sources = _resolve_scalar(name_values)
    add_provenance("full_name", name_sources, len(name_values))

    headline_values = [(g.headline, g.source_type, g.trust_score) for g in group if g.headline]
    headline, headline_conf, headline_sources = _resolve_scalar(headline_values)
    add_provenance("headline", headline_sources, len(headline_values))

    emails, email_sources = _union_field([g.email for g in group], [g.source_type for g in group])
    email_conf = 1.0 if emails else 0.0
    add_provenance("emails", email_sources, len(email_sources))

    phones, phone_sources = _union_field([g.phone for g in group], [g.source_type for g in group])
    phone_conf = 1.0 if phones else 0.0
    add_provenance("phones", phone_sources, len(phone_sources))

    location, location_conf, location_sources = _merge_location(group)
    add_provenance("location", location_sources, len(location_sources))

    links, link_sources = _merge_links(group)
    link_conf = 1.0 if any([links.github, links.linkedin, links.portfolio, links.other]) else 0.0
    add_provenance("links", link_sources, len(link_sources))

    skills, skill_sources = _merge_skills(group)
    skills_conf = sum(s.confidence for s in skills) / len(skills) if skills else 0.0
    add_provenance("skills", skill_sources, len(skill_sources))

    experience, experience_sources = _merge_experience(group)
    experience_conf = (
        MAJORITY_CONFIDENCE
        if len(experience_sources) > 1
        else (SINGLE_SOURCE_CONFIDENCE if experience_sources else 0.0)
    )
    add_provenance("experience", experience_sources, len(experience_sources))

    fallback_seed = sorted(g.email or g.phone or "" for g in group if (g.email or g.phone))
    candidate_id = next((g.candidate_id for g in group if g.candidate_id), None)
    if not candidate_id:
        candidate_id = "CAND-" + ("-".join(fallback_seed)[:40] if fallback_seed else "UNKNOWN")
    else:
        id_source = next(g.source_type for g in group if g.candidate_id)
        provenance.append(Provenance(field="candidate_id", source=id_source, method="extracted"))

    education: list[Education] = []  # no source in scope provides structured education data

    confidences = [
        c
        for c in (name_conf, headline_conf, email_conf, phone_conf, location_conf, link_conf, skills_conf, experience_conf)
        if c > 0
    ]
    overall_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

    return CanonicalProfile(
        candidate_id=candidate_id,
        full_name=full_name,
        emails=emails,
        phones=phones,
        location=location,
        links=links,
        headline=headline,
        years_experience=None,
        skills=skills,
        experience=experience,
        education=education,
        provenance=provenance,
        overall_confidence=overall_confidence,
    )


def merge(raw_sources: list[RawSource]) -> list[CanonicalProfile]:
    """Group raw sources by candidate identity and merge each group into one CanonicalProfile."""
    extracted = [_extract(r) for r in raw_sources]
    groups = _group_by_candidate(extracted)
    logger.info("Merged %d raw source(s) into %d candidate profile(s)", len(raw_sources), len(groups))
    return [_merge_group(group) for group in groups]
