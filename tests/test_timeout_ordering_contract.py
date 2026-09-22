"""Contract for the timers that can end a test run.

Four independent budgets can end a coverage lane, each set somewhere
different, and they only work if each sits above the one inside it. Two
of the four are set here: the shared coverage action's wall-clock
watchdog on the ``cargo`` invocation, and the job's own
``timeout-minutes``, which this contract adds.

The outermost tier was the one missing. Neither coverage job declared
``timeout-minutes``, so both inherited GitHub's six-hour default while
the pull-request lane already runs for twelve minutes.

The two inner tiers are absent because there is no
``.config/nextest.toml`` to set them in: no per-test ``slow-timeout``
and no whole-run ``global-timeout``. The contract binds both the moment
one appears, so it arrives above the per-test allowance and inside the
watchdog rather than merely somewhere, and it reads the values from the
configuration rather than assuming them.

See "Test timeouts: one tier of four" in ``docs/developers-guide.md``,
and the canonical wording in `leynos/shared-actions`' `generate-coverage`
README.
"""

import typing as typ
from pathlib import Path

import pytest

from tests.support.coverage_workflows import (
    COVERAGE_ACTION,
    CoverageJob,
)
from tests.support.coverage_workflows import (
    coverage_jobs as read_coverage_jobs,
)
from tests.support.nextest_config import global_timeout
from tests.support.timeout_ordering import (
    ceiling_shortfalls,
    condition_violations,
    unset_watchdogs,
    unsized_watchdogs,
    whole_run_violations,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT: typ.Final[Path] = Path(__file__).resolve().parents[1]
NEXTEST_CONFIG: typ.Final[Path] = REPO_ROOT / ".config" / "nextest.toml"

#: Everything in a coverage job that is not a `cargo` invocation the
#: watchdog bounds: checkout, toolchain setup, and above all the cache
#: save and restore. The job timer covers it; the watchdog does not.
#:
#: Measured from the worst of many runs rather than one, and across runs
#: of every conclusion rather than successful ones only: a run cancelled
#: at its ceiling is the case the sizing exists to prevent. Across the
#: last 60 `smoke.yml` runs, 43 successful and 17 failed, the widest gap
#: between the coverage step and its job was 541 s on run 34069884428,
#: where the linting and the Python suite run outside the coverage step.
#: Across all 25 `coverage-main.yml` runs it was 98 s on run
#: 32946918439. Neither history holds a cancelled or timeout-terminated
#: run. Fifteen minutes covers the worse of those, and none of the runs
#: was genuinely cold.
OUTSIDE_WATCHDOG_ALLOWANCE_SECONDS: typ.Final[float] = 15 * 60.0

#: The watchdog every coverage step must declare, in seconds.
#:
#: Pinned by value rather than merely required to be present. A watchdog
#: of one second is present, is ordered below every ceiling above it, and
#: passes an assertion that only rejects absence, while terminating
#: `cargo` before the coverage step has begun. The sizing is the
#: repository's: stilyagi's trybuild-heavy suite and its maturin
#: extension build need this much headroom under cold instrumentation,
#: and both workflows say so where they set it.
REQUIRED_WATCHDOG_SECONDS: typ.Final[float] = 1800.0

#: The condition each coverage lane legitimately carries, keyed by
#: workflow and job, as a tuple of the step's ``if`` and its job's.
#:
#: A skipped step runs no `cargo`, so its watchdog never arms and every
#: assertion below says nothing about it. `if: false` on either the step
#: or the job would leave a lane that looks bounded and is not, and a
#: contract that ignored conditions would certify it. The values are
#: pinned rather than merely tolerated, because a lane gaining, losing
#: or changing a condition changes when it runs at all.
#:
#: `smoke.yml`'s coverage step is conditional because that workflow also
#: runs on pushes, where the release smoke matters and coverage does
#: not. `coverage-main.yml` is the trunk lane and runs unconditionally.
REQUIRED_CONDITIONS: typ.Final[dict[tuple[str, str], tuple[object, object]]] = {
    ("smoke.yml", "lint-test"): ("github.event_name == 'pull_request'", None),
    ("coverage-main.yml", "coverage-upload"): (None, None),
}

#: How far a ceiling must sit above the sum it contains, rather than
#: merely reaching it. A ceiling equal to that sum cancels the job at
#: the moment the watchdog would have reported the overrun, and the
#: report is the only thing that makes an overrun actionable.
CEILING_MARGIN_SECONDS: typ.Final[float] = 15 * 60.0

#: The ceiling both coverage jobs carry, as `docs/developers-guide.md`
#: records it. Pinned as well as derived: the derivation below would
#: accept anything above its 45-minute requirement, so a ceiling that
#: had drifted away from the guide would fail nothing.
REQUIRED_JOB_CEILING_SECONDS: typ.Final[float] = 60 * 60.0

#: Build time inside a `cargo` invocation before nextest starts its own
#: clock. Only used if a `global-timeout` appears.
COLD_BUILD_ALLOWANCE_SECONDS: typ.Final[float] = 10 * 60.0


@pytest.fixture(scope="module")
def coverage_jobs() -> tuple[CoverageJob, ...]:
    """Return every job invoking the coverage action, with its budgets.

    Jobs are the unit rather than steps, because the ceiling is a job's
    and it has to contain every watchdog inside it. Counting steps is
    what makes the two invocations here visible to the arithmetic.

    Returns
    -------
    tuple[CoverageJob, ...]
        One entry per coverage-invoking job.
    """
    return read_coverage_jobs()


@pytest.fixture(scope="module")
def nextest_config() -> str:
    """Return the nextest configuration file's text, or an empty string.

    This repository has no ``.config/nextest.toml``, which is the whole
    of why two tiers are missing. Returning an empty string rather than
    failing lets the tiers that do exist be asserted, and lets the two
    that do not be reported as absent rather than as a broken fixture.

    Returns
    -------
    str
        The file's contents, or an empty string when it does not exist.
    """
    if not NEXTEST_CONFIG.is_file():
        return ""
    return NEXTEST_CONFIG.read_text(encoding="utf-8")


def required_ceiling(budgets: cabc.Sequence[float], allowance: float) -> float:
    """Return the smallest acceptable ceiling for one job, in seconds.

    Three terms. Each coverage step may legitimately spend its whole
    watchdog, so the sum is the floor. The measured work outside those
    windows is added because the job timer covers it and the watchdogs
    do not. The margin is added because a ceiling equal to that sum
    cancels the job at the moment the watchdog would have reported the
    overrun.

    Parameters
    ----------
    budgets : cabc.Sequence[float]
        One watchdog budget per coverage step in the job.
    allowance : float
        The measured work outside those windows, in seconds.

    Returns
    -------
    float
        The smallest acceptable ceiling, in seconds.
    """
    return sum(budgets) + allowance + CEILING_MARGIN_SECONDS


def _ceiling_for(budgets: cabc.Sequence[float]) -> float:
    """Return one job's required ceiling with this repository's allowance."""
    return required_ceiling(budgets, OUTSIDE_WATCHDOG_ALLOWANCE_SECONDS)


def test_the_coverage_action_is_invoked_somewhere(
    coverage_jobs: tuple[CoverageJob, ...],
) -> None:
    """The contract needs a job to assert against.

    A repin or a rename that stopped the coordinate matching would
    otherwise turn every assertion below into a vacuous pass over an
    empty list, and the loss would look exactly like success.
    """
    assert coverage_jobs, (
        f"no workflow job uses {COVERAGE_ACTION}; either coverage moved or "
        f"this contract stopped recognizing it"
    )


def test_every_coverage_step_runs_under_an_explicit_watchdog(
    coverage_jobs: tuple[CoverageJob, ...],
) -> None:
    """The default is invisible, so every step must write it down.

    The action kills `cargo` after 1,800 s unless told otherwise, and the
    value here equals that default, which makes writing it down more
    important rather than less: an accidental deletion would change
    nothing observable until the run it killed.
    """
    missing = unset_watchdogs(coverage_jobs)
    assert not missing, f"these inherit the action's default: {missing}"


def test_every_watchdog_is_the_value_this_repository_sized(
    coverage_jobs: tuple[CoverageJob, ...],
) -> None:
    """Presence is not enough: a short watchdog passes every other test.

    The ordering assertions only ask that each tier sits below the one
    above it, so a watchdog of one second satisfies all of them and
    terminates `cargo` almost immediately. A value is the only thing
    that distinguishes a sized watchdog from an arbitrary one, and the
    sizing is written down in both workflows.
    """
    wrong = unsized_watchdogs(coverage_jobs, REQUIRED_WATCHDOG_SECONDS)
    assert not wrong, f"these are not {REQUIRED_WATCHDOG_SECONDS:g} s: {wrong}"


def test_the_job_ceiling_contains_every_watchdog_and_the_work_around_them(
    coverage_jobs: tuple[CoverageJob, ...],
) -> None:
    """Tier four must not pre-empt tier three, for any of the invocations.

    Each coverage step gets its own watchdog, so a job running the action
    twice can legitimately spend both budgets, and its ceiling has to
    contain the sum rather than one of them. The clocks do not start
    together either: the job timer starts before the checkout and runs
    through the cache saves afterwards, which on Windows are the largest
    thing in the job outside the coverage steps themselves.

    A ceiling merely above one watchdog cancels the job partway through
    the second invocation, and a cancellation discards the log that would
    have explained it.
    """
    short = ceiling_shortfalls(coverage_jobs, _ceiling_for)
    assert not short, f"an overrun would be cancelled, not reported: {short}"


def test_each_coverage_job_carries_the_documented_ceiling(
    coverage_jobs: tuple[CoverageJob, ...],
) -> None:
    """The value is the guide's, not merely something above the requirement.

    The derivation above is satisfied by any ceiling over 45 minutes, so
    on its own it would let the value drift away from the table in
    `docs/developers-guide.md` without failing anything. Pinning it makes
    the guide and the workflows one statement.
    """
    wrong = {
        str(job): job.job_timeout
        for job in coverage_jobs
        if job.job_timeout != REQUIRED_JOB_CEILING_SECONDS
    }
    assert not wrong, (
        f"these coverage jobs do not carry the documented "
        f"{REQUIRED_JOB_CEILING_SECONDS / 60:.0f}-minute ceiling: {wrong}; "
        f"change the developers' guide with them or change them back"
    )


def test_a_whole_run_budget_would_sit_inside_each_watchdog(
    coverage_jobs: tuple[CoverageJob, ...], nextest_config: str
) -> None:
    """Tier three must not pre-empt tier two, if tier two appears.

    No ``global-timeout`` is set today, so this asserts nothing about the
    current tree and is not a licence to leave it that way: the guide
    records the gap. What it does is bind the value the moment one is
    added, so it arrives above the largest per-test allowance and inside
    the watchdog rather than merely somewhere.
    """
    if global_timeout(nextest_config) is None:
        pytest.skip("no global-timeout is set; the guide records this as a gap")
    wrong = whole_run_violations(
        coverage_jobs, nextest_config, COLD_BUILD_ALLOWANCE_SECONDS
    )
    assert not wrong, f"the whole-run budget would pre-empt a tier: {wrong}"


def test_each_coverage_lane_carries_the_condition_it_is_meant_to(
    coverage_jobs: tuple[CoverageJob, ...],
) -> None:
    """A skipped step runs no `cargo`, so its watchdog never arms.

    Every assertion above reads a lane's declared budgets and says
    nothing about whether the step runs. `if: false` on the step or on
    its job would leave a lane that looks bounded and is not, and this
    contract would certify it. So would a plausible condition that
    quietly excluded the event the lane exists for.

    The conditions are pinned rather than forbidden, because both are
    legitimate here: `smoke.yml` also runs on pushes, where the release
    smoke matters and coverage does not. Pinning them means a lane
    gaining, losing or changing one has to change this contract and the
    guide with it.

    The coordinate sets are compared both ways before the values are. A
    lane nobody listed is a lane whose condition nothing checks, so a
    new coverage job could arrive carrying `if: false` and pass; a
    listed lane that has stopped invoking the action is the opposite
    loss. Both are reported by name.
    """
    wrong = condition_violations(coverage_jobs, REQUIRED_CONDITIONS)
    assert not wrong, f"these lanes differ from the guide's conditions: {wrong}"
