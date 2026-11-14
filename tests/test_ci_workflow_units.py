"""Unit tests for the CI workflow contracts.

These tests parse repository workflows and assert that CI keeps calling the
canonical Makefile targets instead of duplicating build logic, and that tool
installation stays pinned and Makefile-resolved.
"""

import pathlib
import re
import tomllib
import typing as typ

import pytest

from tests.support.assertions import assert_with_context
from tests.support.workflows import load_workflow

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
WorkflowStep = typ.TypedDict(
    "WorkflowStep",
    {"name": str, "uses": str, "run": str, "with": dict[str, str]},
    total=False,
)
WorkflowJob = typ.TypedDict(
    "WorkflowJob",
    {
        "runs-on": str,
        "strategy": dict[str, dict[str, list[str]]],
        "steps": list[WorkflowStep],
        "uses": str,
        "needs": list[str],
        "permissions": dict[str, str],
    },
    total=False,
)
type SmokeWorkflow = tuple[dict[str, WorkflowJob], list[WorkflowStep], set[str]]


def _workflow_jobs(
    parsed_workflow: dict[str | bool, object],
) -> dict[str, WorkflowJob]:
    """Return the parsed workflow jobs with a narrow test-local shape."""
    jobs = parsed_workflow["jobs"]
    assert isinstance(jobs, dict), "expected isinstance(jobs, dict)"
    return typ.cast("dict[str, WorkflowJob]", jobs)


def _job_steps(job: WorkflowJob) -> list[WorkflowStep]:
    """Return a workflow job's steps, empty when it declares none."""
    # A job that delegates to a reusable workflow has no steps of its own: its
    # work lives in the called file, so the reading must answer with nothing
    # rather than fail on the missing key.
    return job.get("steps") or []


def _workflow_steps(jobs: dict[str, WorkflowJob]) -> list[WorkflowStep]:
    """Return every step from every parsed workflow job."""
    return [step for job in jobs.values() for step in _job_steps(job)]


def _workflow_step_named(job: WorkflowJob, name: str) -> WorkflowStep:
    """Return a named step from a parsed workflow job."""
    for step in _job_steps(job):
        if step.get("name") == name:
            return step
    available_names = [step.get("name", "<unnamed>") for step in _job_steps(job)]
    msg = (
        f"workflow step {name!r} not found in job {job!r}; "
        f"available steps: {available_names!r}"
    )
    raise AssertionError(msg)


def _workflow_document(workflow_name: str) -> dict[str | bool, object]:
    """Parse one repository workflow file into its document mapping."""
    return load_workflow(
        (REPOSITORY_ROOT / ".github" / "workflows" / workflow_name).read_text(
            encoding="utf-8"
        )
    )


def _workflow_environment(parsed_workflow: dict[str | bool, object]) -> dict[str, str]:
    """Return the workflow-level environment variables."""
    environment = parsed_workflow["env"]
    assert isinstance(environment, dict), "expected isinstance(environment, dict)"
    return typ.cast("dict[str, str]", environment)


def _makefile_tool_version(makefile: str, tool: str) -> str:
    """Return one version pin declared in the Makefile."""
    match = re.search(rf"^{tool}_VERSION \?= (?P<version>\S+)$", makefile, re.MULTILINE)
    assert match is not None, f"expected {tool}_VERSION pin in Makefile"
    return match["version"]


@pytest.fixture(name="smoke_workflow", scope="module")
def smoke_workflow_fixture() -> SmokeWorkflow:
    """Parse the smoke workflow once for the per-concern CI assertions."""
    jobs = _workflow_jobs(_workflow_document("smoke.yml"))
    workflow_steps = _workflow_steps(jobs)
    run_commands = {
        command.strip()
        for step in workflow_steps
        for command in str(step.get("run", "")).splitlines()
        if command.strip()
    }
    return jobs, workflow_steps, run_commands


def test_ci_workflow_calls_the_canonical_makefile_targets(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """Make CI exercise Makefile targets instead of duplicating build logic."""
    _jobs, _workflow_steps, run_commands = smoke_workflow
    assert_with_context(
        {
            "make check-fmt",
            "make spelling",
            "make nixie",
            "make typecheck",
            "make lint",
            "make test-doc",
        }.issubset(run_commands),
        "expected <'make check-fmt', 'make spelling', 'make n...",
    )


@pytest.mark.parametrize("tool", ["RUFF", "TY"])
def test_ci_tool_versions_match_makefile(tool: str) -> None:
    """Keep each CI tool pin aligned with its canonical Makefile pin."""
    workflow_environment = _workflow_environment(_workflow_document("smoke.yml"))
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    assert_with_context(
        workflow_environment[f"{tool}_VERSION"]
        == _makefile_tool_version(makefile, tool),
        f"expected CI {tool} version to match the Makefile pin",
    )


def test_ci_workflow_job_topology(smoke_workflow: SmokeWorkflow) -> None:
    """CI must keep the lint-test job, and release-smoke must delegate."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    assert "lint-test" in jobs, "expected 'lint-test' in jobs"
    assert_with_context(
        jobs["lint-test"]["runs-on"]
        == "${{ github.event.pull_request.head.repo.fork && 'ubuntu-latest' "
        "|| 'ubicloud-standard-4' }}",
        "expected jobs['lint-test']['runs-on'] to be the runner-selection expression",
    )
    assert "release-smoke" in jobs, "expected 'release-smoke' in jobs"
    assert_with_context(
        jobs["release-smoke"].get("uses") == "./.github/workflows/build-wheels.yml",
        "release-smoke must delegate to the reusable build-wheels workflow",
    )


def test_the_delegated_build_wheels_workflow_owns_the_platform_matrix() -> None:
    """The reusable workflow, not its caller, states the platform legs.

    The old caller held the operating-system matrix, so a leg could be
    dropped from a pull request while still being built by the release. The
    matrix now lives in the called workflow, which both callers use, and it
    must still name the platforms the release publishes.
    """
    jobs = _workflow_jobs(_workflow_document("build-wheels.yml"))
    hosted = jobs["build-hosted"]
    assert_with_context(
        hosted["runs-on"] == "${{ matrix.os }}",
        "build-hosted must select its runner from the matrix",
    )
    matrix = typ.cast("list[dict[str, str]]", hosted["strategy"]["matrix"]["include"])
    platforms = {(entry["os"], entry["arch"]) for entry in matrix}
    assert_with_context(
        platforms
        == {
            ("macos-latest", "arm64"),
            ("macos-15-intel", "x86_64"),
            ("windows-2022", "x86_64"),
        },
        f"unexpected hosted platform matrix: {sorted(platforms)}",
    )
    linux = typ.cast(
        "list[dict[str, str]]", jobs["build-linux"]["strategy"]["matrix"]["include"]
    )
    assert_with_context(
        {entry["arch"] for entry in linux} == {"x86_64", "aarch64"},
        f"unexpected Linux architecture matrix: {linux}",
    )
    assert_with_context(
        jobs["verify-wheel-install"]["needs"] == ["build-linux", "build-hosted"],
        "verify-wheel-install must wait on every build leg",
    )


def test_every_runnable_leg_smokes_the_wheel_it_built() -> None:
    """A built wheel that is never installed proves nothing about the release.

    Each leg that can execute its own wheel installs the artefact with
    `--no-index` into a fresh virtual environment and runs the smoke module
    from outside the checkout, so the import cannot be satisfied by the source
    tree. The aarch64 wheel is cross-built and needs emulation to import, so
    its leg uploads without running it, and the release publishes it only
    beside attested artefacts.
    """
    jobs = _workflow_jobs(_workflow_document("build-wheels.yml"))
    linux_steps = _job_steps(jobs["build-linux"])
    linux_runs = " ".join(str(step.get("run", "")) for step in linux_steps)
    hosted_runs = " ".join(
        str(step.get("run", "")) for step in _job_steps(jobs["build-hosted"])
    )
    assert_with_context(
        "-m pip install --no-index" in linux_runs,
        "the runnable Linux leg must install its wheel without an index",
    )
    assert_with_context(
        "-m stilyagi.smoke" in linux_runs,
        "the runnable Linux leg must smoke the wheel it built",
    )
    assert_with_context(
        "-m pip install --no-index" in hosted_runs,
        "every hosted leg must install its wheel without an index",
    )
    assert_with_context(
        "-m stilyagi.smoke" in hosted_runs,
        "every hosted leg must smoke the wheel it built",
    )
    smoke_steps = [
        (step, str(step.get("if", "")))
        for step in linux_steps
        if "-m stilyagi.smoke" in str(step.get("run", ""))
    ]
    assert_with_context(
        len(smoke_steps) == 1,
        f"expected one Linux smoke step, found {len(smoke_steps)}",
    )
    assert_with_context(
        smoke_steps[0][1] == "matrix.arch == 'x86_64'",
        "the Linux smoke step must run only where its wheel can be imported",
    )


def test_ci_workflow_triggers_on_pull_request_and_main_push() -> None:
    """CI must run for pull requests and pushes to the main branch."""
    parsed_workflow = _workflow_document("smoke.yml")
    triggers = typ.cast("dict[str, object]", parsed_workflow.get("on", {}))
    assert "pull_request" in triggers, "expected 'pull_request' in triggers"
    assert_with_context(
        "main"
        in typ.cast("dict[str, list[str]]", triggers.get("push", {})).get(
            "branches", []
        ),
        "expected 'main' in typ.cast('dict[str, list[str]]', ...",
    )


def test_ci_workflows_share_python_setup_configuration(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """Every setup-python invocation must share one valid action and interpreter."""
    _jobs, smoke_steps, _run_commands = smoke_workflow
    coverage_steps = _workflow_steps(
        _workflow_jobs(_workflow_document("coverage-main.yml"))
    )
    python_steps = [
        step
        for step in [*smoke_steps, *coverage_steps]
        if str(step.get("uses", "")).startswith("actions/setup-python")
    ]
    assert python_steps, "expected python_steps"
    python_actions = [str(step["uses"]) for step in python_steps]
    assert_with_context(
        all(
            action_name == "actions/setup-python" and separator == "@" and reference
            for action_name, separator, reference in (
                action.partition("@") for action in python_actions
            )
        ),
        "expected each setup-python invocation to name an action reference",
    )
    assert_with_context(
        len(set(python_actions)) == 1,
        "expected all setup-python invocations to use one action reference",
    )
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    python_version = pyproject["tool"]["ty"]["environment"]["python-version"]
    assert isinstance(python_version, str), "expected Python version string"
    assert_with_context(
        all(
            step.get("with", {}).get("python-version") == python_version
            for step in python_steps
        ),
        "expected setup-python interpreter to match typecheck configuration",
    )


def test_ci_workflow_resolves_interrogate_and_formatting_from_makefile(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """Resolve Interrogate and Markdown formatting through the Makefile only.

    Interrogate resolves from the locked dev dependency group through the
    Makefile, so CI must not install it separately. CI installs mdtablefix
    with the pinned action, but the formatter itself must only ever run
    through `make check-fmt`.
    """
    _jobs, _workflow_steps, run_commands = smoke_workflow
    assert_with_context(
        all("interrogate" not in command for command in run_commands),
        "expected all(('interrogate' not in command for comma...",
    )
    assert_with_context(
        all("mdtablefix" not in command for command in run_commands),
        "expected all(('mdtablefix' not in command for comma...",
    )


def test_ci_workflow_installs_versioned_nixie_cli(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """CI must install a versioned nixie-cli release for the Mermaid gate."""
    _jobs, workflow_steps, _run_commands = smoke_workflow
    assert_with_context(
        any(
            re.search(r"\buv tool install nixie-cli==\S+", str(step.get("run", "")))
            is not None
            for step in workflow_steps
        ),
        "expected a versioned nixie-cli installation command",
    )


def test_ci_workflow_installs_test_runner_and_whitaker(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """CI must install cargo-nextest and Whitaker through the shared action."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    test_runner_step = _workflow_step_named(jobs["lint-test"], "Install test runner")
    assert_with_context(
        "cargo binstall --no-confirm cargo-nextest" in test_runner_step["run"],
        "expected 'cargo binstall --no-confirm cargo-nextest'...",
    )
    whitaker_step = _workflow_step_named(jobs["lint-test"], "Install Whitaker")
    # Whitaker is installed only through the shared action, pinned to a full
    # commit SHA; the action owns the installer version, cache and checks, so
    # the step carries no script of its own.
    assert_with_context(
        re.fullmatch(
            r"leynos/shared-actions/\.github/actions/install-whitaker@[0-9a-f]{40}",
            str(whitaker_step.get("uses", "")),
        )
        is not None,
        "expected Install Whitaker to use the shared action at a full SHA",
    )
    assert_with_context(
        "run" not in whitaker_step,
        "expected Install Whitaker to carry no script of its own",
    )
    assert_with_context(
        whitaker_step.get("with") == {"cranelift": "true"},
        "expected Install Whitaker to enable only the cranelift component",
    )


def test_ci_workflow_delegates_the_release_smoke(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """The release-smoke job proves the bytes the reusable workflow built."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    assert_with_context(
        not _job_steps(jobs["release-smoke"]),
        "release-smoke must delegate rather than carry steps of its own",
    )
    assert_with_context(
        jobs["release-smoke"].get("permissions") == {"contents": "read"},
        "the delegating job must grant nothing beyond reading the repository",
    )
