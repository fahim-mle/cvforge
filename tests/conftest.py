"""Shared pytest fixtures for CVForge test suite."""

from pathlib import Path

import pytest

from cvforge.core.normalizer import build_synonym_index
from cvforge.core.yaml_loader import load_master_cv, load_synonyms


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_minimal_cv_path(fixtures_dir: Path) -> Path:
    """Return the path to the minimal valid CV fixture."""
    return fixtures_dir / "valid_minimal_cv.yaml"


@pytest.fixture
def valid_config_path(fixtures_dir: Path) -> Path:
    """Return the path to the valid config fixture."""
    return fixtures_dir / "valid_config.yaml"


@pytest.fixture
def sample_cv_path() -> Path:
    """Return the path to the real sample master CV."""
    return Path(__file__).parent.parent / "data" / "master_cv.yaml"


@pytest.fixture
def sample_synonyms_path() -> Path:
    """Return the path to the real sample synonyms file."""
    return Path(__file__).parent.parent / "data" / "synonyms.yaml"


@pytest.fixture(scope="session")
def synonym_index(monkeypatch_session: pytest.MonkeyPatch) -> dict[str, str]:
    """Build a synonym index from real sample data (master CV + synonyms).

    Uses session scope since it's expensive to build and read-only.
    Requires monkeypatch_session to set env vars for master CV loading.
    """
    # Set test env vars for master CV personal section
    monkeypatch_session.setenv("CVFORGE_NAME", "Test User")
    monkeypatch_session.setenv("CVFORGE_EMAIL", "test@example.com")
    monkeypatch_session.setenv("CVFORGE_PHONE", "0400 000 000")
    monkeypatch_session.setenv("CVFORGE_LOCATION", "Brisbane, AU")
    monkeypatch_session.setenv("CVFORGE_VISA", "Test Visa")
    monkeypatch_session.setenv("CVFORGE_LINKEDIN", "https://linkedin.com/in/test")
    monkeypatch_session.setenv("CVFORGE_GITHUB", "https://github.com/test")

    # Load master CV and synonyms
    data_dir = Path(__file__).parent.parent / "data"
    cv = load_master_cv(data_dir / "master_cv.yaml")
    synonyms = load_synonyms(data_dir / "synonyms.yaml")

    # Build and return index
    return build_synonym_index(synonyms, cv.skill_groups)


@pytest.fixture(scope="session")
def monkeypatch_session() -> pytest.MonkeyPatch:
    """Session-scoped monkeypatch fixture for synonym_index."""
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()
