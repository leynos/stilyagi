"""CV-005: CodeScene coverage belongs to main, and to main alone.

Concordat rule `main-owned-codescene-coverage`. One workflow uploads
coverage to CodeScene, it is the one that runs on pushes to main, and no
workflow serving pull requests names a CodeScene action, invokes
`cs-coverage`, or puts `CS_ACCESS_TOKEN` in reach of any process.

The rule is a policy rather than a gap, and the reasons are worth
keeping beside the assertions. A pull request from a fork cannot read
`CS_ACCESS_TOKEN`, so a changed-line check on that lane was a silent
skip for exactly the contributions least likely to have been measured.
On a branch it put a second tool on the critical path, and when that
tool's unpinned CLI stopped parsing cobertura the check failed every
pull request in six repositories for two days over a defect in none of
them. The ratchet applies the same gate from the repository's own
baseline and needs no token.

What a pull-request lane keeps is `generate-coverage` with
`with-ratchet`, against the baseline the main publisher writes. The two
selections have to match field for field: the ratchet compares this
commit's report with that baseline, so a difference in format, runner
or feature set makes the comparison measure the difference between two
runs rather than between two commits.

The repository's own workflows reach these tests through one fixture,
and every reading below is a pure function over supplied documents. The
constructed cases matter as much as the real ones: the real files use a
single spelling of everything, so they cannot tell a working reader
from a broken one, and each rule here is satisfied by a reading that
finds nothing.

Each assertion is proved by putting the forbidden element back.

Run via `make test`.
"""

import typing as typ

from tests.support.codescene_coverage import (
    CLI_COMMAND,
    CODESCENE_ACTION,
    COVERAGE_ACTION,
    PINNED_COMMIT,
    coverage_steps,
    publishers,
    pull_request_workflows,
)
from tests.support.workflow_secrets import FORBIDDEN_VARIABLE, secret_sites
from tests.support.workflows import workflow_steps

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument


#: The selection inputs that decide what a coverage run measures, as
#: opposed to what happens to the report afterwards.
SELECTION: typ.Final[frozenset[str]] = frozenset({
    "output-path",
    "format",
    "use-cargo-nextest",
    "with-ratchet",
})


def test_no_pull_request_workflow_names_the_codescene_action(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The upload action belongs to the main publisher alone.

    Matched on the action's path rather than on the word `CodeScene`,
    because both workflows discuss the policy in prose and a comment
    explaining why a step is absent must not read as the step.
    """
    offenders = sorted(
        f"{name}: {step.get('uses')}"
        for name, document in pull_request_workflows(documents).items()
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    assert not offenders, (
        f"these pull-request lanes invoke {CODESCENE_ACTION}; CV-005 puts "
        f"the upload and the changed-line check on the push-to-main "
        f"publisher alone: {offenders}"
    )


def test_no_pull_request_workflow_puts_the_secret_in_reach(
    documents: dict[str, WorkflowDocument],
) -> None:
    """A token no fork can read is a gate no fork is held to.

    Swept at every level, because the secret reaches a process by more
    routes than an `env` key: a value under any key at all, an action's
    inputs, a `run` body, and a reusable-workflow call forwarding it by
    name or by `inherit`.
    """
    offenders = sorted(
        site
        for name, document in pull_request_workflows(documents).items()
        for site in secret_sites(name, document)
    )
    assert not offenders, (
        f"these pull-request lanes put {FORBIDDEN_VARIABLE} in reach; a "
        f"fork cannot read it, so the gate it guards is skipped for exactly "
        f"the contributions least likely to have been measured: {offenders}"
    )


def test_no_pull_request_workflow_runs_the_cli(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The action is not the only way to reach the tool.

    A `run:` step invoking `cs-coverage` directly is the same gate
    wearing different clothes, and a rule naming only the action would
    read it as compliance.
    """
    offenders = sorted(
        f"{name}: {str(step.get('run', ''))[:60]}"
        for name, document in pull_request_workflows(documents).items()
        for step in workflow_steps(document)
        if CLI_COMMAND in str(step.get("run", ""))
    )
    assert not offenders, (
        f"these pull-request lanes run {CLI_COMMAND} directly: {offenders}"
    )


def test_exactly_one_workflow_publishes_coverage(
    documents: dict[str, WorkflowDocument],
) -> None:
    """One publisher, so the baseline has one writer.

    Two would race on the ratchet baseline, and which one a pull request
    then compared against would depend on which finished last. None
    would leave every pull request ratcheting against a baseline nobody
    writes, which passes silently and measures nothing.
    """
    found = publishers(documents)
    uploading = sorted(
        name
        for name, document in documents.items()
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    assert len(found) == 1, (
        f"expected exactly one workflow that pushes to main and serves no "
        f"pull request; found {sorted(found)}"
    )
    assert uploading == sorted(found), (
        f"the workflows invoking {CODESCENE_ACTION} must be exactly the "
        f"publisher; the publisher is {sorted(found)} and the uploaders "
        f"are {uploading}"
    )


def test_both_coverage_lanes_name_one_pinned_commit(
    documents: dict[str, WorkflowDocument],
) -> None:
    """One commit across the repository, and a commit rather than a branch.

    The SHA is not named. Section 6f of the developers' guide is
    explicit that a contract asserting a caller's exact commit makes
    every Dependabot bump a manual edit, so what is held here is the
    shape and the agreement: each reference is pinned to a full
    forty-character commit rather than a mutable branch, and the two
    lanes name the same one.

    The agreement is the part that matters for the ratchet. A pull
    request's coverage is compared against the baseline main published,
    so the two lanes running different versions of the generator is a
    comparison between two tools, and a partial repin is invisible in a
    diff that moves the other lane.
    """
    steps = coverage_steps(documents)
    assert steps, "no workflow invokes the coverage action; the reader is broken"
    pins: dict[str, str] = {}
    for name, step in steps.items():
        reference = str(step.get("uses", ""))
        prefix = f"{COVERAGE_ACTION}@"
        assert reference.startswith(prefix), (
            f"{name} must call {COVERAGE_ACTION} by path; it calls {reference!r}"
        )
        pin = reference[len(prefix) :]
        assert PINNED_COMMIT.match(pin), (
            f"{name} pins {pin!r}, which is not a full forty-character "
            f"commit; a branch or a tag moves under the workflow"
        )
        pins[name] = pin
    assert len(set(pins.values())) == 1, (
        f"the coverage lanes name different commits, so a pull request's "
        f"ratchet would compare reports built by two versions of the "
        f"generator: {pins}"
    )


def test_the_pull_request_lane_ratchets_and_publishes_nothing(
    documents: dict[str, WorkflowDocument],
) -> None:
    """What a pull request keeps, and what it must not do.

    The ratchet is the gate. The artefact is the publisher's, and two
    uploads of one name from two lanes is a race whose winner depends on
    which finished last.
    """
    pull_request_lanes = set(pull_request_workflows(documents))
    lanes = {
        name: step
        for name, step in coverage_steps(documents).items()
        if name in pull_request_lanes
    }
    assert lanes, "no pull-request lane generates coverage; the reader is broken"
    for name, step in lanes.items():
        inputs = step.get("with") or {}
        assert isinstance(inputs, dict), (
            f"{name}'s coverage step declares a `with:` block that is not a "
            f"mapping: {inputs!r}"
        )
        assert inputs.get("with-ratchet") == "true", (
            f"{name} must generate coverage with `with-ratchet: 'true'`; the "
            f"ratchet is the whole of the coverage gate on this lane. It "
            f"sets {inputs.get('with-ratchet')!r}"
        )
        assert inputs.get("publish-artefact") == "false", (
            f"{name} must set `publish-artefact: 'false'`; the publisher "
            f"owns the artefact and two uploads of one name race. It sets "
            f"{inputs.get('publish-artefact')!r}"
        )


def test_the_two_selections_match(
    documents: dict[str, WorkflowDocument],
) -> None:
    """A ratchet against a differently-built baseline measures the runs.

    The pull-request report is compared with the baseline the publisher
    wrote, so the inputs that decide *what* is measured must agree
    between the two lanes: the output path, the format, the runner, and
    the feature set. A difference there makes the comparison report the
    difference between two builds rather than between two commits, and
    it does so without any error.

    `publish-artefact` is excluded because it decides what happens to
    the report afterwards rather than what goes into it, and the two
    lanes differ on it deliberately.
    """
    steps = coverage_steps(documents)
    (publisher,) = publishers(documents)
    baseline = {
        key: value
        for key, value in (steps[publisher].get("with") or {}).items()
        if key in SELECTION
    }
    assert baseline, f"{publisher}'s coverage step declares no selection to match"
    for name, step in steps.items():
        if name == publisher:
            continue
        theirs = {
            key: value
            for key, value in (step.get("with") or {}).items()
            if key in SELECTION
        }
        assert theirs == baseline, (
            f"{name}'s coverage selection differs from the baseline "
            f"{publisher} publishes, so the ratchet would compare two "
            f"differently built reports: {theirs} against {baseline}"
        )
