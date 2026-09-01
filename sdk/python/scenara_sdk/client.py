"""Compatibility facade for the split Python SDK client."""

from .client_domains import ScenaraClient
from .client_types import ScenaraError

__all__ = ["ScenaraClient", "ScenaraError"]
