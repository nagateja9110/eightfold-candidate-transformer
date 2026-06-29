"""Pydantic models for the Multi-Source Candidate Data Transformer.

Defines the raw-source envelope, the internal canonical profile, and the
runtime output-config schema used by the projection layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    RECRUITER_CSV = "RECRUITER_CSV"
    GITHUB_API = "GITHUB_API"


class Provenance(BaseModel):
    field: str
    source: SourceType
    method: str


class Skill(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceType] = Field(default_factory=list)


class Experience(BaseModel):
    company: str | None = None
    title: str | None = None
    start: str | None = None  # YYYY-MM
    end: str | None = None  # YYYY-MM
    summary: str | None = None


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    end_year: int | None = None


class Location(BaseModel):
    city: str | None = None
    region: str | None = None
    country: str | None = None  # ISO-3166 alpha-2


class Links(BaseModel):
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    other: list[str] = Field(default_factory=list)


class CanonicalProfile(BaseModel):
    """The single trustworthy internal record produced by the merge stage."""

    candidate_id: str
    full_name: str | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    location: Location = Field(default_factory=Location)
    links: Links = Field(default_factory=Links)
    headline: str | None = None
    years_experience: float | None = None
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    provenance: list[Provenance] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RawSource(BaseModel):
    """Envelope wrapping a single raw record pulled from one source."""

    source_type: SourceType
    raw_data: dict[str, Any]
    trust_score: float = Field(ge=0.0, le=1.0)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class ConfigField(BaseModel):
    """One field requested in a runtime output config."""

    path: str
    type: Literal["string", "number", "boolean", "string[]", "number[]", "object"]
    from_: str | None = Field(default=None, alias="from")
    required: bool = False
    normalize: str | None = None

    model_config = {"populate_by_name": True}


class OutputConfig(BaseModel):
    """Runtime config that reshapes CanonicalProfile into a custom projection."""

    fields: list[ConfigField]
    include_confidence: bool = True
    include_provenance: bool = True
    on_missing: Literal["null", "omit", "error"] = "null"
