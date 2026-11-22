"""Contract test for how CI jobs provision the Makefile parser.

Every full-suite CI job installs Makeutil through the shared action and
verifies it, so the workflows are parsed and asserted structurally.
"""

import pathlib
import typing as typ

from tests.support import makeutil_contract
from tests.support.workflows import load_workflow

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _mapping(value: object, *, subject: str) -> dict[str, object]:
    """Return a JSON object, naming the unexpected `subject` on failure."""
    assert isinstance(value, dict), f"expected {subject} to be a JSON object"
    return typ.cast("dict[str, object]", value)


def _objects(value: object, *, subject: str) -> list[dict[str, object]]:
    """Return a JSON object array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    return [_mapping(item, subject=f"{subject} item") for item in value]


def _workflow_document(workflow_path: str) -> dict[str | bool, object]:
    """Return a repository workflow while preserving scalar strings."""
    workflow = (REPOSITORY_ROOT / workflow_path).read_text(encoding="utf-8")
    return load_workflow(workflow)


def _workflow_job(workflow_path: str, job_name: str) -> dict[str, object]:
    """Return a named job from a repository workflow."""
    workflow = _workflow_document(workflow_path)
    jobs = _mapping(workflow.get("jobs"), subject=f"{workflow_path} jobs")
    return _mapping(jobs.get(job_name), subject=f"{workflow_path} job {job_name!r}")


def _sole_workflow_step(
    workflow_path: str, job_name: str, step_name: str
) -> dict[str, object]:
    """Return the sole named workflow step from `job_name`."""
    steps = _objects(
        _workflow_job(workflow_path, job_name).get("steps"),
        subject=f"{workflow_path} job {job_name!r} steps",
    )
    matches = [step for step in steps if step.get("name") == step_name]
    assert len(matches) == 1, (
        f"expected one {step_name!r} step in {workflow_path} job {job_name!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def test_full_suite_workflows_consistently_provision_makefile_parser() -> None:
    """Every full-suite CI job must consistently install Makeutil independently."""
    lint_step = _sole_workflow_step(
        ".github/workflows/smoke.yml", "lint-test", "Lint and dead-code detection"
    )
    assert lint_step.get("run") == "make lint", "expected `make lint`"
    for workflow_path, job_name in (
        (".github/workflows/smoke.yml", "lint-test"),
        (".github/workflows/coverage-main.yml", "coverage-upload"),
    ):
        environment = _mapping(
            _workflow_document(workflow_path).get("env"),
            subject=f"{workflow_path} environment",
        )
        assert "MAKEUTIL_REVISION" not in environment, (
            f"{workflow_path} must not carry a from-source Makeutil pin"
        )
        assert "MAKEUTIL_TOOLCHAIN" not in environment, (
            f"{workflow_path} must not carry a Makeutil nightly toolchain"
        )
        install_step = _sole_workflow_step(workflow_path, job_name, "Install makeutil")
        contract = f"{workflow_path} {job_name} Makeutil"
        makeutil_contract.assert_installation(install_step, contract=contract)
        makeutil_contract.assert_verification(
            install_step,
            _sole_workflow_step(workflow_path, job_name, "Verify makeutil"),
            contract=contract,
        )
        makeutil_contract.assert_verification_follows_install(
            _objects(
                _workflow_job(workflow_path, job_name).get("steps"),
                subject=f"{contract} steps",
            ),
            contract=contract,
        )
