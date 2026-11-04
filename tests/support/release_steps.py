"""Execute a job's checked-in scripts, one process at a time.

A ``run:`` step is a shell script, and several of ``release.yml``'s end in
``exit``. Running them is therefore a matter of giving each its own process,
in workflow order, and stopping at the first failure — exactly what a runner
does. This module owns that, and the ``if:`` reading that decides whether a
step runs at all.

The scripts come from the parsed workflow documents through
``tests/support/release_workflow``, so what runs here is what ships.
"""

import pathlib
import re
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # fixed, repo-owned scripts
import typing as typ

import pytest

from tests.support.errors import ReadingError
from tests.support.release_workflow import (
    READER,
    RELEASE_WORKFLOW,
    github_output,
    step,
    step_script,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The only ``if:`` form the release workflow's jobs use: one step output
#: compared with a quoted literal, as ``steps.pending.outputs.remaining ==
#: 'true'``. Anything else is refused rather than assumed to run.
_GATE = re.compile(
    r"steps\.(?P<step>[\w-]+)\.outputs\.(?P<output>[\w-]+) == '(?P<value>[^']*)'"
)


def bash_available() -> bool:
    """Return whether a ``bash`` interpreter can be found."""
    return shutil.which("bash") is not None


requires_bash = pytest.mark.skipif(
    not bash_available(), reason="bash is not available on this host"
)


def run_bash(
    script: str, workdir: pathlib.Path, *, environ: cabc.Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run one step's script in ``workdir`` and capture its result.

    Parameters
    ----------
    script
        The step's ``run`` text.
    workdir
        The directory to run in; ``PATH`` resolution is inherited.
    environ
        The environment to run with. ``GITHUB_OUTPUT`` and ``GITHUB_ENV``
        must be supplied by the caller, because a step that writes them
        writes files the test then reads.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The completed process, with its captured streams.

    Raises
    ------
    ReadingError
        If no ``bash`` interpreter is available.
    """
    interpreter = shutil.which("bash")
    if interpreter is None:
        msg = "bash is not available on this host"
        raise ReadingError(msg, reader=READER)
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # the step's own script, fixed in the workflow
        [interpreter, "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=workdir,
        env=dict(environ),
        capture_output=True,
        text=True,
        check=False,
    )


def should_run(condition: object, output: pathlib.Path) -> bool:
    """Return whether a step's ``if:`` lets it run, given the outputs so far.

    Parameters
    ----------
    condition
        The step's ``if:`` value, or ``None`` when it declares none.
    output
        The job's ``GITHUB_OUTPUT`` file, holding the outputs written so far.

    Returns
    -------
    bool
        Whether the condition holds. A step without a condition always runs.

    Raises
    ------
    ReadingError
        If the condition is not one this reader understands. Guessing would
        let a step run that GitHub would skip.
    """
    if condition is None:
        return True
    match = _GATE.fullmatch(str(condition))
    if match is None:
        msg = f"unsupported step condition {condition!r}"
        raise ReadingError(msg, reader=READER, path=RELEASE_WORKFLOW)
    return github_output(output).get(match["output"]) == match["value"]


def run_job_steps(
    job: dict[str, object],
    names: cabc.Iterable[str],
    workdir: pathlib.Path,
    *,
    environ: cabc.Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run named steps of one job, in order, as GitHub runs them.

    A step whose ``if:`` does not hold is skipped, and the first failure ends
    the job, as it does on a runner.

    Parameters
    ----------
    job
        The parsed job mapping the steps belong to.
    names
        The steps to consider, in workflow order.
    workdir
        The workspace the job runs in.
    environ
        The job's environment; ``GITHUB_OUTPUT`` must be present.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The first failing step, or the last step to run when all passed. A job
        whose steps were all skipped returns a successful trivial run.
    """
    output = pathlib.Path(environ["GITHUB_OUTPUT"])
    completed = run_bash("true", workdir, environ=environ)
    for name in names:
        if not should_run(step(job, name).get("if"), output):
            continue
        completed = run_bash(step_script(job, name), workdir, environ=environ)
        if completed.returncode != 0:
            break
    return completed


def run_version_check(
    workdir: pathlib.Path,
    *,
    declared: str,
    tag_version: str,
    environ: cabc.Mapping[str, str],
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """Run ``check-version``'s pyproject.toml step for one declared version.

    The step compares the tag-derived version with whatever ``pyproject.toml``
    sits in its working directory, so the test writes one before running the
    checked-in script. The written file is the whole document the script
    reads: only ``[project].version`` is consulted.

    Parameters
    ----------
    workdir
        The directory holding the linked scripts; a ``pyproject.toml`` is
        written into it.
    declared
        The version ``[project].version`` names.
    tag_version
        The ``TAG_VERSION`` the ``check-version`` job derives from the tag.
    environ
        The environment to run with; ``GITHUB_OUTPUT`` must be present.

    Returns
    -------
    tuple[subprocess.CompletedProcess[str], dict[str, str]]
        The completed process and the step outputs it wrote.
    """
    (workdir / "pyproject.toml").write_text(
        f'[project]\nname = "stilyagi"\nversion = "{declared}"\n', encoding="utf-8"
    )
    output = pathlib.Path(environ["GITHUB_OUTPUT"])
    output.unlink(missing_ok=True)
    completed = run_bash(
        "python3 -m scripts.release_version",
        workdir,
        environ={**environ, "TAG_VERSION": tag_version},
    )
    return completed, github_output(output)


__all__ = [
    "bash_available",
    "requires_bash",
    "run_bash",
    "run_job_steps",
    "run_version_check",
    "should_run",
]
