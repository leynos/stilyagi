"""The pull-request lane as a closure, not a trigger list.

Separated from ``test_workflow_reader_units`` so neither module
outgrows the 400-line limit the lint gate enforces, and because the
subject is its own: which workflows a pull request can actually reach.

A workflow declaring only ``workflow_call`` still runs on a pull
request when a pull-request workflow calls it, and ``secrets: inherit``
hands it the token. A reading that enumerated triggers alone could not
see it, so every refusal built on that enumeration passed over it while
it did the forbidden thing. Measured on episodic, where a probe of the
shape below passed every clause of the equivalent contract.

Run via `make test`.
"""

import typing as typ

import pytest

from tests.support.codescene_coverage import called_workflows, pull_request_workflows
from tests.support.workflow_secrets import secret_sites
from tests.support.workflows import load_workflow, serves_pull_requests

#: A minimal workflow body, so each case below varies one thing.
JOBS: typ.Final[str] = "jobs:\n  a:\n    steps: []\n"


#: A workflow that declares only `workflow_call` and reaches CodeScene
#: with whatever secret it was handed. It names no CodeScene action and
#: runs no `cs-coverage`, so every clause but the token one is blind to
#: it even once it is enumerated; the token clause is what catches it,
#: and only if this workflow is in the pull-request closure at all.
PROBE: typ.Final[str] = (
    "on:\n  workflow_call:\n"
    "jobs:\n  probe:\n    steps:\n"
    "      - run: |\n"
    '          curl -H "Authorization: ${{ secrets.CS_ACCESS_TOKEN }}" \\\n'
    "            https://api.codescene.io/v2/projects/1\n"
)


@pytest.mark.parametrize(
    "prefix",
    [pytest.param("./", id="dot-slash"), pytest.param("$/", id="dollar-slash")],
)
def test_the_pull_request_lane_reaches_a_called_workflow(prefix: str) -> None:
    """The lane is a closure, not a trigger list.

    A workflow declaring only `workflow_call` runs on a pull request
    when a pull-request workflow calls it, and `secrets: inherit` hands
    it the token. Enumerating triggers alone cannot see it, so every
    refusal built on that enumeration passes over it while it does the
    forbidden thing. Measured on episodic: a probe of exactly this shape
    passed every clause of the equivalent contract there.

    Both spellings are covered because GitHub accepts both and a reader
    knowing only `./` silently drops callers written the other way.
    Parametrised rather than combined, so each spelling fails on its own
    and neither can be carried by the other.
    """
    caller = load_workflow(
        "on:\n  pull_request:\n"
        "jobs:\n  call:\n"
        f"    uses: {prefix}.github/workflows/probe.yml\n"
        "    secrets: inherit\n"
    )
    documents = {"ci.yml": caller, "probe.yml": load_workflow(PROBE)}
    assert called_workflows(caller, documents) == frozenset({"probe.yml"}), (
        f"the {prefix!r} spelling must resolve to the called workflow"
    )
    assert sorted(pull_request_workflows(documents)) == ["ci.yml", "probe.yml"], (
        "the called workflow runs on a pull request and must be enumerated "
        "as part of that lane"
    )


def test_a_workflow_nothing_calls_is_not_in_the_lane() -> None:
    """Assert the closure is narrow as well as transitive.

    A traversal that swept in every `workflow_call` document, rather
    than the ones a pull-request workflow actually calls, would hold
    workflows the lane never runs to the lane's rules, and the refusals
    would then fail a repository that complies.
    """
    documents = {
        "ci.yml": load_workflow(f"on:\n  pull_request:\n{JOBS}"),
        "probe.yml": load_workflow(PROBE),
    }
    assert sorted(pull_request_workflows(documents)) == ["ci.yml"], (
        "a reusable workflow no pull-request lane calls is not in the lane"
    )


def test_a_call_to_another_repository_is_not_followed() -> None:
    """What is not in this tree cannot be read, and is not claimed to be.

    Following a reference to another repository would mean asserting
    over content this reading does not have. Saying plainly that it is
    out of scope is better than a silent pass that looks like coverage.
    """
    caller = load_workflow(
        "on:\n  pull_request:\n"
        "jobs:\n  call:\n"
        "    uses: other/repo/.github/workflows/probe.yml@main\n"
    )
    documents = {"ci.yml": caller, "probe.yml": load_workflow(PROBE)}
    assert called_workflows(caller, documents) == frozenset(), (
        "a cross-repository call names a document this reading does not hold"
    )


def test_the_probe_is_caught_once_the_lane_includes_it() -> None:
    """The closure is only worth having if a clause then fails on it.

    This is the measurement the whole change rests on. The probe names
    no CodeScene action and runs no `cs-coverage`, so those two clauses
    are blind to it either way; what catches it is the secret sweep,
    and only because the closure puts it in the lane at all.

    Asserted in both directions in one place: the probe is a site when
    enumerated, and the trigger-only reading never reaches it.
    """
    caller = load_workflow(
        "on:\n  pull_request:\n"
        "jobs:\n  call:\n"
        "    uses: ./.github/workflows/probe.yml\n"
        "    secrets: inherit\n"
    )
    documents = {"ci.yml": caller, "probe.yml": load_workflow(PROBE)}

    trigger_only = [
        name for name, document in documents.items() if serves_pull_requests(document)
    ]
    assert trigger_only == ["ci.yml"], (
        "the premise: enumerating triggers alone does not reach the probe"
    )

    lane = pull_request_workflows(documents)
    offenders = sorted(
        site for name, document in lane.items() for site in secret_sites(name, document)
    )
    assert offenders == [
        "ci.yml: job call secrets: inherit",
        "probe.yml: job probe step 1 run",
    ], (
        f"the closure must put the probe in reach of the secret clause, and "
        f"the caller's `secrets: inherit` with it; it found {offenders}"
    )
