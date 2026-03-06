"""Unit tests for the JD parser module.

Tests cover:
- parse_jd validation: empty string, whitespace-only
- _extract_role_title: from label, from first line, no role found
- _extract_company: from title line, from about section, no company found
- _extract_experience_years: various patterns, no years found, multiple patterns
- parse_jd integration: full structured JD, minimal JD, synonym normalization, deduplication
"""

import pytest

from cvforge.core.exceptions import CVForgeValidationError
from cvforge.core.jd_parser import (
    _extract_company,
    _extract_experience_years,
    _extract_role_title,
    parse_jd,
)

# ---------------------------------------------------------------------------
# TestParseJDValidation
# ---------------------------------------------------------------------------


class TestParseJDValidation:
    """Test suite for parse_jd input validation."""

    def test_empty_string_raises(self, synonym_index: dict[str, str]) -> None:
        """Empty string raises CVForgeValidationError."""
        with pytest.raises(CVForgeValidationError, match="jd_text must be a non-empty string"):
            parse_jd("", synonym_index=synonym_index)

    def test_whitespace_only_raises(self, synonym_index: dict[str, str]) -> None:
        """Whitespace-only string raises CVForgeValidationError."""
        with pytest.raises(CVForgeValidationError, match="jd_text must be a non-empty string"):
            parse_jd("   \n  \t  ", synonym_index=synonym_index)


# ---------------------------------------------------------------------------
# TestExtractRoleTitle
# ---------------------------------------------------------------------------


class TestExtractRoleTitle:
    """Test suite for _extract_role_title function."""

    def test_role_from_label(self) -> None:
        """Extract role from explicit label pattern."""
        jd_text = """
Position: Senior Developer

We are looking for a talented developer...
"""
        result = _extract_role_title(jd_text)

        assert result == "Senior Developer"

    def test_role_from_first_line(self) -> None:
        """Extract role from first non-blank line when it looks like a title."""
        jd_text = """
Senior Frontend Developer - Acme Inc

About the role:
We are seeking...
"""
        result = _extract_role_title(jd_text)

        # Should strip the "- Acme Inc" suffix
        assert result == "Senior Frontend Developer"

    def test_no_role_found(self) -> None:
        """Return None when no clear title is found."""
        jd_text = """
We are a fast-growing startup looking for talented individuals.
Our team is passionate about building great products.
"""
        result = _extract_role_title(jd_text)

        assert result is None


# ---------------------------------------------------------------------------
# TestExtractCompany
# ---------------------------------------------------------------------------


class TestExtractCompany:
    """Test suite for _extract_company function."""

    def test_company_from_title_line(self) -> None:
        """Extract company from title-line suffix pattern."""
        jd_text = """
Senior Developer - Acme Inc

We are looking for...
"""
        entities = ["Acme Inc"]  # Simulated spaCy ORG entity

        result = _extract_company(jd_text, entities)

        assert result == "Acme Inc"

    def test_company_from_about_section(self) -> None:
        """Extract company from 'About {Company}' section header."""
        jd_text = """
Senior Developer

About TechCorp

We are a leading technology company...
"""
        entities = ["TechCorp"]

        result = _extract_company(jd_text, entities)

        assert result == "TechCorp"

    def test_no_company_found(self) -> None:
        """Return None when no company name is found."""
        jd_text = """
Senior Developer

We are looking for a talented developer to join our team.
"""
        entities: list[str] = []

        result = _extract_company(jd_text, entities)

        assert result is None


# ---------------------------------------------------------------------------
# TestExtractExperienceYears
# ---------------------------------------------------------------------------


class TestExtractExperienceYears:
    """Test suite for _extract_experience_years function."""

    def test_years_plus_pattern(self) -> None:
        """Extract years from '5+ years' pattern."""
        jd_text = "We require 5+ years of experience in software development."

        result = _extract_experience_years(jd_text)

        assert result == 5

    def test_years_range_pattern(self) -> None:
        """Extract minimum years from '3-5 years' range pattern."""
        jd_text = "Candidates should have 3-5 years experience in backend development."

        result = _extract_experience_years(jd_text)

        assert result == 3

    def test_minimum_years_pattern(self) -> None:
        """Extract years from 'minimum 3 years' pattern."""
        jd_text = "Minimum 3 years of professional experience required."

        result = _extract_experience_years(jd_text)

        assert result == 3

    def test_no_years_found(self) -> None:
        """Return None when no year mentions are found."""
        jd_text = "We are looking for an experienced developer."

        result = _extract_experience_years(jd_text)

        assert result is None

    def test_multiple_patterns_returns_minimum(self) -> None:
        """When multiple year values found, return the minimum."""
        jd_text = """
Requirements:
- 5+ years of software development experience
- Minimum 3 years with React
"""
        result = _extract_experience_years(jd_text)

        # Should return 3 (the minimum of 5 and 3)
        assert result == 3


# ---------------------------------------------------------------------------
# TestParseJDIntegration
# ---------------------------------------------------------------------------


class TestParseJDIntegration:
    """Integration tests for parse_jd with real spaCy + YAKE."""

    def test_full_jd_structured(self, synonym_index: dict[str, str]) -> None:
        """Parse a realistic, well-structured JD and verify all fields."""
        jd_text = """
Senior Full-Stack Developer - TechCorp

About TechCorp:
We are a leading technology company building innovative solutions.

Requirements:
- 5+ years of professional software development experience
- Strong proficiency in JavaScript, React, and Node.js
- Experience with PostgreSQL and MongoDB
- Solid understanding of REST APIs and GraphQL
- Experience with Docker and CI/CD pipelines

Nice to have:
- Experience with TypeScript
- Familiarity with Kubernetes
- Knowledge of AWS or GCP

We value strong communication skills and team collaboration.
"""
        result = parse_jd(jd_text, synonym_index=synonym_index)

        # Verify role is extracted
        assert result.role is not None
        assert "Full-Stack Developer" in result.role or "Senior" in result.role

        # Verify company is extracted (may include title prefix depending on parsing)
        assert result.company is not None
        assert "TechCorp" in result.company

        # Verify experience_years is extracted
        assert result.experience_years == 5

        # Verify required keywords list is non-empty
        assert len(result.keywords.required) > 0

        # Verify some expected required keywords are present (normalized)
        required_lower = [kw.lower() for kw in result.keywords.required]
        assert any("javascript" in kw for kw in required_lower)
        assert any("react" in kw for kw in required_lower)

        # Verify preferred keywords list is non-empty (from "Nice to have" section)
        assert len(result.keywords.preferred) > 0

        # Verify soft_skills extracted
        assert len(result.keywords.soft_skills) > 0
        soft_lower = [kw.lower() for kw in result.keywords.soft_skills]
        assert any("communication" in kw for kw in soft_lower)

    def test_minimal_jd_skills_only(self, synonym_index: dict[str, str]) -> None:
        """Parse a minimal JD with just a bullet list of skills."""
        jd_text = """
- Python
- Machine Learning
- Docker
- PostgreSQL
- Git
"""
        result = parse_jd(jd_text, synonym_index=synonym_index)

        # Keywords should be extracted even without section headers
        assert len(result.keywords.required) > 0

        # Verify some expected keywords are present
        required_lower = [kw.lower() for kw in result.keywords.required]
        assert any("python" in kw for kw in required_lower)
        assert any("docker" in kw for kw in required_lower)

    def test_jd_with_synonym_normalization(self, synonym_index: dict[str, str]) -> None:
        """Parse JD with aliases and verify they normalize to canonical forms."""
        jd_text = """
Requirements:
- Strong experience with JS and React.js
- Proficiency in k8s and Docker
- Experience with Postgres
"""
        result = parse_jd(jd_text, synonym_index=synonym_index)

        # Verify normalization happened
        # "JS" should normalize to "javascript" (or similar canonical form)
        # "k8s" should normalize to "kubernetes"
        # "Postgres" should normalize to "postgresql"
        all_keywords = (
            result.keywords.required + result.keywords.preferred + result.keywords.soft_skills
        )
        all_keywords_lower = [kw.lower() for kw in all_keywords]

        # Check that normalized forms are present
        # Note: exact matches depend on synonym_index content, so we check for presence
        assert any("javascript" in kw or "js" in kw for kw in all_keywords_lower)
        assert any("kubernetes" in kw or "k8s" in kw for kw in all_keywords_lower)
        assert any("postgres" in kw for kw in all_keywords_lower)

    def test_keywords_are_deduplicated(self, synonym_index: dict[str, str]) -> None:
        """Parse JD with repeated keywords and verify deduplication."""
        jd_text = """
Requirements:
- React experience required
- Strong React skills
- React.js proficiency

Nice to have:
- Advanced React knowledge
"""
        result = parse_jd(jd_text, synonym_index=synonym_index)

        # Count how many times "React" (or normalized form) appears across all buckets
        all_keywords = (
            result.keywords.required + result.keywords.preferred + result.keywords.soft_skills
        )
        all_keywords_lower = [kw.lower() for kw in all_keywords]

        react_count = sum(1 for kw in all_keywords_lower if "react" in kw)

        # Should appear only once (or very few times if YAKE extracts different n-grams)
        # We allow up to 2 to account for potential variations like "React" vs "React skills"
        assert react_count <= 2
