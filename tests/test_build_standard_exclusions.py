"""Hold the routes that must not take the development standard to their exclusions.

Coverage, release, packaging and Whitaker each exclude the parallel frontend,
mold and the Cranelift backend, and each does it by a different mechanism: an
assigned `RUSTFLAGS` that displaces the Cargo configuration, a per-profile
backend key that only the dev profile carries, or the shared action's own
selection of LLVM. The release and Whitaker `RUSTFLAGS` live in the Makefile
and are held by `test_build_standard_make_routes`; these contracts hold the
workflow and configuration halves.

Driven over constructed workflows in both directions first, because a check
over this repository's own correct workflows passes whether or not it
discriminates anything.
"""

import typing as typ

import pytest

from tests.support.build_standard import (
    CARGO_CONFIG,
    MOLD_FLAG,
    THREADS_FLAG,
    read_toml,
)
from tests.support.workflow_documents import WORKFLOWS_DIRECTORY
from tests.support.workflow_files import WorkflowReadingError, read_workflows
from tests.support.workflows import load_workflow, workflow_steps

if typ.TYPE_CHECKING:
    import collections.abc as cabc

COVERAGE_ACTION: typ.Final = "generate-coverage@"
FLAG_VARIABLES: typ.Final = (
    "RUSTFLAGS",
    "RUSTDOCFLAGS",
    "CARGO_BUILD_RUSTFLAGS",
    "CARGO_ENCODED_RUSTFLAGS",
)
DEVELOPMENT_MARKERS: typ.Final = (
    THREADS_FLAG,
    MOLD_FLAG,
    "codegen-backend",
    "cranelift",
)


def _env_maps(node: object) -> cabc.Iterator[dict[str, object]]:
    """Yield every `env` mapping anywhere in a parsed workflow."""
    match node:
        case dict():
            for key, value in node.items():
                if key == "env" and isinstance(value, dict):
                    yield value
                yield from _env_maps(value)
        case list():
            for item in node:
                yield from _env_maps(item)


def development_leaks(document: dict[str | bool, object]) -> list[str]:
    """Return every compiler-flag variable that carries a development marker.

    Parameters
    ----------
    document
        A parsed workflow.

    Returns
    -------
    list[str]
        One entry per leaking variable, naming it and the marker it carries.
        Profile selections (`CARGO_PROFILE_*`) are leaks of the backend.
    """
    leaks: list[str] = []
    for env in _env_maps(document):
        for name, value in env.items():
            text = str(value)
            names_flags = name in FLAG_VARIABLES or name.startswith("CARGO_PROFILE_")
            leaks.extend(
                f"{name} carries {marker}"
                for marker in DEVELOPMENT_MARKERS
                if names_flags and marker in text
            )
            if name.startswith("CARGO_PROFILE_") and "CODEGEN_BACKEND" in name:
                leaks.append(f"{name} selects a backend")
    return leaks


def coverage_steps(
    document: dict[str | bool, object],
) -> list[dict[str, object]]:
    """Return every step that uses the shared coverage action."""
    return [
        step
        for step in workflow_steps(document)
        if COVERAGE_ACTION in str(step.get("uses", ""))
    ]


def coverage_faults(step: dict[str, object]) -> list[str]:
    """Return why a coverage step does not state its own exclusion."""
    env = step.get("env")
    flags = env.get("RUSTFLAGS") if isinstance(env, dict) else None
    if flags is None:
        return ["the coverage step does not assign RUSTFLAGS itself"]
    return [
        f"the coverage step's RUSTFLAGS carries {marker}"
        for marker in DEVELOPMENT_MARKERS
        if marker in str(flags)
    ]


def _workflow(steps: str, env: str = "") -> dict[str | bool, object]:
    """Return a parsed one-job workflow with `steps` and an optional job env."""
    return load_workflow(
        f"on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n{env}    steps:\n{steps}"
    )


COVERAGE_USES = (
    "      - uses: leynos/shared-actions/.github/actions/generate-coverage@abc\n"
)

ENV_HEAD = "        env:\n          RUSTFLAGS: "


def test_a_coverage_step_that_states_its_exclusion_has_no_faults() -> None:
    """The positive control."""
    steps = COVERAGE_USES + ENV_HEAD + "-D warnings\n"
    (step,) = coverage_steps(_workflow(steps))
    assert not coverage_faults(step), "expected not coverage_faults(step)"


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(COVERAGE_USES, "does not assign", id="no_env"),
        pytest.param(
            COVERAGE_USES + ENV_HEAD + "-Zthreads=8\n",
            "carries -Zthreads=8",
            id="inherits_the_frontend",
        ),
        pytest.param(
            COVERAGE_USES + ENV_HEAD + "-D warnings -Clink-arg=-fuse-ld=mold\n",
            "carries -Clink-arg=-fuse-ld=mold",
            id="inherits_mold",
        ),
    ],
)
def test_each_coverage_inheritance_is_detected(steps: str, expected: str) -> None:
    """A coverage step that takes any development flag is a fault."""
    (step,) = coverage_steps(_workflow(steps))
    assert any(expected in fault for fault in coverage_faults(step)), (
        "expected any((expected in fault for fault in coverage_faults(step)))"
    )


@pytest.mark.parametrize(
    "env_line",
    [
        pytest.param("RUSTFLAGS: -Zthreads=8", id="frontend"),
        pytest.param("CARGO_BUILD_RUSTFLAGS: -Clink-arg=-fuse-ld=mold", id="mold"),
        pytest.param("CARGO_PROFILE_DEV_CODEGEN_BACKEND: cranelift", id="backend"),
    ],
)
def test_a_development_flag_anywhere_in_a_workflow_is_a_leak(env_line: str) -> None:
    """A job-level `env` is read as well as a step's."""
    document = _workflow("      - run: echo\n", env=f"    env:\n      {env_line}\n")
    assert development_leaks(document), "expected development_leaks(document)"


def test_a_clean_workflow_has_no_leaks() -> None:
    """The negative control for the leak reader."""
    document = _workflow(
        "      - run: echo\n", env="    env:\n      RUSTFLAGS: -D warnings\n"
    )
    assert not development_leaks(document), "expected not development_leaks(document)"


REAL_WORKFLOWS: typ.Final = read_workflows(WORKFLOWS_DIRECTORY)


def test_the_real_workflows_hold_coverage_steps() -> None:
    """An empty reading is the reader failing, so the lanes are named."""
    found = {
        name for name, document in REAL_WORKFLOWS.items() if coverage_steps(document)
    }
    if not found:
        message = "no coverage step was read from the workflows"
        raise WorkflowReadingError(message, reader="coverage_steps")
    assert found == {"smoke.yml", "coverage-main.yml"}, (
        "expected found == {'smoke.yml', 'coverage-main.yml'}"
    )


@pytest.mark.parametrize("workflow", ["smoke.yml", "coverage-main.yml"])
def test_every_real_coverage_step_states_its_exclusion(workflow: str) -> None:
    """Coverage keeps instrumentation and drops the development flags."""
    steps = coverage_steps(REAL_WORKFLOWS[workflow])
    assert steps, workflow
    for step in steps:
        assert not coverage_faults(step), "expected not coverage_faults(step)"


@pytest.mark.parametrize("workflow", sorted(REAL_WORKFLOWS))
def test_no_real_workflow_leaks_a_development_flag(workflow: str) -> None:
    """No workflow, job or step exports a development flag to a route."""
    assert not development_leaks(REAL_WORKFLOWS[workflow]), (
        "expected not development_leaks(REAL_WORKFLOWS[workflow])"
    )


def test_only_the_dev_profile_selects_a_backend() -> None:
    """A backend key on release or any other profile would reach the wheel."""
    config = read_toml(CARGO_CONFIG)
    profiles = config.get("profile", {})
    assert isinstance(profiles, dict), "expected isinstance(profiles, dict)"
    carriers = {
        name
        for name, table in profiles.items()
        if isinstance(table, dict) and "codegen-backend" in table
    }
    assert carriers <= {"dev"}, f"backend selected outside dev: {carriers}"
