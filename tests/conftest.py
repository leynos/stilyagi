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

from tests.support.codescene_coverage import read_workflows

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from tests.support.workflows import WorkflowDocument

REPOSITORY_ROOT: typ.Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parent.parent
)
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"


@pytest.fixture(scope="session")
def documents() -> dict[str, WorkflowDocument]:
    """Return this repository's workflows, parsed once for the session.

    Returns
    -------
    dict
        File name to parsed document.
    """
    return read_workflows(WORKFLOWS)
