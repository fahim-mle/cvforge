"""Unit tests for the keyword normalizer module.

Tests cover:
- build_synonym_index: from synonyms only, from skills only, merged, precedence, case-insensitivity
- normalize_keyword: exact match, case-insensitive, fuzzy match, no match, edge cases
- normalize_keywords: deduplication, order preservation, mixed known/unknown
"""


from cvforge.core.models import Skill, SkillGroup
from cvforge.core.normalizer import build_synonym_index, normalize_keyword, normalize_keywords

# ---------------------------------------------------------------------------
# TestBuildSynonymIndex
# ---------------------------------------------------------------------------


class TestBuildSynonymIndex:
    """Test suite for build_synonym_index function."""

    def test_build_index_from_synonyms_only(self) -> None:
        """Build index from synonyms dict only, verify aliases map to canonical."""
        synonyms = {
            "javascript": ["js", "es6"],
            "python": ["py", "python3"],
        }
        skill_groups: list[SkillGroup] = []

        index = build_synonym_index(synonyms, skill_groups)

        # Verify aliases map to canonical
        assert index["js"] == "javascript"
        assert index["es6"] == "javascript"
        assert index["py"] == "python"
        assert index["python3"] == "python"

        # Verify canonical terms map to themselves
        assert index["javascript"] == "javascript"
        assert index["python"] == "python"

    def test_build_index_from_skills_only(self) -> None:
        """Build index from skill_groups only, verify skill aliases map to skill name."""
        synonyms: dict[str, list[str]] = {}
        skill_groups = [
            SkillGroup(
                group="Frontend",
                skills=[
                    Skill(name="React.js", aliases=["React", "ReactJS"], tags=["frontend"]),
                    Skill(name="TypeScript", aliases=["TS"], tags=["frontend"]),
                ],
            )
        ]

        index = build_synonym_index(synonyms, skill_groups)

        # Verify skill aliases map to skill name
        assert index["react"] == "React.js"
        assert index["reactjs"] == "React.js"
        assert index["ts"] == "TypeScript"

        # Verify skill names map to themselves
        assert index["react.js"] == "React.js"
        assert index["typescript"] == "TypeScript"

    def test_build_index_merged(self) -> None:
        """Build index from both sources, verify combined index size and lookups."""
        synonyms = {
            "javascript": ["js", "es6"],
            "python": ["py"],
        }
        skill_groups = [
            SkillGroup(
                group="Frontend",
                skills=[
                    Skill(name="React.js", aliases=["React", "ReactJS"], tags=["frontend"]),
                ],
            )
        ]

        index = build_synonym_index(synonyms, skill_groups)

        # Verify entries from both sources
        assert index["js"] == "javascript"
        assert index["py"] == "python"
        assert index["react"] == "React.js"
        assert index["reactjs"] == "React.js"

        # Verify canonical terms from both sources
        assert index["javascript"] == "javascript"
        assert index["python"] == "python"
        assert index["react.js"] == "React.js"

        # Verify total size (all aliases + canonical terms, lowercased)
        # synonyms: javascript, js, es6, python, py = 5
        # skills: react.js, react, reactjs = 3
        # Total = 8
        assert len(index) == 8

    def test_build_index_synonyms_take_precedence(self) -> None:
        """When same alias exists in both sources, synonyms.yaml wins."""
        synonyms = {
            "javascript": ["js"],
        }
        skill_groups = [
            SkillGroup(
                group="Backend",
                skills=[
                    Skill(name="Java Server", aliases=["js"], tags=["backend"]),
                ],
            )
        ]

        index = build_synonym_index(synonyms, skill_groups)

        # synonyms.yaml is processed first, so "js" maps to "javascript"
        assert index["js"] == "javascript"

    def test_build_index_case_insensitive_keys(self) -> None:
        """All index keys are lowercased."""
        synonyms = {
            "JavaScript": ["JS", "Es6"],
        }
        skill_groups = [
            SkillGroup(
                group="Frontend",
                skills=[
                    Skill(name="React.js", aliases=["React", "REACTJS"], tags=["frontend"]),
                ],
            )
        ]

        index = build_synonym_index(synonyms, skill_groups)

        # All keys are lowercase
        assert "js" in index
        assert "es6" in index
        assert "react" in index
        assert "reactjs" in index

        # Original casing is NOT in keys
        assert "JS" not in index
        assert "Es6" not in index
        assert "React" not in index
        assert "REACTJS" not in index

    def test_build_index_canonical_maps_to_itself(self) -> None:
        """Canonical terms map to themselves in the index."""
        synonyms = {
            "javascript": ["js"],
        }
        skill_groups = [
            SkillGroup(
                group="Frontend",
                skills=[
                    Skill(name="React.js", aliases=["React"], tags=["frontend"]),
                ],
            )
        ]

        index = build_synonym_index(synonyms, skill_groups)

        # Canonical terms map to themselves (lowercased key → original value)
        assert index["javascript"] == "javascript"
        assert index["react.js"] == "React.js"


# ---------------------------------------------------------------------------
# TestNormalizeKeyword
# ---------------------------------------------------------------------------


class TestNormalizeKeyword:
    """Test suite for normalize_keyword function."""

    def test_exact_match(self) -> None:
        """Exact alias match returns canonical form."""
        index = {"js": "javascript", "javascript": "javascript"}

        result = normalize_keyword("js", index)

        assert result == "javascript"

    def test_exact_match_case_insensitive(self) -> None:
        """Mixed-case keywords match lowercased index keys."""
        index = {"js": "javascript", "javascript": "javascript"}

        assert normalize_keyword("JS", index) == "javascript"
        assert normalize_keyword("Js", index) == "javascript"
        assert normalize_keyword("jS", index) == "javascript"

    def test_fuzzy_match_above_threshold(self) -> None:
        """Typo with high similarity score matches via fuzzy search."""
        index = {"typescript": "typescript"}

        # "Typscript" is a common typo (missing 'e')
        result = normalize_keyword("Typscript", index, fuzzy_threshold=85)

        assert result == "typescript"

    def test_fuzzy_match_below_threshold(self) -> None:
        """Keyword with low similarity score returns unchanged."""
        index = {"typescript": "typescript", "javascript": "javascript"}

        # "xyz" has no similarity to any index key
        result = normalize_keyword("xyz", index, fuzzy_threshold=95)

        assert result == "xyz"

    def test_no_match_returns_original(self) -> None:
        """Completely unknown term returns unchanged."""
        index = {"javascript": "javascript", "python": "python"}

        result = normalize_keyword("cobol", index)

        assert result == "cobol"

    def test_empty_keyword(self) -> None:
        """Empty string returns empty string."""
        index = {"javascript": "javascript"}

        result = normalize_keyword("", index)

        assert result == ""

    def test_empty_index(self) -> None:
        """Any keyword with empty index returns unchanged."""
        index: dict[str, str] = {}

        result = normalize_keyword("javascript", index)

        assert result == "javascript"

    def test_already_canonical(self) -> None:
        """Canonical term returns itself."""
        index = {"javascript": "javascript", "js": "javascript"}

        result = normalize_keyword("javascript", index)

        assert result == "javascript"


# ---------------------------------------------------------------------------
# TestNormalizeKeywords
# ---------------------------------------------------------------------------


class TestNormalizeKeywords:
    """Test suite for normalize_keywords function."""

    def test_deduplication_after_normalization(self) -> None:
        """Multiple surface forms of same term deduplicate to one canonical form."""
        index = {"js": "javascript", "javascript": "javascript"}

        result = normalize_keywords(["js", "javascript", "JS"], index)

        # All three normalize to "javascript", deduplicated to one
        assert result == ["javascript"]

    def test_preserves_first_seen_order(self) -> None:
        """Order of first occurrence is preserved."""
        index = {
            "js": "javascript",
            "javascript": "javascript",
            "py": "python",
            "python": "python",
            "react": "react",
        }

        result = normalize_keywords(["py", "js", "react", "javascript"], index)

        # "javascript" appears second (via "js"), so it's second in output
        # "javascript" (fourth) is a duplicate, so it's dropped
        assert result == ["python", "javascript", "react"]

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        index = {"javascript": "javascript"}

        result = normalize_keywords([], index)

        assert result == []

    def test_mixed_known_and_unknown(self) -> None:
        """Some keywords normalize, some don't, all present in output."""
        index = {"js": "javascript", "javascript": "javascript"}

        result = normalize_keywords(["js", "cobol", "fortran"], index)

        # "js" normalizes to "javascript", others pass through
        assert result == ["javascript", "cobol", "fortran"]
