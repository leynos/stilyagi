"""Shared fixture for the package-skeleton test modules.

The fixture is not autouse: this module is loaded as a plugin, which would
make an autouse fixture apply to the whole session. Each package-skeleton test
module opts in with ``pytest.mark.usefixtures``, as the single original module
did through its own autouse fixture.
"""

import typing as typ

import pytest
import stilyagi.engine.extraction as extraction_module

if typ.TYPE_CHECKING:
    import collections.abc as cabc


@pytest.fixture
def reset_extraction_state() -> cabc.Iterator[None]:
    """Reset process-wide extraction adapter state around every test."""
    extraction_module.reset_extraction_state_for_tests()
    yield
    extraction_module.reset_extraction_state_for_tests()
