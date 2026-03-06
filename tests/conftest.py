"""Shared pytest fixtures for CVForge test suite."""

from pathlib import Path

import pytest


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
