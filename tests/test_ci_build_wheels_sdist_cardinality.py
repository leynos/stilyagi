"""Hold the wheel build to producing exactly one source distribution.

A wheel matrix multiplies every artefact it builds by the number of legs, so a
source distribution built inside it would be handed to the publisher four times
over: four names, one of which would win on PyPI and three of which would
collide with it. The build therefore produces the sdist from one designated
leg, and each consumer refuses anything but exactly one.

Two steps enforce the cardinality: ``verify-wheel-install``'s "Require exactly
one sdist" after every artefact has been downloaded into one directory, and
``release.yml``'s ``attest`` job over what it collected, because a publisher
must not sign an ambiguous set either. Both are read from the workflow
documents, so a change to a guard is a change to what this contract runs.

Both are whole steps, run verbatim from the checked-in documents against a
scratch directory laid out the way the steps' own downloads leave it. Nothing
is extracted or retyped: what runs here is what a tag runs.
"""

import typing as typ

import pytest

from tests.support.release_steps import (
    requires_bash,
    run_bash,
)
from tests.support.release_workflow import (
    BUILD_WHEELS_WORKFLOW,
    RELEASE_WORKFLOW,
    REPOSITORY_ROOT,
    step_script,
    workflow_job,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.workflows import WorkflowDocument

WHEEL: typ.Final = "stilyagi-0.2.0-cp314-cp314-manylinux_2_28_x86_64.whl"
SDIST: typ.Final = "stilyagi-0.2.0.tar.gz"
OTHER_SDIST: typ.Final = "stilyagi-0.1.0.tar.gz"
SHELL: typ.Final = {"PATH": "/usr/bin:/bin"}


def _document(name: str) -> WorkflowDocument:
    """Return one workflow document from the repository's workflow directory."""
    return load_workflow((WORKFLOWS_DIRECTORY / name).read_text(encoding="utf-8"))


def _script(name: str, job: str, step: str) -> str:
    """Return one named step's script from a workflow's job."""
    return step_script(workflow_job(_document(name), job), step)


def _populate(directory: pathlib.Path, *names: str) -> None:
    """Write one file per distinct name into an existing directory."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"artefact")


def test_the_verify_job_repeats_the_count_after_downloading() -> None:
    """The consumer does not trust the producer's directory."""
    script = _script(
        BUILD_WHEELS_WORKFLOW, "verify-wheel-install", "Require exactly one sdist"
    )
    assert '"${DIST_DIR}"/*.tar.gz' in script, "expected '\"${DIST_DIR}\"/*.tar.gz' ..."


def test_the_attest_job_counts_what_it_collected() -> None:
    """A publisher attests exactly one sdist, not whatever arrived."""
    script = _script(RELEASE_WORKFLOW, "attest", "Collect release artefacts")
    assert "dist/publish/*.tar.gz" in script, "expected 'dist/publish/*.tar.gz' ..."


@requires_bash
@pytest.mark.parametrize(
    ("names", "expected"),
    [
        pytest.param((SDIST, WHEEL), 0, id="one_sdist"),
        pytest.param((), 1, id="empty"),
        pytest.param((SDIST, OTHER_SDIST), 1, id="two_different_sdists"),
        pytest.param((WHEEL, WHEEL), 1, id="wheels_only"),
    ],
)
def test_the_verify_job_refuses_an_ambiguous_artefact_set(
    names: tuple[str, ...], expected: int, tmp_path: pathlib.Path
) -> None:
    """The consumer repeats the count over the merged download directory."""
    _populate(tmp_path / "dist", *names)
    script = _script(
        BUILD_WHEELS_WORKFLOW, "verify-wheel-install", "Require exactly one sdist"
    )
    completed = run_bash(script, tmp_path, environ={**SHELL, "DIST_DIR": "dist"})
    assert completed.returncode == expected, (names, completed.stderr)


#: Where each download step leaves what it fetched. The wheels arrive one
#: directory per ``wheels-*`` artefact, and the sdist under ``dist/sdist``.
def _download(
    dist: pathlib.Path, *, wheels: tuple[str, ...] = (), sdists: tuple[str, ...] = ()
) -> None:
    """Lay out the two download steps' directories on disk."""
    _populate(dist / "wheels-linux", *wheels)
    _populate(dist / "sdist", *sdists)


@requires_bash
@pytest.mark.parametrize(
    ("wheels", "sdists", "expected"),
    [
        pytest.param((WHEEL, WHEEL), (SDIST,), 0, id="one_sdist"),
        pytest.param((), (), 1, id="empty"),
        pytest.param((), (SDIST, OTHER_SDIST), 1, id="two_different_sdists"),
        pytest.param((WHEEL,), (), 1, id="wheel_but_no_sdist"),
        pytest.param((WHEEL, "other.whl"), (SDIST,), 0, id="every_wheel_kept"),
    ],
)
def test_the_attest_job_collects_every_wheel_and_refuses_an_ambiguous_set(
    wheels: tuple[str, ...],
    sdists: tuple[str, ...],
    expected: int,
    tmp_path: pathlib.Path,
) -> None:
    """Attesting is publishing: the same count holds before a signature.

    The whole step runs, collection loop included, because the loop is what
    decides the set the guard then counts: a guard that passes over a
    collection that dropped a wheel would still attest an incomplete release.
    """
    _download(tmp_path / "dist", wheels=wheels, sdists=sdists)
    script = _script(RELEASE_WORKFLOW, "attest", "Collect release artefacts")
    completed = run_bash(script, tmp_path, environ=SHELL)
    assert completed.returncode == expected, (wheels, sdists, completed.stderr)
    if expected == 0:
        published = sorted(
            path.name for path in (tmp_path / "dist" / "publish").iterdir()
        )
        assert published == sorted({*wheels, *sdists}), published


def test_the_guards_live_in_the_workflows_this_repository_ships() -> None:
    """The documents read above are the checked-in files, not copies."""
    for name in (BUILD_WHEELS_WORKFLOW, RELEASE_WORKFLOW):
        path = REPOSITORY_ROOT / ".github" / "workflows" / name
        assert path.is_file(), path
