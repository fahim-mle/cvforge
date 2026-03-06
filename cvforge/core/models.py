"""Pydantic data models for the CVForge master CV schema and JD parse output.

These models are the foundational data layer — every module in the system
(YAML loader, tailoring engine, ATS scorer, template renderer) consumes them.

Model dependency order (leaf → root):
    Personal → RoleVariant → Skill → SkillGroup → Highlight → Experience
    → Education → Certification → MasterCV

    JDKeywords → ParsedJD
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "Personal",
    "RoleVariant",
    "Skill",
    "SkillGroup",
    "Highlight",
    "Experience",
    "Education",
    "Certification",
    "MasterCV",
    "JDKeywords",
    "ParsedJD",
]

# ---------------------------------------------------------------------------
# Shared type alias
# ---------------------------------------------------------------------------

# A non-empty, whitespace-stripped string.  Pydantic v2 runs `str` coercion
# before validators, so we strip in a reusable validator rather than a custom
# type to keep the schema output clean.
StrField = Annotated[str, Field(min_length=1)]


def _strip(v: str) -> str:
    """Strip leading/trailing whitespace from a string value."""
    return v.strip()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Personal(BaseModel):
    """Contact and identity information for the CV owner.

    All fields are required; linkedin and github are stored as plain strings
    (full URLs) so ATS parsers receive them verbatim without Pydantic's
    HttpUrl serialisation quirks.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    email: str
    phone: str
    location: str
    visa: str
    linkedin: str
    github: str

    # Strip whitespace from every string field in one validator pass.
    @field_validator(
        "name", "email", "phone", "location", "visa", "linkedin", "github", mode="before"
    )
    @classmethod
    def strip_strings(cls, v: str) -> str:
        """Remove leading/trailing whitespace from all string fields."""
        if isinstance(v, str):
            return _strip(v)
        return v


class RoleVariant(BaseModel):
    """A named CV persona (e.g. 'software_engineer', 'ml_engineer').

    Each variant carries its own professional summary and controls which skill
    groups are surfaced first via ``skill_priority``.

    ``summary_base`` is an optional reference to another variant's key; when
    set, the tailoring engine inherits that variant's summary as a starting
    point instead of using a standalone ``summary``.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str | None = None
    summary_base: str | None = None
    skill_priority: list[str] = Field(default_factory=list)

    @field_validator("title", "summary", "summary_base", mode="before")
    @classmethod
    def strip_strings(cls, v: object) -> object:
        """Strip whitespace from string fields; pass through None unchanged."""
        if isinstance(v, str):
            return _strip(v)
        return v


class Skill(BaseModel):
    """A single skill entry within a skill group.

    ``aliases`` enables synonym matching against job-description keywords
    (e.g. 'React' → 'React.js').  ``tags`` link the skill to role-variant
    categories for priority ordering and ATS scoring.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    aliases: list[str] = Field(default_factory=list)
    tags: list[str]

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        """Strip whitespace from the skill name."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("aliases", "tags", mode="before")
    @classmethod
    def strip_list_strings(cls, v: list[object]) -> list[object]:
        """Strip whitespace from every element in list-of-string fields."""
        if isinstance(v, list):
            return [_strip(item) if isinstance(item, str) else item for item in v]
        return v


class SkillGroup(BaseModel):
    """A labelled cluster of related skills rendered as one CV section.

    ``tags`` at the group level are optional metadata; individual ``Skill``
    entries carry their own tags for fine-grained matching.
    """

    model_config = ConfigDict(extra="forbid")

    group: str
    tags: list[str] | None = None
    skills: list[Skill]

    @field_validator("group", mode="before")
    @classmethod
    def strip_group(cls, v: str) -> str:
        """Strip whitespace from the group label."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def strip_tags(cls, v: object) -> object:
        """Strip whitespace from tag strings when present."""
        if isinstance(v, list):
            return [_strip(item) if isinstance(item, str) else item for item in v]
        return v


class Highlight(BaseModel):
    """A single bullet-point achievement within an experience or education entry.

    ``variant_only`` gates visibility: when set, the highlight is rendered
    only for the listed variant keys.  When ``None`` (the default), the
    highlight appears in every variant.

    ``tags`` drive ATS keyword matching and granular selection by the
    tailoring engine.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    tags: list[str] = Field(default_factory=list)
    # None → show for all variants; list → show only for named variants.
    variant_only: list[str] | None = None

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        """Strip whitespace from the highlight text."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def strip_tags(cls, v: list[object]) -> list[object]:
        """Strip whitespace from tag strings."""
        if isinstance(v, list):
            return [_strip(item) if isinstance(item, str) else item for item in v]
        return v


class Experience(BaseModel):
    """A single employment record in the work history.

    ``role_variants`` maps each variant key to the display title used for
    that variant (e.g. the same QCIF role becomes "Software Engineer" or
    "ML Engineer" depending on the target CV).

    ``show_for`` gates the entire entry: when set, the experience is omitted
    from variants not listed.  When ``None``, it appears in all variants.
    """

    model_config = ConfigDict(extra="forbid")

    company: str
    location: str
    start: str
    # None indicates a current/ongoing role.
    end: str | None = None
    # Maps variant key → display title for that variant.
    role_variants: dict[str, str]
    tags: list[str] = Field(default_factory=list)
    highlights: list[Highlight] = Field(default_factory=list)
    # None → show for all variants; list → show only for named variants.
    show_for: list[str] | None = None

    @field_validator("company", "location", "start", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        """Strip whitespace from scalar string fields."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("end", mode="before")
    @classmethod
    def strip_end(cls, v: object) -> object:
        """Strip whitespace from end date when present."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def strip_tags(cls, v: list[object]) -> list[object]:
        """Strip whitespace from tag strings."""
        if isinstance(v, list):
            return [_strip(item) if isinstance(item, str) else item for item in v]
        return v

    @field_validator("role_variants", mode="before")
    @classmethod
    def strip_role_variant_values(cls, v: object) -> object:
        """Strip whitespace from role variant display titles."""
        if isinstance(v, dict):
            return {k: (_strip(val) if isinstance(val, str) else val) for k, val in v.items()}
        return v


class Education(BaseModel):
    """An academic qualification.

    ``start`` is optional because some historical records omit it.
    ``highlights`` and ``tags`` default to empty lists so minimal entries
    (degree + institution only) are valid without extra keys.
    """

    model_config = ConfigDict(extra="forbid")

    degree: str
    institution: str
    location: str
    start: str | None = None
    end: str
    tags: list[str] = Field(default_factory=list)
    highlights: list[Highlight] = Field(default_factory=list)

    @field_validator("degree", "institution", "location", "end", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        """Strip whitespace from required string fields."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("start", mode="before")
    @classmethod
    def strip_start(cls, v: object) -> object:
        """Strip whitespace from start date when present."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def strip_tags(cls, v: list[object]) -> list[object]:
        """Strip whitespace from tag strings."""
        if isinstance(v, list):
            return [_strip(item) if isinstance(item, str) else item for item in v]
        return v


class Certification(BaseModel):
    """A professional certification or credential.

    ``tags`` default to an empty list; they are used for ATS keyword matching
    when present.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    issuer: str
    tags: list[str] = Field(default_factory=list)

    @field_validator("name", "issuer", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        """Strip whitespace from string fields."""
        if isinstance(v, str):
            return _strip(v)
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def strip_tags(cls, v: list[object]) -> list[object]:
        """Strip whitespace from tag strings."""
        if isinstance(v, list):
            return [_strip(item) if isinstance(item, str) else item for item in v]
        return v


class MasterCV(BaseModel):
    """Root model representing the complete master CV document.

    Loaded from ``master_cv.yaml``, this is the single source of truth that
    every downstream module (tailoring engine, ATS scorer, PDF renderer)
    operates on.  All child models enforce ``extra='forbid'`` so YAML typos
    surface as validation errors rather than silent data loss.
    """

    model_config = ConfigDict(extra="forbid")

    personal: Personal
    # Keys are variant identifiers (e.g. 'software_engineer', 'ml_engineer').
    role_variants: dict[str, RoleVariant]
    skill_groups: list[SkillGroup]
    experience: list[Experience]
    education: list[Education]
    certifications: list[Certification] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# JD Parse Output models
# ---------------------------------------------------------------------------


class JDKeywords(BaseModel):
    """Classified keyword lists extracted from a job description.

    Keywords are grouped by signal strength:
    - ``required``: terms near "must", "required", "essential"
    - ``preferred``: terms near "nice to have", "bonus", "preferred"
    - ``soft_skills``: interpersonal/behavioural terms ("team player", "communication")

    All lists contain normalized, deduplicated strings.
    """

    model_config = ConfigDict(extra="forbid")

    required: list[str] = Field(default_factory=list)
    preferred: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)


class ParsedJD(BaseModel):
    """Structured output from parsing a raw job description.

    Produced by ``jd_parser``, consumed by ``matcher`` and ``scorer``.
    Not persisted to disk — lives in memory for the duration of a tailoring
    session.

    All fields are optional because not every JD contains every piece of
    metadata; callers must handle ``None`` gracefully.
    """

    model_config = ConfigDict(extra="forbid")

    # Extracted role title, e.g. "Senior Frontend Developer".
    role: str | None = None
    # Extracted company name, e.g. "Acme Inc".
    company: str | None = None
    # Classified keyword lists — always present, may contain empty sub-lists.
    keywords: JDKeywords = Field(default_factory=JDKeywords)
    # Minimum years of experience stated in the JD, e.g. 5.
    experience_years: int | None = None
