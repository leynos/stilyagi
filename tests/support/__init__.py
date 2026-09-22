"""Private test support helpers for the Stilyagi test suite.

Re-exports the package's exception types, so a caller can catch every
fault these helpers raise without naming the module it happens to live
in.
"""

from tests.support.errors import ReadingError, SupportError

__all__ = ["ReadingError", "SupportError"]
