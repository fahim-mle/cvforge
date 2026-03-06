"""Unit tests for the YAML loader module.

Tests cover:
- Config loading (valid, missing, invalid YAML, non-dict root)
- Master CV loading (valid, minimal, missing fields, extra fields, syntax errors)
- Synonyms loading (valid, missing, non-list values)
- Field validation (whitespace stripping, variant_only, show_for, summary_base)
"""

from pathlib import Path

import pytest

from cvforge.core.exceptions import CVForgeValidationError
from cvforge.core.yaml_loader import load_config, load_master_cv, load_synonyms

# ---------------------------------------------------------------------------
# TestLoadConfig
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Test suite for load_config function."""

    def test_load_config_from_explicit_path(self, valid_config_path: Path) -> None:
        """Load valid config from explicit path and verify structure."""
        config = load_config(valid_config_path)

        assert isinstance(config, dict)
        assert "master_cv" in config
        assert "synonyms" in config
        assert config["master_cv"] == "./valid_minimal_cv.yaml"
        assert config["synonyms"] == "./valid_synonyms.yaml"

    def test_load_config_missing_file(self, fixtures_dir: Path) -> None:
        """Raise FileNotFoundError when config file does not exist."""
        nonexistent = fixtures_dir / "does_not_exist.yaml"

        with pytest.raises(FileNotFoundError, match="CVForge config file not found"):
            load_config(nonexistent)

    def test_load_config_invalid_yaml(self, fixtures_dir: Path) -> None:
        """Raise CVForgeValidationError when config contains invalid YAML syntax."""
        invalid_yaml = fixtures_dir / "invalid_yaml_syntax.yaml"

        with pytest.raises(CVForgeValidationError, match="Failed to parse YAML file"):
            load_config(invalid_yaml)

    def test_load_config_non_dict_root(self, fixtures_dir: Path) -> None:
        """Raise CVForgeValidationError when config root is not a dict."""
        non_dict_config = fixtures_dir / "invalid_config_non_dict.yaml"

        with pytest.raises(CVForgeValidationError, match="must be a YAML mapping, got list"):
            load_config(non_dict_config)


# ---------------------------------------------------------------------------
# TestLoadMasterCV
# ---------------------------------------------------------------------------


class TestLoadMasterCV:
    """Test suite for load_master_cv function."""

    def test_load_master_cv_from_explicit_path(self, sample_cv_path: Path) -> None:
        """Load sample CV and verify field counts match expected structure."""
        cv = load_master_cv(sample_cv_path)

        # Verify counts based on data/master_cv.yaml
        assert len(cv.experience) == 5
        assert len(cv.skill_groups) == 7
        assert len(cv.role_variants) == 3
        assert len(cv.education) == 2
        assert len(cv.certifications) == 1

    def test_load_master_cv_minimal(self, valid_minimal_cv_path: Path) -> None:
        """Load minimal fixture and verify basic structure."""
        cv = load_master_cv(valid_minimal_cv_path)

        assert cv.personal.name == "Test User"
        assert len(cv.role_variants) == 1
        assert "software_engineer" in cv.role_variants
        assert len(cv.skill_groups) == 1
        assert cv.skill_groups[0].group == "Backend"
        assert len(cv.skill_groups[0].skills) == 1
        assert len(cv.experience) == 1
        assert len(cv.education) == 1
        assert len(cv.certifications) == 0

    def test_load_master_cv_personal_fields(self, sample_cv_path: Path, monkeypatch) -> None:
        """Verify all personal fields are populated and stripped."""
        # Set test env vars to avoid depending on real .env values
        monkeypatch.setenv("CVFORGE_NAME", "Alex Johnson")
        monkeypatch.setenv("CVFORGE_EMAIL", "alex.johnson.dev@example.com")
        monkeypatch.setenv("CVFORGE_PHONE", "0400 000 000")
        monkeypatch.setenv("CVFORGE_LOCATION", "Brisbane, Queensland")
        monkeypatch.setenv("CVFORGE_VISA", "485 Graduate Temporary (Full Working Rights)")
        monkeypatch.setenv("CVFORGE_LINKEDIN", "https://linkedin.com/in/alexjohnson-dev")
        monkeypatch.setenv("CVFORGE_GITHUB", "https://github.com/alexjohnson-dev")

        cv = load_master_cv(sample_cv_path)

        assert cv.personal.name == "Alex Johnson"
        assert cv.personal.email == "alex.johnson.dev@example.com"
        assert cv.personal.phone == "0400 000 000"
        assert cv.personal.location == "Brisbane, Queensland"
        assert cv.personal.visa == "485 Graduate Temporary (Full Working Rights)"
        assert cv.personal.linkedin == "https://linkedin.com/in/alexjohnson-dev"
        assert cv.personal.github == "https://github.com/alexjohnson-dev"

        # Verify no leading/trailing whitespace
        assert cv.personal.name.strip() == cv.personal.name
        assert cv.personal.email.strip() == cv.personal.email

    def test_load_master_cv_role_variants(self, sample_cv_path: Path) -> None:
        """Verify variant keys, titles, and skill_priority lists."""
        cv = load_master_cv(sample_cv_path)

        assert "software_engineer" in cv.role_variants
        assert "ml_engineer" in cv.role_variants
        assert "data_engineer" in cv.role_variants

        se = cv.role_variants["software_engineer"]
        assert se.title == "Software Engineer"
        assert se.summary is not None
        assert "Full-stack Software Engineer" in se.summary
        assert se.skill_priority == ["frontend", "backend", "devops", "data-science"]

        ml = cv.role_variants["ml_engineer"]
        assert ml.title == "Machine Learning Engineer"
        assert ml.skill_priority == [
            "ml",
            "data-engineering",
            "analytics",
            "devops",
            "frontend",
        ]

    def test_load_master_cv_variant_only_filtering(self, sample_cv_path: Path) -> None:
        """Verify highlights with variant_only are loaded correctly."""
        cv = load_master_cv(sample_cv_path)

        # Find QCIF experience (first entry)
        qcif = cv.experience[0]
        assert qcif.company == "Queensland Cyber Infrastructure Federation (QCIF)"

        # Find highlight with variant_only
        variant_only_highlights = [h for h in qcif.highlights if h.variant_only is not None]
        assert len(variant_only_highlights) > 0

        # Check the automation highlight
        automation_highlight = next((h for h in qcif.highlights if "shell scripts" in h.text), None)
        assert automation_highlight is not None
        assert automation_highlight.variant_only == ["software_engineer"]

    def test_load_master_cv_show_for(self, sample_cv_path: Path) -> None:
        """Verify experience with show_for is loaded with the field set."""
        cv = load_master_cv(sample_cv_path)

        # Find Bluebeak.ai experience (last entry)
        bluebeak = next((exp for exp in cv.experience if exp.company == "Bluebeak.ai"), None)
        assert bluebeak is not None
        assert bluebeak.show_for == ["ml_engineer", "data_engineer"]

    def test_load_master_cv_summary_base(self, sample_cv_path: Path) -> None:
        """Verify data_engineer variant has summary_base and no summary."""
        cv = load_master_cv(sample_cv_path)

        de = cv.role_variants["data_engineer"]
        assert de.summary_base == "ml_engineer"
        assert de.summary is None

    def test_load_master_cv_missing_file(self, fixtures_dir: Path) -> None:
        """Raise FileNotFoundError when CV file does not exist."""
        nonexistent = fixtures_dir / "does_not_exist.yaml"

        with pytest.raises(FileNotFoundError, match="YAML file not found"):
            load_master_cv(nonexistent)

    def test_load_master_cv_missing_personal(self, fixtures_dir: Path) -> None:
        """Raise CVForgeValidationError when personal section is missing."""
        invalid_cv = fixtures_dir / "invalid_missing_personal.yaml"

        with pytest.raises(CVForgeValidationError, match="Master CV validation failed"):
            load_master_cv(invalid_cv)

    def test_load_master_cv_extra_field(self, fixtures_dir: Path) -> None:
        """Raise CVForgeValidationError when extra field is present (extra='forbid')."""
        invalid_cv = fixtures_dir / "invalid_extra_field.yaml"

        with pytest.raises(CVForgeValidationError, match="Master CV validation failed"):
            load_master_cv(invalid_cv)

    def test_load_master_cv_invalid_yaml_syntax(self, fixtures_dir: Path) -> None:
        """Raise CVForgeValidationError when YAML syntax is invalid."""
        invalid_yaml = fixtures_dir / "invalid_yaml_syntax.yaml"

        with pytest.raises(CVForgeValidationError, match="Failed to parse YAML file"):
            load_master_cv(invalid_yaml)

    def test_load_master_cv_whitespace_stripping(self, tmp_path: Path) -> None:
        """Verify that string fields with padding are stripped."""
        cv_with_padding = tmp_path / "cv_with_padding.yaml"
        cv_with_padding.write_text(
            """
personal:
  name: "  Padded Name  "
  email: "  padded@example.com  "
  phone: "  0400 000 000  "
  location: "  Brisbane, AU  "
  visa: "  Citizen  "
  linkedin: "  https://linkedin.com/in/test  "
  github: "  https://github.com/test  "

role_variants:
  software_engineer:
    title: "  Software Engineer  "
    summary: "  A padded summary.  "
    skill_priority: ["backend"]

skill_groups:
  - group: "  Backend  "
    skills:
      - name: "  Python  "
        tags: ["  backend  "]

experience:
  - company: "  Test Company  "
    location: "  Brisbane, AU  "
    start: "  2024-01  "
    end: "  2024-12  "
    role_variants:
      software_engineer: "  Software Engineer  "
    tags: ["  backend  "]
    highlights:
      - text: "  Built a test application  "
        tags: ["  backend  "]

education:
  - degree: "  Bachelor of CS  "
    institution: "  Test University  "
    location: "  Brisbane, AU  "
    end: "  2023-12  "
    tags: ["  cs  "]
""",
            encoding="utf-8",
        )

        cv = load_master_cv(cv_with_padding)

        # Verify all strings are stripped
        assert cv.personal.name == "Padded Name"
        assert cv.personal.email == "padded@example.com"
        assert cv.personal.phone == "0400 000 000"
        assert cv.role_variants["software_engineer"].title == "Software Engineer"
        assert cv.role_variants["software_engineer"].summary == "A padded summary."
        assert cv.skill_groups[0].group == "Backend"
        assert cv.skill_groups[0].skills[0].name == "Python"
        assert cv.skill_groups[0].skills[0].tags == ["backend"]
        assert cv.experience[0].company == "Test Company"
        assert cv.experience[0].location == "Brisbane, AU"
        assert cv.experience[0].highlights[0].text == "Built a test application"
        assert cv.education[0].degree == "Bachelor of CS"


# ---------------------------------------------------------------------------
# TestLoadSynonyms
# ---------------------------------------------------------------------------


class TestLoadSynonyms:
    """Test suite for load_synonyms function."""

    def test_load_synonyms_from_explicit_path(self, sample_synonyms_path: Path) -> None:
        """Load sample synonyms and verify count and known entries."""
        synonyms = load_synonyms(sample_synonyms_path)

        assert isinstance(synonyms, dict)
        # data/synonyms.yaml has 30 entries (excluding comments)
        assert len(synonyms) == 30

        # Verify known entries
        assert "javascript" in synonyms
        assert synonyms["javascript"] == [
            "js",
            "es6",
            "es6+",
            "ecmascript",
            "vanilla js",
        ]

        assert "python" in synonyms
        assert synonyms["python"] == ["python3", "py"]

        assert "machine_learning" in synonyms
        assert synonyms["machine_learning"] == ["ml", "machine-learning", "ml/ai"]

    def test_load_synonyms_missing_file(self, fixtures_dir: Path) -> None:
        """Raise FileNotFoundError when synonyms file does not exist."""
        nonexistent = fixtures_dir / "does_not_exist.yaml"

        with pytest.raises(FileNotFoundError, match="YAML file not found"):
            load_synonyms(nonexistent)

    def test_load_synonyms_non_list_value(self, fixtures_dir: Path) -> None:
        """Raise CVForgeValidationError when a synonym value is not a list."""
        invalid_synonyms = fixtures_dir / "invalid_synonyms_non_list.yaml"

        with pytest.raises(CVForgeValidationError, match="value for 'python' must be a list"):
            load_synonyms(invalid_synonyms)

    def test_load_synonyms_values_are_string_lists(self, sample_synonyms_path: Path) -> None:
        """Verify all synonym values are list[str]."""
        synonyms = load_synonyms(sample_synonyms_path)

        for key, value in synonyms.items():
            assert isinstance(key, str), f"Key {key!r} is not a string"
            assert isinstance(value, list), f"Value for {key!r} is not a list"
            assert all(isinstance(alias, str) for alias in value), (
                f"Not all aliases for {key!r} are strings"
            )


# ---------------------------------------------------------------------------
# TestEnvVarResolution
# ---------------------------------------------------------------------------


class TestEnvVarResolution:
    """Test suite for environment variable resolution in YAML files."""

    def test_resolve_env_vars_in_master_cv(self, sample_cv_path: Path, monkeypatch) -> None:
        """Verify env vars are resolved in master_cv.yaml personal section."""
        # Set test env vars
        monkeypatch.setenv("CVFORGE_NAME", "Test Name")
        monkeypatch.setenv("CVFORGE_EMAIL", "test@example.com")
        monkeypatch.setenv("CVFORGE_PHONE", "1234567890")
        monkeypatch.setenv("CVFORGE_LOCATION", "Test City")
        monkeypatch.setenv("CVFORGE_VISA", "Test Visa")
        monkeypatch.setenv("CVFORGE_LINKEDIN", "https://linkedin.com/in/test")
        monkeypatch.setenv("CVFORGE_GITHUB", "https://github.com/test")

        cv = load_master_cv(sample_cv_path)

        # Verify all personal fields match the monkeypatched values
        assert cv.personal.name == "Test Name"
        assert cv.personal.email == "test@example.com"
        assert cv.personal.phone == "1234567890"
        assert cv.personal.location == "Test City"
        assert cv.personal.visa == "Test Visa"
        assert cv.personal.linkedin == "https://linkedin.com/in/test"
        assert cv.personal.github == "https://github.com/test"

    def test_missing_env_var_raises(self, tmp_path: Path) -> None:
        """Verify CVForgeValidationError is raised when env var is missing."""
        cv_with_missing_var = tmp_path / "cv_missing_var.yaml"
        cv_with_missing_var.write_text(
            """
personal:
  name: "${MISSING_VAR}"
  email: "test@example.com"
  phone: "0400 000 000"
  location: "Brisbane, AU"
  visa: "Citizen"
  linkedin: "https://linkedin.com/in/test"
  github: "https://github.com/test"

role_variants:
  software_engineer:
    title: "Software Engineer"
    summary: "Test summary"
    skill_priority: ["backend"]

skill_groups:
  - group: "Backend"
    skills:
      - name: "Python"
        aliases: []
        tags: ["backend"]

experience:
  - company: "Test Company"
    location: "Brisbane, AU"
    start: "2024-01"
    end: "2024-12"
    role_variants:
      software_engineer: "Software Engineer"
    tags: ["backend"]
    highlights:
      - text: "Built a test application"
        tags: ["backend"]

education:
  - degree: "Bachelor of CS"
    institution: "Test University"
    location: "Brisbane, AU"
    end: "2023-12"
    tags: ["cs"]
""",
            encoding="utf-8",
        )

        with pytest.raises(
            CVForgeValidationError, match="Environment variable 'MISSING_VAR' is not set"
        ):
            load_master_cv(cv_with_missing_var)

    def test_non_string_values_pass_through(self, tmp_path: Path, monkeypatch) -> None:
        """Verify non-string values (ints, bools) are unchanged by env var resolution."""
        monkeypatch.setenv("TEST_NAME", "Test User")

        cv_with_mixed_types = tmp_path / "cv_mixed_types.yaml"
        cv_with_mixed_types.write_text(
            """
personal:
  name: "${TEST_NAME}"
  email: "test@example.com"
  phone: "0400 000 000"
  location: "Brisbane, AU"
  visa: "Citizen"
  linkedin: "https://linkedin.com/in/test"
  github: "https://github.com/test"

role_variants:
  software_engineer:
    title: "Software Engineer"
    summary: "Test summary"
    skill_priority: ["backend"]

skill_groups:
  - group: "Backend"
    skills:
      - name: "Python"
        aliases: []
        tags: ["backend"]

experience:
  - company: "Test Company"
    location: "Brisbane, AU"
    start: "2024-01"
    end: "2024-12"
    role_variants:
      software_engineer: "Software Engineer"
    tags: ["backend"]
    highlights:
      - text: "Built a test application"
        tags: ["backend"]

education:
  - degree: "Bachelor of CS"
    institution: "Test University"
    location: "Brisbane, AU"
    end: "2023-12"
    tags: ["cs"]
""",
            encoding="utf-8",
        )

        cv = load_master_cv(cv_with_mixed_types)

        # Verify env var was resolved
        assert cv.personal.name == "Test User"

        # Verify non-string values remain unchanged
        assert isinstance(cv.role_variants["software_engineer"].skill_priority, list)
        assert cv.role_variants["software_engineer"].skill_priority == ["backend"]

    def test_env_vars_not_resolved_in_non_personal_sections(
        self, sample_cv_path: Path, monkeypatch
    ) -> None:
        """Verify experience/skills data loads correctly regardless of env vars."""
        # Set test env vars for personal section
        monkeypatch.setenv("CVFORGE_NAME", "Test Name")
        monkeypatch.setenv("CVFORGE_EMAIL", "test@example.com")
        monkeypatch.setenv("CVFORGE_PHONE", "1234567890")
        monkeypatch.setenv("CVFORGE_LOCATION", "Test City")
        monkeypatch.setenv("CVFORGE_VISA", "Test Visa")
        monkeypatch.setenv("CVFORGE_LINKEDIN", "https://linkedin.com/in/test")
        monkeypatch.setenv("CVFORGE_GITHUB", "https://github.com/test")

        cv = load_master_cv(sample_cv_path)

        # Verify experience data loads correctly (no tokens in these sections)
        assert len(cv.experience) == 5
        assert cv.experience[0].company == "Queensland Cyber Infrastructure Federation (QCIF)"

        # Verify skills data loads correctly
        assert len(cv.skill_groups) == 7
        assert cv.skill_groups[0].group == "Programming & Query Languages"

        # Verify role variants load correctly
        assert len(cv.role_variants) == 3
        assert "software_engineer" in cv.role_variants
