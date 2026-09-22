"""The timeout-ordering rules, driven with jobs the tree does not contain.

`test_timeout_ordering_contract` asserts that each rule finds nothing in
this repository's workflows. That is satisfied by a rule that can never
find anything, so each is driven here with a job or a configuration
built to break it, and with one built to pass it. The whole-run rule
matters most: no `global-timeout` is set today, so its reading is never
reached from the real configuration at all.
"""

import pytest

from tests.support.coverage_workflows import CoverageJob
from tests.support.timeout_ordering import (
    ceiling_shortfalls,
    condition_violations,
    unset_watchdogs,
    unsized_watchdogs,
    whole_run_violations,
)

#: A per-test budget of two minutes: a 60-second period, terminated after two.
BOUNDED: str = (
    '[profile.default]\nslow-timeout = { period = "60s", terminate-after = 2 }\n'
)


def job(
    *watchdogs: float | None,
    timeout: float | None = 3600.0,
    conditions: tuple[tuple[object, object], ...] = (),
) -> CoverageJob:
    """Return a coverage job with those watchdogs, one step per watchdog."""
    return CoverageJob(
        "ci.yml", "cover", len(watchdogs), watchdogs, timeout, conditions
    )


def test_a_step_without_a_watchdog_is_reported_and_a_set_one_is_not() -> None:
    """Only the step that inherits the action's default is named."""
    assert unset_watchdogs([job(None, 1800.0)]) == ["ci.yml:cover: step 1 of 2"], (
        "the step setting no watchdog is the one reported"
    )
    assert unset_watchdogs([job(1800.0, 1800.0)]) == [], "set watchdogs pass"


def test_a_watchdog_other_than_the_sized_value_is_reported() -> None:
    """Presence is not the rule; the value is."""
    assert unsized_watchdogs([job(1800.0, 900.0)], 1800.0) == [
        "ci.yml:cover: step 2 of 2 sets 900 s"
    ], "the step setting a shorter watchdog is named with its value"
    assert unsized_watchdogs([job(1800.0, None)], 1800.0) == [], (
        "an unset watchdog is the other rule's to report"
    )


@pytest.mark.parametrize(
    ("timeout", "expected"),
    [
        pytest.param(None, ["ci.yml:cover has no timeout-minutes"], id="no-ceiling"),
        pytest.param(
            3000.0,
            [
                (
                    "ci.yml:cover has a ceiling of 3000s, below the 3600s needed "
                    "to contain 2 watchdog(s)"
                )
            ],
            id="short-ceiling",
        ),
        pytest.param(3600.0, [], id="sufficient-ceiling"),
    ],
)
def test_a_ceiling_must_contain_every_watchdog(
    timeout: float | None, expected: list[str]
) -> None:
    """The ceiling is compared with the sum of the job's budgets, not one."""
    found = ceiling_shortfalls([job(1800.0, 1800.0, timeout=timeout)], sum)
    assert found == expected, f"a {timeout} s ceiling over two 1800 s watchdogs"


def test_no_whole_run_budget_means_no_tier_to_order() -> None:
    """Absent is not a violation; the guide records it as a gap."""
    assert whole_run_violations([job(1800.0)], BOUNDED, 600.0) == [], (
        "a configuration with no global-timeout has nothing to order"
    )


def test_a_whole_run_budget_inside_the_watchdog_passes() -> None:
    """Five minutes, termination and a cold build all fit in thirty."""
    config = BOUNDED + 'global-timeout = "5m"\n'
    assert whole_run_violations([job(1800.0)], config, 600.0) == [], (
        "a five-minute whole-run budget sits inside a thirty-minute watchdog"
    )


def test_a_whole_run_budget_the_watchdog_cannot_cover_is_reported() -> None:
    """Forty minutes of tests cannot finish inside a thirty-minute watchdog."""
    config = BOUNDED + 'global-timeout = "40m"\n'
    found = whole_run_violations([job(1800.0, None)], config, 600.0)
    assert [entry.split(" sets ")[0] for entry in found] == [
        "ci.yml:cover step 1",
        "ci.yml:cover step 2",
    ], f"both steps are below the requirement, the unset one too: {found}"


def test_a_whole_run_budget_below_one_test_is_reported() -> None:
    """The run must outlast the longest single test it allows."""
    config = BOUNDED + 'global-timeout = "90s"\n'
    found = whole_run_violations([job(1800.0)], config, 600.0)
    assert found == [
        "the 90s global-timeout is not above the 120s largest per-test allowance"
    ], f"a 90 s run cannot hold a 120 s test: {found}"


def test_the_condition_rule_names_every_kind_of_difference() -> None:
    """Unlisted, missing and differing lanes are each reported by name."""
    required = {
        ("ci.yml", "cover"): ("github.event_name == 'pull_request'", None),
        ("main.yml", "publish"): (None, None),
    }
    jobs = [
        job(1800.0, conditions=(("false", None),)),
        CoverageJob("extra.yml", "cover", 1, (1800.0,), 3600.0, ((None, None),)),
    ]
    assert condition_violations(jobs, required) == [
        "('extra.yml', 'cover') is not listed",
        "('main.yml', 'publish') no longer invokes the coverage action",
        (
            "('ci.yml', 'cover') carries [\"('false', None)\"], not "
            "(\"github.event_name == 'pull_request'\", None)"
        ),
    ], "each difference is reported once, by lane"


def test_the_condition_rule_passes_the_pinned_conditions() -> None:
    """Assert the rule is narrow as well as sufficient."""
    required = {("ci.yml", "cover"): (None, None)}
    assert (
        condition_violations([job(1800.0, conditions=((None, None),))], required) == []
    ), "a lane carrying exactly its pinned condition passes"
