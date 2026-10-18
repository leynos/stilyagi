"""Derive which workflow jobs reach the build-tools preflight, and read their wiring.

A coverage build excludes mold from its compiler flags and still executes
tests that drive Make targets, which run the build-tools preflight. Netsuke's
coverage publisher failed for exactly that reason after the standard landed:
the install lived somewhere the publisher never ran. The rule these readings
serve is therefore derived from reachability rather than from job names: every
Linux job that reaches the suite or the preflight, through the coverage action,
a direct `cargo nextest run`, `pytest`, or a Make goal whose evaluated recipe
reaches either, installs the pinned tools in its own unconditional step before
the first step that reaches them.

A reading that finds no such job, or cannot place a runner, is reported rather
than passed, because a refusal over an empty set is satisfied by any repository.
"""

import dataclasses as dc
import re
import typing as typ

from tests.support.build_standard import (
    PROBE_CHECK,
    PROBE_UV,
    dry_run,
    read_invocations,
)
from tests.support.workflow_files import WorkflowReadingError
from tests.support.workflows import workflow_jobs

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.workflows import WorkflowDocument

READER: typ.Final = "build_tools_wiring"
INSTALL_TARGET: typ.Final = "install-build-tools"
COVERAGE_ACTION: typ.Final = "generate-coverage@"

_MAKE_INVOCATION: typ.Final = re.compile(r"(?:^|[\s;&|(])make\b([^\n;&|)]*)")
_SUITE_COMMAND: typ.Final = re.compile(
    r"\bcargo\s+(?:nextest\s+run|llvm-cov)\b|(?<![\w-])pytest\b"
)
_SWALLOWED_FAILURE: typ.Final = re.compile(r"\|\|\s*(?:true|:|exit\s+0)\b")
_QUOTED: typ.Final = re.compile(r"'([^']*)'")
_MATRIX_REFERENCE: typ.Final = re.compile(r"^\$\{\{\s*matrix\.([\w-]+)\s*\}\}$")
_LINUX_PREFIXES: typ.Final = ("ubuntu", "ubicloud")
_OTHER_PREFIXES: typ.Final = ("macos", "windows")


@dc.dataclass(frozen=True, slots=True)
class JobReading:
    """A Linux-capable job that reaches the suite or the preflight."""

    workflow: str
    job: str
    reaching_steps: tuple[int, ...]
    install_steps: tuple[int, ...]
    faults: tuple[str, ...]


def make_goals(run_text: str) -> list[str]:
    """Return the Make goals a `run:` script invokes, in order.

    Options (`-j4`, `-C dir`) and variable assignments (`CARGO=x`) are not
    goals. `$(MAKE)`-style recursion is a recipe's concern, not a step's.

    Returns
    -------
    list[str]
        The goals, in the order the script names them.
    """
    words = (
        word
        for match in _MAKE_INVOCATION.finditer(run_text)
        for word in match.group(1).split()
    )
    return [word for word in words if not word.startswith("-") and "=" not in word]


class MakeReach:
    """What each Make goal's evaluated recipe reaches, asked of Make itself.

    The dependency graph is not parsed from the Makefile's text: `make
    --dry-run --always-make` evaluates prerequisites, recursion and
    conditionals as Make does, so an indirect prerequisite is found where a
    text reading would miss it.
    """

    def __init__(self, probe_dir: pathlib.Path) -> None:
        """Remember the directory of probe executables Make resolves."""
        self._probe_dir = probe_dir
        self._cache: dict[str, tuple[bool, bool]] = {}

    def _evaluate(self, goal: str) -> tuple[bool, bool]:
        """Return whether `goal` reaches the preflight, and whether the suite."""
        if goal not in self._cache:
            output = dry_run(goal, self._probe_dir)
            tools = (PROBE_CHECK, PROBE_UV, "probe-python", "probe-cargo")
            invocations = read_invocations(output, tools)
            preflight = any(inv.program == PROBE_CHECK for inv in invocations)
            suite = bool(_SUITE_COMMAND.search(output)) or any(
                inv.program == "probe-cargo" and inv.has_args("nextest", "run")
                for inv in invocations
            )
            self._cache[goal] = (preflight, suite)
        return self._cache[goal]

    def reaches_preflight(self, goal: str) -> bool:
        """Return whether `goal` runs the build-tools preflight."""
        return self._evaluate(goal)[0]

    def reaches_suite(self, goal: str) -> bool:
        """Return whether `goal` runs a test suite."""
        return self._evaluate(goal)[1]


def _matrix_values(job: dict[str, object], key: str) -> list[str]:
    """Return every value a job's matrix gives `key`, `include` entries too."""
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if not isinstance(matrix, dict):
        return []
    values = [v for v in _as_list(matrix.get(key)) if isinstance(v, str)]
    includes = matrix.get("include")
    entries = includes if isinstance(includes, list) else []
    values.extend(
        entry[key]
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get(key), str)
    )
    return values


def _as_list(value: object) -> list[object]:
    """Return a scalar or list value as a list."""
    return value if isinstance(value, list) else [value]


def _labels_of(value: object, job: dict[str, object]) -> list[str]:
    """Return every runner label one `runs-on` entry can select."""
    if not isinstance(value, str):
        return []
    reference = _MATRIX_REFERENCE.match(value.strip())
    if reference:
        return _matrix_values(job, reference.group(1))
    if "${{" in value:
        return _QUOTED.findall(value)
    return [value]


def runner_labels(job: dict[str, object]) -> list[str]:
    """Return every runner label a job can run on.

    Scalar, list, `{labels: ...}` mapping, runner-selection expression and
    matrix-reference forms are all read.

    Returns
    -------
    list[str]
        Every label the job can select, across matrix legs and expression arms.

    Raises
    ------
    WorkflowReadingError
        If no label can be derived, which would otherwise make the job
        silently not Linux.
    """
    runs_on = job.get("runs-on")
    entries: list[object]
    if isinstance(runs_on, dict):
        entries = _as_list(runs_on.get("labels"))
    else:
        entries = _as_list(runs_on)
    labels = [label for entry in entries for label in _labels_of(entry, job)]
    if not labels:
        message = f"cannot place runs-on {runs_on!r}; refusing to pass vacuously"
        raise WorkflowReadingError(message, reader=READER)
    return labels


def is_linux_capable(job: dict[str, object]) -> bool:
    """Return whether any runner the job can select is Linux.

    Returns
    -------
    bool
        True when at least one selectable runner is Linux.

    Raises
    ------
    WorkflowReadingError
        If a label is neither recognizably Linux nor recognizably another
        platform: a self-hosted label cannot be placed, and guessing would
        pass or fail the job for the wrong reason.
    """
    linux = False
    for label in runner_labels(job):
        lowered = label.lower()
        if lowered.startswith(_LINUX_PREFIXES):
            linux = True
        elif not lowered.startswith(_OTHER_PREFIXES):
            message = f"cannot place runner label {label!r} as Linux or not"
            raise WorkflowReadingError(message, reader=READER)
    return linux


def _step_reaches(step: dict[str, object], reach: MakeReach) -> bool:
    """Return whether one step reaches the suite or the preflight."""
    uses = step.get("uses")
    if isinstance(uses, str) and COVERAGE_ACTION in uses:
        return True
    run = step.get("run")
    if not isinstance(run, str):
        return False
    if _SUITE_COMMAND.search(run):
        return True
    return any(
        reach.reaches_preflight(goal) or reach.reaches_suite(goal)
        for goal in make_goals(run)
    )


def _is_install_step(step: dict[str, object]) -> bool:
    """Return whether a step runs `make install-build-tools`."""
    run = step.get("run")
    return isinstance(run, str) and INSTALL_TARGET in make_goals(run)


def _install_faults(step: dict[str, object]) -> list[str]:
    """Return why an install step could be skipped or its failure swallowed."""
    faults: list[str] = []
    if "if" in step:
        faults.append("the install step is conditional (`if:`)")
    if str(step.get("continue-on-error", "false")).strip().lower() != "false":
        faults.append("the install step sets `continue-on-error`")
    if _SWALLOWED_FAILURE.search(str(step.get("run", ""))):
        faults.append("the install step swallows its failure with `|| true`")
    return faults


def read_job(
    workflow: str, name: str, job: dict[str, object], reach: MakeReach
) -> JobReading | None:
    """Return a job's reading, or None when it is not a Linux suite job."""
    steps = [s for s in _as_list(job.get("steps")) if isinstance(s, dict)]
    reaching = tuple(i for i, step in enumerate(steps) if _step_reaches(step, reach))
    if not reaching or not is_linux_capable(job):
        return None
    installs = tuple(i for i, step in enumerate(steps) if _is_install_step(step))
    faults: list[str] = []
    if not installs:
        faults.append("no step runs `make install-build-tools`")
    else:
        before = [i for i in installs if i < reaching[0]]
        if not before:
            faults.append("the install runs after the first step that reaches it")
        for index in before:
            faults.extend(_install_faults(steps[index]))
    return JobReading(workflow, name, reaching, installs, tuple(faults))


def suite_job_readings(
    documents: dict[str, WorkflowDocument], reach: MakeReach
) -> list[JobReading]:
    """Return a reading for every Linux job that reaches the suite or preflight.

    Returns
    -------
    list[JobReading]
        One reading per such job.

    Raises
    ------
    WorkflowReadingError
        If no job is found.
    """
    readings = [
        reading
        for workflow, document in documents.items()
        for name, job in workflow_jobs(document).items()
        if (reading := read_job(workflow, name, job, reach)) is not None
    ]
    if not readings:
        message = (
            "no Linux job reaching the suite or the build-tools preflight was "
            "found; the wiring rule is satisfied by finding nothing, so this is "
            "the reader failing"
        )
        raise WorkflowReadingError(message, reader=READER)
    return readings


def external_workflow_calls(documents: dict[str, WorkflowDocument]) -> list[str]:
    """Return `workflow:job` for every job that calls a reusable workflow.

    A reusable workflow's steps are not in this repository, so reachability
    through it cannot be read; each call must be classified by a person.

    Returns
    -------
    list[str]
        One `workflow:job` entry per reusable-workflow call.
    """
    return [
        f"{workflow}:{name}"
        for workflow, document in documents.items()
        for name, job in workflow_jobs(document).items()
        if "uses" in job
    ]
