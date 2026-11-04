"""Hold the release readings to the refusals their callers depend on.

``tests/support/release_workflow`` and ``tests/support/release_steps`` answer
questions about ``release.yml``: which job, which step, which script, and
whether a step's ``if:`` lets it run. Each answer has a shape a caller cannot
use -- a job the workflow does not declare, a step with no script, a condition
the reader cannot evaluate -- and each of those is a `ReadingError` naming the
reading. A helper that answered with an empty mapping, or skipped a step it did
not understand, would let a contract pass over a workflow it never read.

The real workflow declares every job, step and condition its contracts name, so
none of these paths is reachable from it. They are constructed here, as the
reader cases in ``tests/test_workflow_reader_units.py`` are.
"""

import typing as typ

import pytest

from tests.support import release_steps
from tests.support.errors import ReadingError
from tests.support.release_fakes import fake_release
from tests.support.release_steps import (
    requires_bash,
    run_bash,
    run_job_steps,
    should_run,
)
from tests.support.release_workflow import (
    READER,
    RELEASE_WORKFLOW,
    outputs,
    step,
    step_mappings,
    step_script,
    workflow_job,
)
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


def _refused(reading: cabc.Callable[[], object]) -> ReadingError:
    """Call `reading`, require a refusal, and return it."""
    with pytest.raises(ReadingError) as raised:
        reading()
    assert raised.value.reader == READER, raised.value.reader
    return raised.value


# -- workflow_job ------------------------------------------------------------


def test_a_workflow_declaring_no_jobs_is_refused() -> None:
    """A document with no jobs cannot answer which job a release runs."""
    refused = _refused(lambda: workflow_job(load_workflow("on:\n  push:\n"), "attest"))
    assert str(refused) == f"{RELEASE_WORKFLOW} declares no jobs", refused
    assert refused.path == RELEASE_WORKFLOW, refused.path


@pytest.mark.parametrize(
    ("declared", "why"),
    [
        pytest.param("  b:\n    steps: []\n", "the job is absent", id="absent"),
        pytest.param("  a: not-a-mapping\n", "the job is a scalar", id="scalar"),
    ],
)
def test_a_job_the_workflow_cannot_answer_with_is_refused(
    declared: str, why: str
) -> None:
    """A job that is missing and one that is malformed read the same to a caller."""
    document = load_workflow(f"on:\n  push:\njobs:\n{declared}")
    refused = _refused(lambda: workflow_job(document, "a"))
    assert "declares no job 'a'" in str(refused), f"{why}: {refused}"
    assert refused.path == RELEASE_WORKFLOW, refused.path


# -- step and step_mappings --------------------------------------------------


@pytest.mark.parametrize(
    "read",
    [step_mappings, lambda job: step(job, "a")],
    ids=["step_mappings", "step"],
)
def test_a_steps_field_that_is_not_a_list_is_refused(
    read: cabc.Callable[[dict[str, object]], object],
) -> None:
    """Both step readers share one refusal for a ``steps`` that is not a list."""
    refused = _refused(lambda: read({"steps": "not-a-list"}))
    assert "a job's steps must be a list" in str(refused), refused
    assert refused.path == RELEASE_WORKFLOW, refused.path


def test_a_step_the_job_lacks_is_refused_with_the_names_it_has() -> None:
    """The refusal lists the steps that do exist, so a rename is visible."""
    refused = _refused(lambda: step({"steps": [{"name": "A"}]}, "B"))
    assert "no step named 'B'" in str(refused), refused
    assert "['A']" in str(refused), refused


def test_a_step_with_no_run_script_is_refused() -> None:
    """A step that only uses an action has no shell script to execute."""
    refused = _refused(lambda: step_script({"steps": [{"name": "A"}]}, "A"))
    assert "step 'A' carries no run script" in str(refused), refused
    assert refused.path == RELEASE_WORKFLOW, refused.path


# -- outputs -----------------------------------------------------------------


def test_a_job_without_outputs_declares_none() -> None:
    """The empty mapping is an answer: most jobs hand nothing forward."""
    assert outputs({}) == {}, outputs({})


def test_outputs_that_are_not_a_mapping_are_refused() -> None:
    """A list cannot be read as output names and the expressions producing them."""
    refused = _refused(lambda: outputs({"outputs": ["version"]}))
    assert "a job's outputs must be a mapping" in str(refused), refused
    assert refused.path == RELEASE_WORKFLOW, refused.path


# -- should_run --------------------------------------------------------------


def test_a_step_without_a_condition_always_runs(tmp_path: pathlib.Path) -> None:
    """An absent ``if:`` is not an unsupported one."""
    assert should_run(None, tmp_path / "output") is True, "an absent condition skipped"


def test_a_condition_the_reader_cannot_evaluate_is_refused(
    tmp_path: pathlib.Path,
) -> None:
    """Guessing would run a step that GitHub would skip."""
    refused = _refused(lambda: should_run("always()", tmp_path / "output"))
    assert "unsupported step condition 'always()'" in str(refused), refused
    assert refused.path == RELEASE_WORKFLOW, refused.path


# -- running a job -----------------------------------------------------------


@requires_bash
def test_a_step_whose_condition_does_not_hold_is_skipped(
    tmp_path: pathlib.Path,
) -> None:
    """A skipped step's script must not run, and the next step still does."""
    fake = fake_release(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir()
    job: dict[str, object] = {
        "steps": [
            {
                "name": "Guarded",
                "if": "steps.gate.outputs.ready == 'true'",
                "run": "touch guarded",
            },
            {"name": "Always", "run": "touch always"},
        ]
    }
    completed = run_job_steps(
        job, ["Guarded", "Always"], workdir, environ=fake.environ()
    )
    assert completed.returncode == 0, completed.stderr
    assert not (workdir / "guarded").exists(), "a skipped step ran"
    assert (workdir / "always").exists(), "the step after a skip did not run"


def test_a_host_without_bash_refuses_to_run_a_script(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step that cannot be executed is a fault, not a silent success."""

    def _no_interpreter(_name: str) -> None:
        """Answer every lookup with nothing."""

    monkeypatch.setattr(release_steps.shutil, "which", _no_interpreter)
    refused = _refused(lambda: run_bash("true", tmp_path, environ={}))
    assert str(refused) == "bash is not available on this host", refused
