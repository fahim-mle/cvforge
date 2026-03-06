"""JD parser for CVForge.

Extracts structured keyword data from raw job description text using a
heuristic pipeline:

1. YAKE statistical keyword extraction (n-grams, top-30)
2. spaCy NER for named entities (ORG, PRODUCT, GPE) and noun chunks
3. Paragraph-level classification into required / preferred / soft_skills
4. Synonym normalization via the shared normalizer

The parser is intentionally heuristic — it targets 70–80% recall on
well-structured JDs without any LLM dependency.

Typical usage::

    from cvforge.core import parse_jd

    result = parse_jd(jd_text)
    print(result.keywords.required)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from cvforge.core.exceptions import CVForgeValidationError
from cvforge.core.models import JDKeywords, MasterCV, ParsedJD
from cvforge.core.normalizer import build_synonym_index, normalize_keywords

if TYPE_CHECKING:
    # spaCy Language is only imported for type hints; the actual load is lazy.
    from spacy.language import Language

__all__ = ["parse_jd"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy spaCy model — loaded once on first use to avoid startup cost when the
# parser module is imported but not called.
# ---------------------------------------------------------------------------

_nlp: Language | None = None


def _get_nlp() -> Language:
    """Return the shared spaCy model, loading it on first call."""
    global _nlp  # noqa: PLW0603 — intentional module-level singleton
    if _nlp is None:
        import spacy

        logger.debug("Loading spaCy model en_core_web_sm (first use)")
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


# ---------------------------------------------------------------------------
# Known soft-skill surface forms (lower-cased for comparison)
# ---------------------------------------------------------------------------

_SOFT_SKILL_TERMS: frozenset[str] = frozenset(
    [
        "communication",
        "team player",
        "leadership",
        "problem solving",
        "problem-solving",
        "collaboration",
        "mentoring",
        "self-motivated",
        "self motivated",
        "detail-oriented",
        "detail oriented",
        "analytical",
        "adaptable",
        "time management",
        "critical thinking",
        "interpersonal",
        "organisational",
        "organizational",
        "written communication",
        "verbal communication",
        "stakeholder management",
        "presentation skills",
        "fast learner",
        "proactive",
        "initiative",
        "ownership",
        "accountability",
    ]
)

# ---------------------------------------------------------------------------
# Paragraph-level signal markers
# ---------------------------------------------------------------------------

# Patterns that mark a paragraph/section as "required" territory.
_REQUIRED_MARKERS: re.Pattern[str] = re.compile(
    r"\b(required|must have|must-have|essential|mandatory|minimum|you (must|will|should) have"
    r"|what you('ll| will) need|requirements|qualifications)\b",
    re.IGNORECASE,
)

# Patterns that mark a paragraph/section as "preferred" territory.
_PREFERRED_MARKERS: re.Pattern[str] = re.compile(
    r"\b(nice to have|nice-to-have|preferred|bonus|plus|desirable|ideally|advantageous"
    r"|would be (great|a plus|beneficial)|not required but)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _extract_keywords_yake(text: str) -> list[str]:
    """Extract statistical keywords from *text* using YAKE.

    Configured for English, up to trigrams, with aggressive deduplication.
    YAKE scores are lower-is-better; we return only the keyword strings
    (scores are discarded — classification happens downstream).

    Args:
        text: Raw JD text.

    Returns:
        Up to 30 keyword strings, ordered by YAKE relevance (most relevant first).
    """
    import yake

    extractor = yake.KeywordExtractor(
        lan="en",
        n=3,  # max n-gram size
        dedupLim=0.9,
        top=30,
        features=None,
    )
    # YAKE returns list[(keyword, score)]; lower score = more relevant.
    raw: list[tuple[str, float]] = extractor.extract_keywords(text)
    keywords = [kw for kw, _score in raw]
    logger.debug("YAKE extracted %d keywords", len(keywords))
    return keywords


def _extract_entities_spacy(text: str) -> list[str]:
    """Extract named entities and technical noun chunks from *text* via spaCy.

    Entity types collected:
    - ORG  — company / tool / framework names
    - PRODUCT — product names
    - GPE  — geo-political entities (catches some tech names spaCy mislabels)

    Additionally, noun chunks that look like technical terms (≤ 4 tokens,
    no stop-word-only chunks) are included to catch phrases YAKE may miss.

    Args:
        text: Raw JD text.

    Returns:
        Deduplicated list of entity/chunk strings (original casing preserved).
    """
    nlp = _get_nlp()
    doc = nlp(text)

    seen: set[str] = set()
    results: list[str] = []

    def _add(term: str) -> None:
        key = term.strip().lower()
        if key and key not in seen:
            seen.add(key)
            results.append(term.strip())

    # Named entities of interest.
    for ent in doc.ents:
        if ent.label_ in {"ORG", "PRODUCT", "GPE"}:
            _add(ent.text)

    # Noun chunks: keep short ones that aren't purely stop words.
    for chunk in doc.noun_chunks:
        tokens = [t for t in chunk if not t.is_stop and not t.is_punct]
        if tokens and len(chunk) <= 4:
            _add(chunk.text)

    logger.debug("spaCy extracted %d entities/chunks", len(results))
    return results


def _extract_role_title(text: str) -> str | None:
    """Heuristically extract the job title from the opening lines of *text*.

    Checks (in order):
    1. Explicit label patterns: "Role:", "Position:", "Job Title:", "Title:"
    2. The first non-blank line if it is short (≤ 10 words) and starts with
       an uppercase letter — typical of a standalone title line.

    When the first line contains a company suffix in the form
    "Title - Company" or "Title at Company", only the title portion is
    returned.

    Args:
        text: Raw JD text.

    Returns:
        Extracted role title string, or ``None`` if no confident match found.
    """
    # Pattern 1: explicit label on any line.
    label_pattern = re.compile(
        r"^\s*(?:role|position|job title|title)\s*[:\-]\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = label_pattern.search(text)
    if match:
        title = match.group(1).strip()
        logger.debug("Role title found via label pattern: %r", title)
        return title

    # Pattern 2: first non-blank line that looks like a title.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        words = stripped.split()
        # A title line: short, starts with uppercase, no sentence-ending punctuation.
        if (
            1 <= len(words) <= 12
            and stripped[0].isupper()
            and not stripped.endswith((".", "?", "!"))
        ):
            # Strip a trailing "- Company" or "at Company" suffix so we return
            # only the role portion (e.g. "Senior Dev - Acme Inc" → "Senior Dev").
            title = re.sub(r"\s*[-–|]\s*[A-Z].+$", "", stripped).strip()
            if not title:
                title = stripped
            logger.debug("Role title inferred from first line: %r", title)
            return title
        # Stop after the first non-blank line regardless.
        break

    logger.debug("No role title found")
    return None


def _extract_company(text: str, entities: list[str]) -> str | None:
    """Heuristically extract the hiring company name from *text*.

    Checks (in order):
    1. Explicit label patterns: "Company:", "Organisation:", "Employer:"
    2. Title-line suffix: "Role Title - Company Name" or "Role Title at Company"
    3. "About {Company}" section headers (requires a proper-noun company name,
       not generic phrases like "the Role" or "the Team")
    4. "join {Company}" / "at {Company}" inline phrases cross-referenced with
       spaCy ORG entities
    5. Fallback: first spaCy ORG entity in the document

    Args:
        text: Raw JD text.
        entities: ORG/PRODUCT/GPE entities extracted by spaCy.

    Returns:
        Company name string, or ``None`` if no confident match found.
    """
    # Words that are NOT company names even if they look like proper nouns.
    _generic_names: frozenset[str] = frozenset(
        {
            "us",
            "the role",
            "the company",
            "the team",
            "the position",
            "the organisation",
            "the organization",
            "our team",
            "our company",
        }
    )

    # Collect ORG entities for cross-referencing.
    org_lower: set[str] = {ent.lower() for ent in entities}

    # Pattern 1: explicit label.
    label_pattern = re.compile(
        r"^\s*(?:company|organisation|organization|employer|hiring company)\s*[:\-]\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    match = label_pattern.search(text)
    if match:
        company = match.group(1).strip()
        logger.debug("Company found via label pattern: %r", company)
        return company

    # Pattern 2: title-line suffix "Role - Company" or "Role at Company".
    # Only inspect the first non-blank line.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # "Title - Company Name" or "Title | Company Name"
        suffix_match = re.search(r"\s*[-–|]\s*([A-Z][A-Za-z0-9 &.,'-]+)$", stripped)
        if suffix_match:
            candidate = suffix_match.group(1).strip()
            if candidate.lower() not in _generic_names and len(candidate) > 2:
                logger.debug("Company found via title-line suffix: %r", candidate)
                return candidate
        break

    # Pattern 3: "About {Company}" section header.
    # Require the company name to start with an uppercase letter and NOT be a
    # generic phrase.  "About the Role:" is excluded because "the" is lowercase.
    about_pattern = re.compile(
        r"^\s*about\s+([A-Z][A-Za-z0-9 &.,'-]{1,50}?)(?:\s*[:!]|$)",
        re.MULTILINE,
    )
    for match in about_pattern.finditer(text):
        candidate = match.group(1).strip().rstrip(":")
        if candidate.lower() not in _generic_names and len(candidate) > 2:
            logger.debug("Company found via 'About' pattern: %r", candidate)
            return candidate

    # Pattern 4: "join {Company}" / "at {Company}" cross-referenced with ORG entities.
    _lookahead = r"(?=\s*[,.\n]|\s+(?:we|our|is|are|to|and)\b)"
    inline_pattern = re.compile(
        r"\b(?:at|join|joining|with)\s+([A-Z][A-Za-z0-9 &.,'-]{1,40}?)" + _lookahead,
        re.MULTILINE,
    )
    for match in inline_pattern.finditer(text):
        candidate = match.group(1).strip()
        if candidate.lower() in org_lower and candidate.lower() not in _generic_names:
            logger.debug("Company found via inline pattern + ORG entity: %r", candidate)
            return candidate

    # Fallback: first spaCy ORG entity in the document.
    for ent in entities:
        if ent.lower() in org_lower and ent.lower() not in _generic_names:
            logger.debug("Company fallback to first ORG entity: %r", ent)
            return ent

    logger.debug("No company found")
    return None


def _extract_experience_years(text: str) -> int | None:
    """Extract the minimum years of experience stated in *text*.

    Recognises patterns such as:
    - "5+ years"
    - "3-5 years experience"
    - "minimum 3 years"
    - "at least 4 years"
    - "3 or more years"

    When multiple year values are found, the minimum is returned (most
    conservative interpretation of the requirement).

    Args:
        text: Raw JD text.

    Returns:
        Minimum years as an integer, or ``None`` if no pattern matched.
    """
    patterns: list[re.Pattern[str]] = [
        # "5+ years", "5 + years"
        re.compile(r"\b(\d+)\s*\+\s*years?\b", re.IGNORECASE),
        # "3-5 years", "3 to 5 years"
        re.compile(r"\b(\d+)\s*(?:-|to)\s*\d+\s*years?\b", re.IGNORECASE),
        # "minimum 3 years", "at least 4 years", "minimum of 2 years"
        re.compile(r"\b(?:minimum|at least|min\.?)\s+(?:of\s+)?(\d+)\s*years?\b", re.IGNORECASE),
        # "3 or more years"
        re.compile(r"\b(\d+)\s+or\s+more\s+years?\b", re.IGNORECASE),
        # "X years of experience" (plain)
        re.compile(r"\b(\d+)\s+years?\s+(?:of\s+)?experience\b", re.IGNORECASE),
    ]

    found: list[int] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            try:
                found.append(int(match.group(1)))
            except (ValueError, IndexError):
                pass

    if not found:
        logger.debug("No experience years found")
        return None

    minimum = min(found)
    logger.debug("Experience years found: %r → minimum=%d", found, minimum)
    return minimum


# ---------------------------------------------------------------------------
# Keyword classification
# ---------------------------------------------------------------------------


def _is_soft_skill(keyword: str) -> bool:
    """Return True if *keyword* matches a known soft-skill term."""
    kw_lower = keyword.lower().strip()
    # Direct membership check.
    if kw_lower in _SOFT_SKILL_TERMS:
        return True
    # Substring check: catches "strong communication skills" → "communication".
    return any(soft in kw_lower for soft in _SOFT_SKILL_TERMS)


# High-frequency stop words and filler phrases that YAKE sometimes surfaces.
# These are not technical skills and should be dropped before classification.
_NOISE_PATTERNS: re.Pattern[str] = re.compile(
    r"^(?:"
    # Bullet/list artefacts (leading dash, asterisk, or bracket from markdown)
    r"[-*•]\s*"
    # Pure stop-word phrases
    r"|(?:the|a|an|our|your|their|its|this|that|these|those)\s+"
    # Generic filler verbs/phrases (standalone — must be the whole keyword)
    r"|(?:experience with|experience in|knowledge of|understanding of"
    r"|familiarity with|ability to|strong|proven|solid|good|excellent"
    r"|working knowledge|hands-on|demonstrated|deep)\s*$"
    r")",
    re.IGNORECASE,
)

# Single generic words that are not technical skills on their own.
# Multi-word phrases containing these words may still be valid (e.g. "Git").
_GENERIC_SINGLE_WORDS: frozenset[str] = frozenset(
    {
        "experience",
        "familiarity",
        "knowledge",
        "understanding",
        "proficiency",
        "ability",
        "skills",
        "skill",
        "background",
        "developer",
        "engineer",
        "senior",
        "junior",
        "lead",
        "manager",
        "team",
        "role",
        "position",
        "candidate",
        "applicant",
        "strong",
        "proven",
        "solid",
        "excellent",
        "good",
        "deep",
        "hands-on",
        "demonstrated",
        "working",
        "frontend",
        "backend",  # too generic alone; kept when part of a phrase
    }
)

# Minimum character length for a keyword to be kept (filters single chars, digits).
_MIN_KW_LEN = 2

# Maximum word count for a keyword — very long phrases are usually sentences,
# not skills (YAKE trigrams are fine; longer = noise).
_MAX_KW_WORDS = 5


def _filter_noise(keywords: list[str]) -> list[str]:
    """Remove clearly non-technical keywords from *keywords*.

    Filters out:
    - Keywords shorter than ``_MIN_KW_LEN`` characters
    - Keywords with more than ``_MAX_KW_WORDS`` words
    - Keywords that are purely numeric
    - Keywords matching ``_NOISE_PATTERNS`` (stop-word phrases, filler)
    - Keywords containing newline characters (YAKE artefacts from bullet lists)
    - Single-word keywords that are in ``_GENERIC_SINGLE_WORDS``
    - Phrases that are verb-heavy connectors ("to join", "join our engineering")

    Args:
        keywords: Raw merged keyword list.

    Returns:
        Filtered list preserving original order.
    """
    # Connector phrases that YAKE extracts from narrative sentences.
    _connector_re = re.compile(
        r"^(?:to\s+\w+|join\s+\w+|\w+\s+to\s+\w+|\w+\s+our\s+\w+)",
        re.IGNORECASE,
    )

    result: list[str] = []
    for kw in keywords:
        kw_stripped = kw.strip()

        # Drop empty, too-short, or purely numeric tokens.
        if len(kw_stripped) < _MIN_KW_LEN or kw_stripped.isdigit():
            continue

        # Drop multi-line artefacts (e.g. ")\n- Experience").
        if "\n" in kw_stripped or "\r" in kw_stripped:
            continue

        # Drop overly long phrases (> _MAX_KW_WORDS words).
        words = kw_stripped.split()
        if len(words) > _MAX_KW_WORDS:
            continue

        # Drop noise patterns.
        if _NOISE_PATTERNS.match(kw_stripped):
            continue

        # Drop single generic words that are not technical on their own.
        if len(words) == 1 and kw_stripped.lower() in _GENERIC_SINGLE_WORDS:
            continue

        # Drop connector phrases (narrative glue, not skills).
        if _connector_re.match(kw_stripped):
            continue

        result.append(kw_stripped)

    logger.debug("Noise filter: %d → %d keywords", len(keywords), len(result))
    return result


def _split_into_paragraphs(text: str) -> list[str]:
    """Split *text* into logical paragraphs.

    A paragraph boundary is one or more blank lines.  Single newlines within
    a paragraph are preserved so that bullet-list items stay together with
    their section header.

    Args:
        text: Raw JD text.

    Returns:
        List of non-empty paragraph strings.
    """
    # Split on two or more consecutive newlines (blank line separator).
    paragraphs = re.split(r"\n{2,}", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _classify_keywords(text: str, keywords: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Classify *keywords* into required, preferred, and soft-skill buckets.

    Algorithm:
    1. Split the JD into paragraphs.
    2. Tag each paragraph as "required", "preferred", or "neutral" based on
       the presence of signal markers (see ``_REQUIRED_MARKERS`` /
       ``_PREFERRED_MARKERS``).
    3. For each keyword, find the paragraph(s) it appears in and assign the
       most specific classification (preferred > required > neutral).
    4. Keywords not found in any paragraph default to "required" (conservative
       assumption: if it's in the JD, it's probably wanted).
    5. Soft-skill keywords are always moved to the soft_skills bucket
       regardless of their paragraph classification.

    Args:
        text: Full raw JD text (used for paragraph splitting).
        keywords: Combined keyword list from YAKE + spaCy.

    Returns:
        Three lists: (required, preferred, soft_skills) — may overlap only
        in the sense that a keyword appears in exactly one bucket.
    """
    paragraphs = _split_into_paragraphs(text)

    # Tag each paragraph.
    para_tags: list[str] = []
    for para in paragraphs:
        if _PREFERRED_MARKERS.search(para):
            para_tags.append("preferred")
        elif _REQUIRED_MARKERS.search(para):
            para_tags.append("required")
        else:
            para_tags.append("neutral")

    logger.debug(
        "Paragraph classification: %s",
        {tag: para_tags.count(tag) for tag in ("required", "preferred", "neutral")},
    )

    required: list[str] = []
    preferred: list[str] = []
    soft_skills: list[str] = []

    for kw in keywords:
        # Soft skills are classified independently of paragraph context.
        if _is_soft_skill(kw):
            soft_skills.append(kw)
            continue

        kw_lower = kw.lower()
        # Determine which paragraph(s) contain this keyword.
        kw_tags: list[str] = []
        for para, tag in zip(paragraphs, para_tags):
            if kw_lower in para.lower():
                kw_tags.append(tag)

        # Resolve to a single classification.
        if "preferred" in kw_tags:
            preferred.append(kw)
        elif "required" in kw_tags or "neutral" in kw_tags:
            # Both "required" paragraphs and unclassified paragraphs → required.
            required.append(kw)
        else:
            # Keyword not found in any paragraph (e.g. extracted by YAKE from
            # a very short JD with no paragraph breaks) → default to required.
            required.append(kw)

    logger.debug(
        "Classification result: required=%d, preferred=%d, soft_skills=%d",
        len(required),
        len(preferred),
        len(soft_skills),
    )
    return required, preferred, soft_skills


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_jd(
    jd_text: str,
    synonym_index: dict[str, str] | None = None,
    cv: MasterCV | None = None,
) -> ParsedJD:
    """Parse a raw job description into structured keyword data.

    Runs a multi-stage heuristic pipeline:

    1. Input validation
    2. YAKE keyword extraction
    3. spaCy NER + noun-chunk extraction
    4. Role title and company heuristics
    5. Experience years regex extraction
    6. Keyword deduplication and merging
    7. Paragraph-level required/preferred/soft-skill classification
    8. Synonym normalization

    If ``synonym_index`` is not provided, one is built from the master CV and
    ``synonyms.yaml``.  If ``cv`` is not provided, it is loaded from the
    project config.  Both are optional performance shortcuts when parsing
    multiple JDs in a single session.

    Args:
        jd_text: Raw job description text (pasted or read from file).
        synonym_index: Pre-built synonym index (optional, for performance when
            parsing multiple JDs).
        cv: Pre-loaded master CV (optional).

    Returns:
        ``ParsedJD`` with extracted and classified keywords.

    Raises:
        CVForgeValidationError: If ``jd_text`` is empty or whitespace-only.
    """
    # ------------------------------------------------------------------
    # 1. Input validation
    # ------------------------------------------------------------------
    if not jd_text or not jd_text.strip():
        raise CVForgeValidationError(
            "jd_text must be a non-empty string; received empty or whitespace-only input."
        )

    text = jd_text.strip()
    logger.debug("parse_jd: input length=%d chars", len(text))

    # ------------------------------------------------------------------
    # 2. Build synonym index if not supplied
    # ------------------------------------------------------------------
    if synonym_index is None:
        logger.debug("parse_jd: building synonym index (not pre-supplied)")
        from cvforge.core.yaml_loader import load_master_cv, load_synonyms

        if cv is None:
            cv = load_master_cv()
        synonyms_data = load_synonyms()
        synonym_index = build_synonym_index(synonyms_data, cv.skill_groups)
    elif cv is None:
        # synonym_index was supplied but cv was not — we don't need cv here,
        # it was only needed to build the index.
        pass

    # ------------------------------------------------------------------
    # 3. YAKE keyword extraction
    # ------------------------------------------------------------------
    logger.debug("parse_jd: running YAKE extraction")
    yake_keywords = _extract_keywords_yake(text)

    # ------------------------------------------------------------------
    # 4. spaCy NER + noun-chunk extraction
    # ------------------------------------------------------------------
    logger.debug("parse_jd: running spaCy extraction")
    spacy_entities = _extract_entities_spacy(text)

    # ------------------------------------------------------------------
    # 5. Role title and company
    # ------------------------------------------------------------------
    role = _extract_role_title(text)
    company = _extract_company(text, spacy_entities)

    # ------------------------------------------------------------------
    # 6. Experience years
    # ------------------------------------------------------------------
    experience_years = _extract_experience_years(text)

    # ------------------------------------------------------------------
    # 7. Merge and deduplicate keywords
    #
    # Strategy: YAKE is the primary source (statistically ranked).
    # spaCy entities are appended if not already present (case-insensitive).
    # This avoids double-counting while preserving YAKE's ordering.
    # ------------------------------------------------------------------
    seen_lower: set[str] = {kw.lower() for kw in yake_keywords}
    merged: list[str] = list(yake_keywords)

    for ent in spacy_entities:
        if ent.lower() not in seen_lower:
            # Filter out very short tokens (single chars, numbers) and
            # tokens that are clearly not technical terms.
            if len(ent.strip()) > 1 and not ent.strip().isdigit():
                merged.append(ent)
                seen_lower.add(ent.lower())

    logger.debug("parse_jd: merged keyword pool size=%d", len(merged))

    # ------------------------------------------------------------------
    # 8. Filter noise from the merged pool
    # ------------------------------------------------------------------
    logger.debug("parse_jd: filtering noise")
    merged = _filter_noise(merged)

    # ------------------------------------------------------------------
    # 9. Classify into required / preferred / soft_skills
    # ------------------------------------------------------------------
    logger.debug("parse_jd: classifying keywords")
    raw_required, raw_preferred, raw_soft = _classify_keywords(text, merged)

    # ------------------------------------------------------------------
    # 10. Normalize each bucket via the synonym index
    # ------------------------------------------------------------------
    logger.debug("parse_jd: normalizing keywords")
    norm_required = normalize_keywords(raw_required, synonym_index)
    norm_preferred = normalize_keywords(raw_preferred, synonym_index)
    norm_soft = normalize_keywords(raw_soft, synonym_index)

    # Cross-bucket deduplication: if a term appears in both required and
    # preferred (can happen when the same phrase occurs in both sections),
    # keep it only in required (stronger signal).
    preferred_set = set(norm_required)
    norm_preferred = [kw for kw in norm_preferred if kw not in preferred_set]

    keywords = JDKeywords(
        required=norm_required,
        preferred=norm_preferred,
        soft_skills=norm_soft,
    )

    result = ParsedJD(
        role=role,
        company=company,
        keywords=keywords,
        experience_years=experience_years,
    )

    logger.debug(
        "parse_jd: done — role=%r, company=%r, years=%r, required=%d, preferred=%d, soft_skills=%d",
        result.role,
        result.company,
        result.experience_years,
        len(result.keywords.required),
        len(result.keywords.preferred),
        len(result.keywords.soft_skills),
    )

    return result
