"""Hold each job of coverage-main.yml to the runner the split gives it.

The measuring job runs on a GitHub-hosted runner, which cannot write Ubicloud's
cache store. The two jobs beside it run on Ubicloud and write what the
Ubicloud pull-request lane reads from main: the ratchet baseline and the
compiler cache. The workflow runs on pushes to main only, so no job needs a
fork fallback arm.
"""

import typing as typ

import pytest

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from tests.support.workflows import WorkflowDocument

RUNNERS: typ.Final = {
    "coverage-upload": "ubuntu-latest",
    "coverage-baseline": "ubicloud-standard-2",
    "coverage-warmup": "ubicloud-standard-4",
}


@pytest.mark.parametrize(("job", "runner"), sorted(RUNNERS.items()))
def test_each_job_runs_on_its_runner(
    documents: dict[str, WorkflowDocument], job: str, runner: str
) -> None:
    """Name each job's runner outright, and let no other job in.

    Parameters
    ----------
    documents
        This repository's workflows, parsed once for the session.
    job
        The job identifier.
    runner
        The runner label the job must name.
    """
    jobs = documents["coverage-main.yml"].get("jobs")
    assert isinstance(jobs, dict), "coverage-main.yml has no jobs"
    assert sorted(jobs) == sorted(RUNNERS), f"unexpected jobs: {sorted(jobs)}"
    assert jobs[job].get("runs-on") == runner, f"{job} must run on {runner}"
