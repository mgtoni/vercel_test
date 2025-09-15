"""API package for the serverless function entrypoint.

This package exists so that `api.index` can import internal modules using
relative imports (e.g., `from .utils.crypto_utils import ...`).

No runtime side-effects here on import.
"""

__all__ = []

