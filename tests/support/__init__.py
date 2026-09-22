"""Private test support helpers for the Stilyagi test suite.

Re-exports the package's exception base, so a caller can catch every
fault these helpers raise without naming the module it happens to live
in.
"""

from tests.support.errors import SupportError

__all__ = ["SupportError"]
