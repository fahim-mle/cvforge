"""Custom exception hierarchy for CVForge.

All exceptions raised by the core engine inherit from ``CVForgeError`` so
callers can catch the entire family with a single ``except CVForgeError``
clause, or target specific sub-types for finer-grained handling.
"""

__all__ = [
    "CVForgeError",
    "CVForgeValidationError",
]


class CVForgeError(Exception):
    """Base exception for all CVForge errors."""


class CVForgeValidationError(CVForgeError):
    """Raised when YAML data fails schema validation.

    Wraps Pydantic ``ValidationError`` and YAML parse errors with a
    human-readable message that includes the offending field path and the
    underlying error detail, making it actionable without requiring the caller
    to inspect Pydantic internals.
    """
