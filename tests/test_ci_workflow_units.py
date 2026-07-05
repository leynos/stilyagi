"""Unit tests for the CI smoke workflow contract.

These tests parse `.github/workflows/smoke.yml` and assert that CI keeps
calling the canonical Makefile targets instead of duplicating build logic,
and that tool installation stays pinned and Makefile-resolved.
"""

import pathlib
import typing as typ

import pytest
import yaml

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
    },
    total=False,
)
SmokeWorkflow = tuple[dict[str, "WorkflowJob"], list["WorkflowStep"], set[str]]


def _workflow_document(workflow: str) -> dict[str, object]:
    """Parse a GitHub Actions workflow while preserving the `on` key as text."""
    # BaseLoader is required here; safe_load drops the literal `on` workflow key.
    loaded = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return typ.cast("dict[str, object]", loaded)


def _workflow_jobs(parsed_workflow: dict[str, object]) -> dict[str, WorkflowJob]:
    """Return the parsed workflow jobs with a narrow test-local shape."""
    jobs = parsed_workflow["jobs"]
    assert isinstance(jobs, dict)
    return typ.cast("dict[str, WorkflowJob]", jobs)


def _job_steps(job: WorkflowJob) -> list[WorkflowStep]:
    """Return a workflow job's steps with a narrow test-local shape."""
    return typ.cast("list[WorkflowStep]", job["steps"])


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


def _smoke_workflow_document() -> dict[str, object]:
    """Parse the smoke workflow file into its document mapping."""
    return _workflow_document(
        (REPOSITORY_ROOT / ".github" / "workflows" / "smoke.yml").read_text(
            encoding="utf-8"
        )
    )


@pytest.fixture(name="smoke_workflow", scope="module")
def smoke_workflow_fixture() -> SmokeWorkflow:
    """Parse the smoke workflow once for the per-concern CI assertions."""
    jobs = _workflow_jobs(_smoke_workflow_document())
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
    assert {
        "make check-fmt",
        "make markdownlint",
        "make nixie",
        "make typecheck",
        "make lint",
        "make test",
    }.issubset(run_commands)


def test_ci_workflow_job_topology(smoke_workflow: SmokeWorkflow) -> None:
    """CI must keep the lint-test job and the release-smoke OS matrix."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    assert "lint-test" in jobs
    assert jobs["lint-test"]["runs-on"] == "ubuntu-latest"
    assert "release-smoke" in jobs
    assert jobs["release-smoke"]["runs-on"] == "${{ matrix.os }}"
    assert jobs["release-smoke"]["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "macos-latest",
        "windows-latest",
    ]


def test_ci_workflow_triggers_on_pull_request_and_main_push() -> None:
    """CI must run for pull requests and pushes to the main branch."""
    parsed_workflow = _smoke_workflow_document()
    triggers = typ.cast("dict[str, object]", parsed_workflow.get("on", {}))
    assert "pull_request" in triggers
    assert "main" in typ.cast("dict[str, list[str]]", triggers.get("push", {})).get(
        "branches", []
    )


def test_ci_workflow_pins_python_setup_action(smoke_workflow: SmokeWorkflow) -> None:
    """Every setup-python step must pin the action hash and Python version."""
    _jobs, workflow_steps, _run_commands = smoke_workflow
    python_steps = [
        step
        for step in workflow_steps
        if str(step.get("uses", "")).startswith("actions/setup-python@")
    ]
    assert python_steps
    assert all(
        step["uses"] == "actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405"
        for step in python_steps
    )
    assert all(step["with"]["python-version"] == "3.14" for step in python_steps)


def test_ci_workflow_resolves_interrogate_and_formatting_from_makefile(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """Resolve Interrogate and mdformat-all through the Makefile only.

    Interrogate resolves from the locked dev dependency group through the
    Makefile, so CI must not install it separately, and CI must not invoke
    `mdformat-all` outside the Makefile either.
    """
    _jobs, workflow_steps, run_commands = smoke_workflow
    assert all("interrogate" not in command for command in run_commands)
    assert all("mdformat-all" not in str(step) for step in workflow_steps)


def test_ci_workflow_installs_nixie_cli(smoke_workflow: SmokeWorkflow) -> None:
    """CI must install the pinned nixie-cli release for the Mermaid gate."""
    _jobs, workflow_steps, _run_commands = smoke_workflow
    assert any(
        "uv tool install nixie-cli==1.0.0" in str(step.get("run", ""))
        for step in workflow_steps
    )


def test_ci_workflow_installs_test_runner_and_whitaker(
    smoke_workflow: SmokeWorkflow,
) -> None:
    """CI must install cargo-nextest and the pinned Whitaker toolchain."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    test_runner_step = _workflow_step_named(jobs["lint-test"], "Install test runner")
    assert "cargo binstall --no-confirm cargo-nextest" in test_runner_step["run"]
    whitaker_step = _workflow_step_named(jobs["lint-test"], "Install Whitaker")
    whitaker_run = str(whitaker_step["run"])
    assert "github.com/leynos/whitaker" in whitaker_run
    assert "whitaker-installer" in whitaker_run
    assert "--cranelift" in whitaker_run


def test_ci_workflow_runs_release_smoke(smoke_workflow: SmokeWorkflow) -> None:
    """The release-smoke job must build and smoke-test through make release."""
    jobs, _workflow_steps, _run_commands = smoke_workflow
    release_smoke_step = _workflow_step_named(jobs["release-smoke"], "Release smoke")
    assert "make release" in release_smoke_step["run"]
