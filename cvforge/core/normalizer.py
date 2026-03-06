"""Keyword normalizer for CVForge.

Builds a unified synonym index from two sources:
1. ``synonyms.yaml`` — canonical_term → [aliases]
2. Master CV ``skill_groups`` — skill.name → skill.aliases

Provides case-insensitive lookup with optional fuzzy fallback via rapidfuzz,
so extracted JD keywords can be resolved to their canonical forms before
matching and scoring.

Typical usage::

    from cvforge.core import load_master_cv, load_synonyms
    from cvforge.core.normalizer import build_synonym_index, normalize_keywords

    cv = load_master_cv()
    synonyms = load_synonyms()
    index = build_synonym_index(synonyms, cv.skill_groups)
    normalized = normalize_keywords(["js", "React.js", "k8s"], index)
    # → ["javascript", "React.js", "kubernetes"]
"""

from __future__ import annotations

import logging

from rapidfuzz import process as rf_process

from cvforge.core.models import SkillGroup

__all__ = [
    "build_synonym_index",
    "normalize_keyword",
    "normalize_keywords",
]

logger = logging.getLogger(__name__)


def build_synonym_index(
    synonyms: dict[str, list[str]],
    skill_groups: list[SkillGroup],
) -> dict[str, str]:
    """Build a bidirectional lookup: any alias/variant → canonical form.

    Merges two sources:

    1. **synonyms.yaml** — each key is the canonical term; its list of values
       are aliases that should resolve back to that canonical term.
    2. **Master CV skill aliases** — each ``Skill.name`` is the canonical form;
       its ``Skill.aliases`` list contains surface variants.

    All index keys are lowercased so lookups are case-insensitive.  The
    canonical form is stored in its original casing (as declared in the source
    file) so the returned value is human-readable.

    Conflict resolution: synonyms.yaml takes precedence over skill aliases.
    If the same lowercased alias appears in both sources, the synonyms.yaml
    mapping wins (it is processed first and later writes are skipped).

    Args:
        synonyms: Mapping of canonical_term → list[alias] from synonyms.yaml.
        skill_groups: List of ``SkillGroup`` objects from the master CV.

    Returns:
        ``dict`` mapping lowercased alias/variant → canonical form string.

    Example::

        {
            "js": "javascript",
            "es6": "javascript",
            "react.js": "react",
            "reactjs": "react",
            "python3": "python",
            ...
        }
    """
    index: dict[str, str] = {}

    # --- Source 1: synonyms.yaml ---
    # canonical_term (key) → [aliases]
    # We also map the canonical term itself so an exact match on the canonical
    # form is handled uniformly (e.g. "javascript" → "javascript").
    for canonical, aliases in synonyms.items():
        # Map the canonical key to itself (lowercased key → original key).
        canonical_lower = canonical.lower()
        if canonical_lower not in index:
            index[canonical_lower] = canonical

        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower not in index:
                index[alias_lower] = canonical
            else:
                logger.debug(
                    "Synonym index: alias %r already mapped to %r; skipping duplicate from %r",
                    alias_lower,
                    index[alias_lower],
                    canonical,
                )

    # --- Source 2: Master CV skill aliases ---
    # skill.name is the canonical form; skill.aliases are surface variants.
    for group in skill_groups:
        for skill in group.skills:
            skill_lower = skill.name.lower()
            if skill_lower not in index:
                # Map the skill name to itself so it is findable by exact match.
                index[skill_lower] = skill.name

            for alias in skill.aliases:
                alias_lower = alias.lower()
                if alias_lower not in index:
                    index[alias_lower] = skill.name
                else:
                    logger.debug(
                        "Synonym index: alias %r already mapped to %r; "
                        "skipping duplicate from skill %r",
                        alias_lower,
                        index[alias_lower],
                        skill.name,
                    )

    logger.debug("Built synonym index with %d entries", len(index))
    return index


def normalize_keyword(
    keyword: str,
    synonym_index: dict[str, str],
    fuzzy_threshold: int = 85,
) -> str:
    """Normalize a single keyword using the synonym index.

    Resolution order:

    1. **Exact match** (case-insensitive) — ``keyword.lower()`` looked up
       directly in ``synonym_index``.
    2. **Fuzzy match** — ``rapidfuzz.process.extractOne`` finds the closest
       key in ``synonym_index``; accepted only when the score is ≥
       ``fuzzy_threshold``.
    3. **No match** — the original ``keyword`` is returned unchanged.

    Args:
        keyword: Raw keyword extracted from a JD (may be mixed-case).
        synonym_index: Output of :func:`build_synonym_index`.
        fuzzy_threshold: Minimum rapidfuzz score (0–100) to accept a fuzzy
            match.  Default 85 matches the project-wide ATS scoring threshold.

    Returns:
        The canonical form of the keyword, or the original keyword if no
        match is found.
    """
    if not keyword or not synonym_index:
        return keyword

    keyword_lower = keyword.lower()

    # --- Step 1: exact match (case-insensitive) ---
    if keyword_lower in synonym_index:
        canonical = synonym_index[keyword_lower]
        logger.debug("normalize_keyword: exact match %r → %r", keyword, canonical)
        return canonical

    # --- Step 2: fuzzy match against index keys ---
    # extractOne returns (best_match_key, score, index) or None when choices is empty.
    result = rf_process.extractOne(
        keyword_lower, synonym_index.keys(), score_cutoff=fuzzy_threshold
    )
    if result is not None:
        best_key, score, _ = result
        canonical = synonym_index[best_key]
        logger.debug(
            "normalize_keyword: fuzzy match %r → %r (score=%.1f via key %r)",
            keyword,
            canonical,
            score,
            best_key,
        )
        return canonical

    # --- Step 3: no match — return original ---
    logger.debug("normalize_keyword: no match for %r, returning unchanged", keyword)
    return keyword


def normalize_keywords(
    keywords: list[str],
    synonym_index: dict[str, str],
    fuzzy_threshold: int = 85,
) -> list[str]:
    """Normalize a list of keywords, deduplicating after normalization.

    Each keyword is passed through :func:`normalize_keyword`.  After
    normalization, duplicates that arise from multiple surface forms resolving
    to the same canonical term are removed.  First-seen order is preserved.

    Args:
        keywords: Raw keyword list extracted from a JD.
        synonym_index: Output of :func:`build_synonym_index`.
        fuzzy_threshold: Passed through to :func:`normalize_keyword`.

    Returns:
        Deduplicated list of normalized keywords in first-seen order.
    """
    seen: set[str] = set()
    result: list[str] = []

    for kw in keywords:
        normalized = normalize_keyword(kw, synonym_index, fuzzy_threshold)
        # Deduplicate on the normalized form (case-sensitive, as returned by
        # normalize_keyword — canonical forms already have consistent casing).
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)

    return result
