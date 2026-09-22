"""The timeout-ordering rules as readings that return their violations.

Each function takes the coverage jobs and the values the contract pins,
and returns one message per violation rather than asserting. The
contract in `test_timeout_ordering_contract` asserts that each returns
nothing for this repository's workflows; `test_timeout_ordering_rules`
drives the same functions with jobs and configurations the tree does
not contain and asserts that each rule reports what it exists to
report. A rule exercised only over files that satisfy it passes whether
or not it works, and the tier this repository has not set yet, the
whole-run `global-timeout`, would otherwise never be read at all.
"""

import typing as typ
from fractions import Fraction

from tests.support.nextest_config import (
    global_timeout,
    largest_test_allowance,
    termination_allowance,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from tests.support.coverage_workflows import CoverageJob


def unset_watchdogs(jobs: cabc.Iterable[CoverageJob]) -> list[str]:
    """Return every coverage step that sets no watchdog of its own.

    Parameters
    ----------
    jobs : Iterable[CoverageJob]
        The coverage jobs to read.

    Returns
    -------
    list of str
        One entry per step inheriting the shared action's default.
    """
    return [
        f"{job}: step {index + 1} of {job.steps}"
        for job in jobs
        for index, watchdog in enumerate(job.watchdogs)
        if watchdog is None
    ]


def unsized_watchdogs(jobs: cabc.Iterable[CoverageJob], required: float) -> list[str]:
    """Return every set watchdog that is not the sized value.

    Parameters
    ----------
    jobs : Iterable[CoverageJob]
        The coverage jobs to read.
    required : float
        The watchdog this repository sized, in seconds.

    Returns
    -------
    list of str
        One entry per step setting another value.
    """
    return [
        f"{job}: step {index + 1} of {job.steps} sets {watchdog:g} s"
        for job in jobs
        for index, watchdog in enumerate(job.watchdogs)
        if watchdog is not None and watchdog != required
    ]


def ceiling_shortfalls(
    jobs: cabc.Iterable[CoverageJob], required_ceiling: cabc.Callable[..., float]
) -> list[str]:
    """Return every job whose ceiling cannot contain its watchdogs.

    A job with no `timeout-minutes` is reported as such, because it
    inherits GitHub's six-hour default rather than any ceiling at all.

    Parameters
    ----------
    jobs : Iterable[CoverageJob]
        The coverage jobs to read.
    required_ceiling : Callable
        Returns the smallest acceptable ceiling for a job's watchdog
        budgets, in seconds.

    Returns
    -------
    list of str
        One entry per job without a sufficient ceiling.
    """
    found: list[str] = []
    for job in jobs:
        budgets = [watchdog for watchdog in job.watchdogs if watchdog is not None]
        required = required_ceiling(budgets)
        if job.job_timeout is None:
            found.append(f"{job} has no timeout-minutes")
        elif job.job_timeout < required:
            found.append(
                f"{job} has a ceiling of {job.job_timeout:.0f}s, below the "
                f"{required:.0f}s needed to contain {len(budgets)} watchdog(s)"
            )
    return found


def whole_run_violations(
    jobs: cabc.Iterable[CoverageJob], nextest_config: str, cold_build: float
) -> list[str]:
    """Return every way a whole-run budget would pre-empt a tier beside it.

    Empty when no `global-timeout` is set, since there is then no tier
    to order. When one is, it must sit above the largest per-test
    allowance, and each watchdog must cover it, nextest's termination
    procedure, and a cold build.

    Every term is exact, and the cold-build constant is converted rather
    than added as a `float`: one `float` in the sum rounds the whole of
    it, which would put the comparison back where the strict `>`
    started.

    Parameters
    ----------
    jobs : Iterable[CoverageJob]
        The coverage jobs to read.
    nextest_config : str
        The nextest configuration's text.
    cold_build : float
        Build time inside a `cargo` invocation before nextest starts its
        own clock, in seconds.

    Returns
    -------
    list of str
        One entry per violation.
    """
    whole_run = global_timeout(nextest_config)
    if whole_run is None:
        return []
    found: list[str] = []
    largest = largest_test_allowance(nextest_config)
    if whole_run <= largest:
        found.append(
            f"the {whole_run:.0f}s global-timeout is not above the "
            f"{largest:.0f}s largest per-test allowance"
        )
    required = whole_run + termination_allowance(nextest_config) + Fraction(cold_build)
    found += [
        f"{job} step {index + 1} sets a {watchdog or 0:.0f}s watchdog, below "
        f"the {required:.0f}s needed to cover the {whole_run:.0f}s whole-run "
        f"budget, nextest's termination procedure, and a cold build"
        for job in jobs
        for index, watchdog in enumerate(job.watchdogs)
        if watchdog is None or watchdog < required
    ]
    return found


def condition_violations(
    jobs: cabc.Iterable[CoverageJob],
    required: dict[tuple[str, str], tuple[object, object]],
) -> list[str]:
    """Return every lane whose conditions differ from the pinned ones.

    Compared both ways before the values are. A lane nobody listed is a
    lane whose condition nothing checks; a listed lane that has stopped
    invoking the action is the opposite loss. Both are reported by name.

    Parameters
    ----------
    jobs : Iterable[CoverageJob]
        The coverage jobs to read.
    required : dict
        The ``(step if, job if)`` each ``(workflow, job)`` must carry.

    Returns
    -------
    list of str
        One entry per unlisted, missing or differing lane.
    """
    found = {(job.workflow, job.job): job.conditions for job in jobs}
    unlisted = [f"{lane} is not listed" for lane in sorted(set(found) - set(required))]
    missing = [
        f"{lane} no longer invokes the coverage action"
        for lane in sorted(set(required) - set(found))
    ]
    wrong = [
        f"{lane} carries {sorted(map(str, set(found[lane])))}, not {expected}"
        for lane, expected in required.items()
        if lane in found and set(found[lane]) != {expected}
    ]
    return unlisted + missing + wrong
