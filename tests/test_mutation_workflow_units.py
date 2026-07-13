"""Contract tests for the mutation-testing caller workflow.

The executable logic lives in the ``leynos/shared-actions`` reusable
workflow, which carries its own unit and integration tests; stilyagi's
caller is declarative configuration. These tests parse the caller with
PyYAML and pin the contract it must uphold, so drift (repointing the pin
at a branch, widening permissions, or losing the workspace-test and
scaffolding-exclusion configuration) fails CI on the pull request rather
than surfacing in a scheduled or manual run.

The Rust workspace is the only mutation target: the Python package is a
maturin native-extension package whose pytest suite depends on the
compiled bridge and on repository-root artefacts, which the shared
mutmut caller's in-process sandbox cannot honour.

These tests ride the repository's ordinary pytest run (``make test``).
"""

import pathlib
import typing as typ

import yaml

WORKFLOW_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "mutation-testing.yml"
)

#: The estate-wide pin for leynos/shared-actions (the merge commit of
#: leynos/shared-actions PR #334, which adds the `cs-coverage check`
#: mode consumed by the CodeScene coverage rollout). Bump the workflow
#: and this test together.
PINNED_SHA = "927edd45ae77be4251a8a18ca9eb5613a2e32cbd"

EXPECTED_USES = (
    "leynos/shared-actions/.github/workflows/mutation-cargo.yml@" + PINNED_SHA
)

#: The exact caller configuration: mutate the workspace crates only,
#: skip the test scaffolding crates, mirror CI's --all-features
#: baseline, and run the whole workspace's tests against each mutant
#: because CI tests with --workspace.
EXPECTED_WITH_BLOCK = {
    "paths": "crates/",
    "exclude-globs": (
        "crates/stilyagi-test-fixtures/**,crates/stilyagi-test-support/**"
    ),
    "extra-args": "--all-features --test-workspace=true",
}

EXPECTED_JOB_NAME = "mutation-rust"


def _load() -> dict[str, typ.Any]:
    """Parse the workflow file into a mapping."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict), "the workflow must parse to a mapping"
    return workflow


def _triggers(workflow: dict[str, typ.Any]) -> dict[str, typ.Any]:
    """Return the ``on:`` mapping (PyYAML parses the bare key as True)."""
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), "the workflow must declare an on: mapping"
    return triggers


def _mutation_job(workflow: dict[str, typ.Any]) -> dict[str, typ.Any]:
    """Return the single calling job."""
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "the workflow must declare a jobs mapping"
    assert list(jobs) == [EXPECTED_JOB_NAME], (
        f"expected a single job named {EXPECTED_JOB_NAME!r}, found {sorted(jobs)}"
    )
    return jobs[EXPECTED_JOB_NAME]


def test_uses_reference_is_pinned_to_the_documented_sha() -> None:
    """Pin the shared workflow call to the exact documented SHA."""
    uses = _mutation_job(_load()).get("uses")
    assert uses is not None, f"jobs.{EXPECTED_JOB_NAME}.uses is missing"
    path, _, ref = uses.partition("@")
    assert path == "leynos/shared-actions/.github/workflows/mutation-cargo.yml", (
        f"jobs.{EXPECTED_JOB_NAME}.uses must reference mutation-cargo.yml, got {path!r}"
    )
    assert len(ref) == 40, (
        f"jobs.{EXPECTED_JOB_NAME}.uses must pin a full 40-character commit "
        f"SHA, not a branch or tag: {ref!r}"
    )
    assert all(c in "0123456789abcdef" for c in ref), (
        f"jobs.{EXPECTED_JOB_NAME}.uses must pin a lowercase hex commit SHA, "
        f"not a branch or tag: {ref!r}"
    )
    assert uses == EXPECTED_USES, (
        f"jobs.{EXPECTED_JOB_NAME}.uses pins {ref!r}; the estate documents "
        f"{PINNED_SHA!r} — bump the workflow and this test together"
    )


def test_job_permissions_are_exactly_least_privilege() -> None:
    """Grant the job contents: read and id-token: write, nothing broader."""
    permissions = _mutation_job(_load()).get("permissions")
    assert permissions == {"contents": "read", "id-token": "write"}, (
        f"jobs.{EXPECTED_JOB_NAME}.permissions must be exactly "
        f"{{'contents': 'read', 'id-token': 'write'}}, got {permissions!r}"
    )


def test_workflow_default_permissions_are_empty() -> None:
    """Keep the workflow-level default token scope empty."""
    workflow = _load()
    assert workflow.get("permissions") == {}, (
        f"top-level permissions must be an empty mapping, got "
        f"{workflow.get('permissions')!r}"
    )


def test_concurrency_serializes_per_ref_without_cancelling() -> None:
    """Queue runs per ref instead of cancelling one another."""
    concurrency = _load().get("concurrency")
    assert isinstance(concurrency, dict), "the workflow must declare concurrency"
    assert concurrency.get("group") == "mutation-testing-${{ github.ref }}", (
        f"concurrency.group must key on the triggering ref, got "
        f"{concurrency.get('group')!r}"
    )
    assert concurrency.get("cancel-in-progress") is False, (
        f"concurrency.cancel-in-progress must be false, got "
        f"{concurrency.get('cancel-in-progress')!r}"
    )


def test_triggers_keep_schedule_and_plain_dispatch() -> None:
    """Keep the daily schedule and an inputless manual dispatch."""
    triggers = _triggers(_load())
    schedule = triggers.get("schedule")
    assert schedule == [{"cron": "50 8 * * *"}], (
        f"on.schedule must be the daily 08:50 UTC cron, got {schedule!r}"
    )
    assert "workflow_dispatch" in triggers, "on.workflow_dispatch is missing"
    dispatch = triggers.get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    assert not inputs, (
        "on.workflow_dispatch must not declare inputs; the Actions "
        "run-workflow control selects the ref"
    )


def test_with_block_carries_the_exact_caller_configuration() -> None:
    """Pass exactly the documented caller configuration, nothing else."""
    with_block = _mutation_job(_load()).get("with")
    assert with_block == EXPECTED_WITH_BLOCK, (
        f"jobs.{EXPECTED_JOB_NAME}.with must equal {EXPECTED_WITH_BLOCK!r} "
        f"(crates-only paths, scaffolding-crate excludes, and CI's "
        f"--all-features --workspace baseline), got {with_block!r}"
    )
