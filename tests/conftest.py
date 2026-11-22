"""Fixtures shared by more than one test module.

The workflow tree is read once for the whole session. Three contract
modules assert over it, and parsing it per module read the same files
three times to produce three identical results. A session-scoped
fixture is also the honest shape: these are readings of a tree that
does not change while the suite runs.
"""

import pathlib
import typing as typ

import pytest

from tests.support.build_tools_harness import PinWorkspace, write_pins
from tests.support.workflow_files import read_workflows

pytest_plugins = ("tests.support.cache_extraction",)

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from tests.support.workflows import WorkflowDocument

REPOSITORY_ROOT: typ.Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parent.parent
)
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"


@pytest.fixture
def pins(tmp_path: pathlib.Path) -> PinWorkspace:
    """Return fixture pin files naming the pinned channel and mold release.

    Three build-tools contract modules drive the same orchestration against the
    same three pin files, so the fixture is shared rather than restated in each.

    Parameters
    ----------
    tmp_path:
        The per-test directory the three pin files are written beneath.

    Returns
    -------
    PinWorkspace
        The written pin paths, ready to hand the orchestration.
    """
    return write_pins(tmp_path)


@pytest.fixture(scope="session")
def documents() -> dict[str, WorkflowDocument]:
    """Return this repository's workflows, parsed once for the session.

    Returns
    -------
    dict
        File name to parsed document.
    """
    return read_workflows(WORKFLOWS)
