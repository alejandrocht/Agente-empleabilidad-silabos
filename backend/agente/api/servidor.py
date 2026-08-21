"""Compatibility import for callers that use the package-qualified API path."""

from api.servidor import app

__all__ = ["app"]
