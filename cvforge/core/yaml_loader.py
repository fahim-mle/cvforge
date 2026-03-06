"""YAML loader for CVForge master CV and supporting data files.

Responsibilities:
- Load ``cvforge.yaml`` project configuration
- Load and validate ``master_cv.yaml`` against the ``MasterCV`` Pydantic model
- Load ``synonyms.yaml`` synonym mapping

All file paths are handled via ``pathlib.Path``.  Relative paths declared
inside ``cvforge.yaml`` are resolved relative to the config file's parent
directory, so the tool works regardless of the caller's working directory.

Errors surface as:
- ``FileNotFoundError`` — file does not exist at the resolved path
- ``CVForgeValidationError`` — YAML is malformed or fails schema validation
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import dotenv
import yaml
from pydantic import ValidationError

from cvforge.core.exceptions import CVForgeValidationError
from cvforge.core.models import MasterCV

__all__ = [
    "load_config",
    "load_master_cv",
    "load_synonyms",
]

logger = logging.getLogger(__name__)

# Default config file name looked up in the current working directory.
_DEFAULT_CONFIG_NAME = "cvforge.yaml"

# Matches ${VAR_NAME} tokens in YAML string values.
_ENV_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_yaml(path: Path) -> Any:
    """Read and parse a YAML file, raising ``CVForgeValidationError`` on parse failure.

    Args:
        path: Absolute or resolved path to the YAML file.

    Returns:
        Parsed Python object (typically ``dict``).

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        CVForgeValidationError: If the file contains invalid YAML.
    """
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise CVForgeValidationError(f"Failed to parse YAML file '{path}': {exc}") from exc


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ``${VAR_NAME}`` tokens in a parsed YAML structure.

    Only string values are inspected; lists, dicts, and non-string scalars are
    traversed or passed through unchanged.  Resolution uses ``os.environ`` so
    callers must load ``.env`` before invoking this function.

    Args:
        value: Any Python value produced by ``yaml.safe_load``.

    Returns:
        The same structure with all ``${VAR_NAME}`` tokens replaced by their
        environment variable values.

    Raises:
        CVForgeValidationError: If a referenced environment variable is not set.
    """
    if isinstance(value, str):

        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            env_value = os.environ.get(var_name)
            if env_value is None:
                raise CVForgeValidationError(
                    f"Environment variable '{var_name}' is not set. Check your .env file."
                )
            return env_value

        return _ENV_TOKEN_RE.sub(_replace, value)

    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]

    # Non-string scalars (int, float, bool, None) pass through unchanged.
    return value


def _resolve_config_path(config_path: Path | None) -> Path:
    """Return the resolved config file path.

    Falls back to ``cvforge.yaml`` in the current working directory when
    ``config_path`` is ``None``.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
    """
    if config_path is not None:
        resolved = config_path.resolve()
    else:
        resolved = Path.cwd() / _DEFAULT_CONFIG_NAME

    if not resolved.exists():
        raise FileNotFoundError(f"CVForge config file not found: {resolved}")

    return resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load ``cvforge.yaml`` configuration.

    If no path is given, look for ``cvforge.yaml`` in the current working
    directory.

    Args:
        config_path: Explicit path to the config file, or ``None`` to use the
            default location.

    Returns:
        Parsed configuration as a plain ``dict``.

    Raises:
        FileNotFoundError: If the config file does not exist.
        CVForgeValidationError: If the config file contains invalid YAML.
    """
    resolved = _resolve_config_path(config_path)
    logger.debug("Loading CVForge config from: %s", resolved)

    data = _read_yaml(resolved)

    if not isinstance(data, dict):
        raise CVForgeValidationError(
            f"Config file '{resolved}' must be a YAML mapping, got {type(data).__name__}"
        )

    return data


def load_master_cv(cv_path: Path | None = None) -> MasterCV:
    """Load and validate ``master_cv.yaml``.

    If no path is given, the path is read from ``cvforge.yaml`` (resolved
    relative to the config file's parent directory).

    Args:
        cv_path: Explicit path to the master CV YAML file, or ``None`` to
            resolve via the project config.

    Returns:
        A fully validated ``MasterCV`` instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        CVForgeValidationError: If the YAML is malformed or fails schema
            validation.
    """
    if cv_path is None:
        config_path = _resolve_config_path(None)
        config = load_config(config_path)

        raw_cv_path: str = config.get("master_cv", "./data/master_cv.yaml")
        # Resolve relative to the config file's parent so the tool works from
        # any working directory.
        cv_path = (config_path.parent / raw_cv_path).resolve()
    else:
        # When an explicit cv_path is given there is no config_path to derive
        # the project root from, so fall back to the CV file's own parent.
        config_path = cv_path.resolve().parent

    resolved = cv_path.resolve()
    logger.info("Loading master CV from: %s", resolved)

    # Load .env from the project root (config file's parent) if it exists.
    # override=False preserves any variables already set in the shell environment.
    env_file = config_path.parent / ".env"
    if env_file.exists():
        dotenv.load_dotenv(env_file, override=False)
        logger.debug("Loaded .env from: %s", env_file)
    else:
        logger.debug("No .env file found at: %s — relying on shell environment", env_file)

    raw: Any = _read_yaml(resolved)

    if not isinstance(raw, dict):
        raise CVForgeValidationError(
            f"Master CV file '{resolved}' must be a YAML mapping, got {type(raw).__name__}"
        )

    # Resolve ${VAR_NAME} tokens throughout the raw dict before Pydantic sees it.
    raw = _resolve_env_vars(raw)

    try:
        return MasterCV.model_validate(raw)
    except ValidationError as exc:
        # Build a concise, human-readable summary of every validation failure.
        error_lines = []
        for error in exc.errors():
            field_path = " → ".join(str(loc) for loc in error["loc"])
            error_lines.append(f"  [{field_path}] {error['msg']}")

        detail = "\n".join(error_lines)
        raise CVForgeValidationError(
            f"Master CV validation failed for '{resolved}':\n{detail}"
        ) from exc


def load_synonyms(synonyms_path: Path | None = None) -> dict[str, list[str]]:
    """Load ``synonyms.yaml`` canonical-term → aliases mapping.

    If no path is given, the path is read from ``cvforge.yaml`` (resolved
    relative to the config file's parent directory).

    Args:
        synonyms_path: Explicit path to the synonyms YAML file, or ``None``
            to resolve via the project config.

    Returns:
        A ``dict`` mapping each canonical term (``str``) to a list of alias
        strings.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        CVForgeValidationError: If the YAML is malformed or has unexpected
            structure.
    """
    if synonyms_path is None:
        config_path = _resolve_config_path(None)
        config = load_config(config_path)

        raw_syn_path: str = config.get("synonyms", "./data/synonyms.yaml")
        synonyms_path = (config_path.parent / raw_syn_path).resolve()

    resolved = synonyms_path.resolve()
    logger.debug("Loading synonyms from: %s", resolved)

    raw: Any = _read_yaml(resolved)

    if not isinstance(raw, dict):
        raise CVForgeValidationError(
            f"Synonyms file '{resolved}' must be a YAML mapping, got {type(raw).__name__}"
        )

    # Coerce values to list[str] and validate structure.
    result: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise CVForgeValidationError(
                f"Synonyms file '{resolved}': keys must be strings, got {type(key).__name__!r}"
            )
        if not isinstance(value, list):
            raise CVForgeValidationError(
                f"Synonyms file '{resolved}': value for '{key}' must be a list, "
                f"got {type(value).__name__!r}"
            )
        result[key] = [str(alias) for alias in value]

    return result
