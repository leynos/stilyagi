"""Fixtures shared by more than one test module.

The workflow tree is read once for the whole session. Three contract
modules assert over it, and parsing it per module read the same files
three times to produce three identical results. A session-scoped
fixture is also the honest shape: these are readings of a tree that
does not change while the suite runs.

This module also puts ``scripts/`` on the import path, which is what lets the
release scripts be imported by their bare module names. ``scripts/`` is a
namespace package, so importing one of its modules both ways — ``release_assets``
and ``scripts.release_assets`` — would load it twice, and each copy would
define its own ``ReleaseAssetError``. A step that catches one class and misses
the other is exactly the failure this avoids: the modules import each other by
bare name, as scripts elsewhere in that directory do, so the tests must import
them by bare name too. ``scripts/tests/conftest.py`` makes the same choice for
the duplication-gate lane. The path is appended rather than prepended, so the
application's own modules still win on a name collision.
"""

import pathlib
import sys
import typing as typ

import pytest

from tests.support.workflow_files import read_workflows

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from tests.support.workflows import WorkflowDocument

REPOSITORY_ROOT: typ.Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parent.parent
)
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"
SCRIPT_DIRECTORY: typ.Final[pathlib.Path] = REPOSITORY_ROOT / "scripts"

if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.append(str(SCRIPT_DIRECTORY))


@pytest.fixture(scope="session")
def documents() -> dict[str, WorkflowDocument]:
    """Return this repository's workflows, parsed once for the session.

    Returns
    -------
    dict
        File name to parsed document.
    """
    return read_workflows(WORKFLOWS)
