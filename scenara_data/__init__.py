"""Independent Scenara Data service package.

This package owns dataset/version/intake state for local qualification and can
be deployed as a separate process. It intentionally has no Core database
imports or shared persistence objects.
"""

__version__ = "0.3.0.dev42"

__all__ = ["__version__"]
