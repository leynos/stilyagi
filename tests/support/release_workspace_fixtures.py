"""The workspace fixture the release publishing contracts share.

A publishing step runs in a workspace holding this repository's ``scripts/``
and a pair of state directories standing in for PyPI and the GitHub Release.
Two contract modules run such steps, so the fixture lives here rather than in
either of them: a module that imported it from the other would couple two
tests that assert different things.

The module is declared as a ``pytest_plugins`` entry by each user, which is
how this repository shares a fixture between contract modules.
"""

import typing as typ

import pytest

from tests.support.release_fakes import fake_release
from tests.support.release_workflow import REPOSITORY_ROOT, link_scripts

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.release_workspace import Workspace


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> Workspace:
    """Return a working directory, its fake destinations and its publish dir.

    Parameters
    ----------
    tmp_path
        The per-test directory the workspace and the fake state are built in.

    Returns
    -------
    Workspace
        The job's working directory, with this repository's ``scripts/``
        linked into it; the scripted destinations; and the ``dist/publish``
        directory the artefact download fills.
    """
    work = tmp_path / "work"
    work.mkdir()
    link_scripts(REPOSITORY_ROOT, work)
    publish = work / "dist" / "publish"
    publish.mkdir(parents=True)
    return work, fake_release(tmp_path), publish


__all__ = ["workspace"]
