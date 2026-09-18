"""CV-005: CodeScene coverage belongs to main, and to main alone.

Concordat rule `main-owned-codescene-coverage`. One workflow uploads
coverage to CodeScene, it is the one that runs on pushes to main, and no
workflow serving pull requests names a CodeScene action, invokes
`cs-coverage`, or receives `CS_ACCESS_TOKEN`.

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

Each assertion here is proved by putting the forbidden element back.

Run via `make test`.
"""

import pytest

from tests.support.codescene_coverage import (
    CLI_COMMAND,
    CODESCENE_ACTION,
    COVERAGE_ACTION,
    PINNED_COMMIT,
    coverage_steps,
    documents,
    publishers,
    pull_request_workflows,
)
from tests.support.workflow_secrets import FORBIDDEN_VARIABLE, token_sites
from tests.support.workflows import load_workflow, triggers, workflow_steps


def test_no_pull_request_workflow_names_the_codescene_action() -> None:
    """The upload action belongs to the main publisher alone.

    Matched on the action's path rather than on the word `CodeScene`,
    because both workflows discuss the policy in prose and a comment
    explaining why a step is absent must not read as the step.
    """
    offenders = sorted(
        f"{name}: {step.get('uses')}"
        for name, document in pull_request_workflows().items()
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    assert not offenders, (
        f"these pull-request lanes invoke {CODESCENE_ACTION}; CV-005 puts "
        f"the upload and the changed-line check on the push-to-main "
        f"publisher alone: {offenders}"
    )


def test_no_pull_request_workflow_receives_the_access_token() -> None:
    """A token no fork can read is a gate no fork is held to.

    Swept at every level, because the variable can be set on the
    workflow, on a job or on a step, handed to an action as an input,
    or referenced inside a `run` body, and all five reach a process.
    The name is what matters; the expression supplying it may be a
    secret, a variable or a literal.
    """
    offenders = sorted(
        site
        for name, document in pull_request_workflows().items()
        for site in token_sites(name, document)
    )
    assert not offenders, (
        f"these pull-request lanes put {FORBIDDEN_VARIABLE} in reach; a fork "
        f"cannot read it, so the gate it guards is skipped for exactly the "
        f"contributions least likely to have been measured: {offenders}"
    )


def test_the_token_sweep_reads_structure_rather_than_prose() -> None:
    """Assert the sweep above is narrow as well as sufficient.

    Its first version matched the raw file text and failed on the
    comment that explains why the step was removed, which would have
    left the next person deleting the explanation to make the contract
    pass. A comment is not a token, and a rule that cannot tell them
    apart teaches the wrong lesson.

    Both directions are driven here, because the repository's own files
    only exercise one of them.
    """
    explained = load_workflow(
        "on:\n  pull_request:\n"
        "jobs:\n  a:\n    steps:\n"
        f"      - run: echo hi  # no {FORBIDDEN_VARIABLE} here, deliberately\n"
    )
    assert token_sites("explained.yml", explained) == [], (
        "a comment naming the token is not the token being set"
    )
    for fragment, where in (
        (
            f"env:\n  {FORBIDDEN_VARIABLE}: x\njobs:\n  a:\n    steps: []\n",
            "workflow env",
        ),
        (
            f"jobs:\n  a:\n    env:\n      {FORBIDDEN_VARIABLE}: x\n    steps: []\n",
            "job a env",
        ),
        (
            (
                "jobs:\n  a:\n    steps:\n      - env:\n"
                f"          {FORBIDDEN_VARIABLE}: x\n"
            ),
            "job a step 1 env",
        ),
        (
            (
                "jobs:\n  a:\n    steps:\n      - with:\n"
                f"          token: ${{{{ secrets.{FORBIDDEN_VARIABLE} }}}}\n"
            ),
            "job a step 1 inputs",
        ),
        (
            f"jobs:\n  a:\n    steps:\n      - run: echo ${FORBIDDEN_VARIABLE}\n",
            "job a step 1 run",
        ),
    ):
        document = load_workflow("on:\n  pull_request:\n" + fragment)
        assert token_sites("x.yml", document) == [f"x.yml: {where}"], (
            f"the sweep must find the token at {where} in {fragment!r}"
        )


def test_no_pull_request_workflow_runs_the_cli() -> None:
    """The action is not the only way to reach the tool.

    A `run:` step invoking `cs-coverage` directly is the same gate
    wearing different clothes, and a rule naming only the action would
    read it as compliance.
    """
    offenders = sorted(
        f"{name}: {str(step.get('run', ''))[:60]}"
        for name, document in pull_request_workflows().items()
        for step in workflow_steps(document)
        if CLI_COMMAND in str(step.get("run", ""))
    )
    assert not offenders, (
        f"these pull-request lanes run {CLI_COMMAND} directly: {offenders}"
    )


def test_exactly_one_workflow_publishes_coverage() -> None:
    """One publisher, so the baseline has one writer.

    Two would race on the ratchet baseline, and which one a pull request
    then compared against would depend on which finished last. None
    would leave every pull request ratcheting against a baseline nobody
    writes, which passes silently and measures nothing.
    """
    found = publishers()
    uploading = sorted(
        name
        for name, document in documents().items()
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    assert len(found) == 1, (
        f"expected exactly one workflow that pushes to main and serves no "
        f"pull request; found {sorted(found)}"
    )
    assert uploading == sorted(found), (
        f"the workflows invoking {CODESCENE_ACTION} must be exactly the "
        f"publisher; the publisher is {sorted(found)} and the "
        f"uploaders are {uploading}"
    )


def test_the_publisher_uploads_rather_than_checks() -> None:
    """The mode is named, not left to the action's default.

    `mode` decides whether the step uploads a report or gates a pull
    request against one, and the default has changed before. Naming it
    is how this file's reader knows which of the two this step does
    without reading the action.
    """
    ((name, document),) = publishers().items()
    steps = [
        step
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    ]
    assert len(steps) == 1, f"{name} must invoke the action once; found {len(steps)}"
    inputs = steps[0].get("with") or {}
    assert isinstance(inputs, dict), (
        f"the step's `with:` block is not a mapping: {inputs!r}"
    )
    assert inputs.get("mode") == "upload", (
        f"{name}'s CodeScene step must name `mode: upload`; it names "
        f"{inputs.get('mode')!r}"
    )


def test_the_publisher_passes_no_deprecated_checksum() -> None:
    """The old checksum input fails the run outright.

    `installer-checksum` is rejected when non-empty from this pin, and
    `archive-checksum` is not a rename of it: it digests the manifest
    archive, while the repository variable the old input carried holds
    the installer script's digest. Carrying the value across under the
    new name would fail every run, so neither input is passed and the
    action's own manifest pins the CLI instead.
    """
    ((name, document),) = publishers().items()
    inputs = next(
        step.get("with") or {}
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    assert isinstance(inputs, dict), (
        f"the step's `with:` block is not a mapping: {inputs!r}"
    )
    for rejected in ("installer-checksum", "archive-checksum"):
        assert rejected not in inputs, (
            f"{name} passes {rejected!r}; `installer-checksum` is rejected "
            f"when non-empty and `archive-checksum` digests a different "
            f"artefact from the variable this repository holds, so neither "
            f"carries the old value safely"
        )


def test_both_coverage_lanes_name_one_pinned_commit() -> None:
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
    steps = coverage_steps()
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


def test_the_pull_request_lane_ratchets_and_publishes_nothing() -> None:
    """What a pull request keeps, and what it must not do.

    The ratchet is the gate. The artefact is the publisher's, and two
    uploads of one name from two lanes is a race whose winner depends on
    which finished last.
    """
    pull_request_lanes = set(pull_request_workflows())
    lanes = {
        name: step
        for name, step in coverage_steps().items()
        if name in pull_request_lanes
    }
    assert lanes, "no pull-request lane generates coverage; the reader is broken"
    for name, step in lanes.items():
        inputs = step.get("with") or {}
        assert isinstance(inputs, dict), (
            f"the step's `with:` block is not a mapping: {inputs!r}"
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


def test_the_two_selections_match() -> None:
    """A ratchet against a differently-built baseline measures the runs.

    The pull-request report is compared with the baseline the publisher
    wrote, so the inputs deciding *what* is measured have to agree. A
    format, runner or feature difference makes the comparison report the
    difference between two builds rather than between two commits, and
    it does so without any error.

    `publish-artefact` is excluded because it decides what happens to
    the report afterwards rather than what goes into it, and the two
    lanes differ on it deliberately.
    """
    steps = coverage_steps()
    (publisher,) = publishers()
    selection = {"output-path", "format", "use-cargo-nextest", "with-ratchet"}
    baseline = {
        key: value
        for key, value in (steps[publisher].get("with") or {}).items()
        if key in selection
    }
    assert baseline, f"{publisher}'s coverage step declares no selection to match"
    for name, step in steps.items():
        if name == publisher:
            continue
        theirs = {
            key: value
            for key, value in (step.get("with") or {}).items()
            if key in selection
        }
        assert theirs == baseline, (
            f"{name}'s coverage selection differs from the baseline "
            f"{publisher} publishes, so the ratchet would compare two "
            f"differently built reports: {theirs} against {baseline}"
        )


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("on:\n  pull_request:\n", {"pull_request"}, id="mapping"),
        pytest.param("'on':\n  pull_request:\n", {"pull_request"}, id="quoted-key"),
        pytest.param("on: [pull_request, push]", {"pull_request", "push"}, id="list"),
        pytest.param("on: pull_request", {"pull_request"}, id="bare-string"),
        pytest.param("on:\n  push:\n    branches: [main]\n", {"push"}, id="push-only"),
    ],
)
def test_the_trigger_reader_handles_every_spelling(
    document: str, expected: set[str]
) -> None:
    """Assert the reader on documents this repository does not contain.

    Every rule above derives its subject from the triggers, so a reader
    that returns nothing makes all of them pass over an empty set. That
    failure reports compliance rather than an error, which is why it is
    driven here with constructed documents: the real workflows all use
    one spelling, so they cannot tell a working reader from a broken
    one.

    The quoted-key case is the sharp one. YAML 1.1 resolves an unquoted
    `on:` to the boolean `True`, so a loader that resolves scalars keys
    every workflow under `True` and none under `on`. This repository's
    `load_workflow` uses `yaml.BaseLoader` and keeps the string, and the
    reader looks under both, so neither choice can silently empty the
    contract.
    """
    assert triggers(load_workflow(document)) == expected, (
        f"the reader must find {sorted(expected)} in {document!r}"
    )


def test_the_trigger_reader_survives_a_resolving_loader() -> None:
    """The `on` key can arrive as a boolean, and the reader must cope.

    Written against `yaml.safe_load` rather than the repository's
    helper, because the hazard is a property of the loader rather than
    of the document: swapping `load_workflow` to a resolving loader is
    a one-word change that would otherwise empty every rule in this file
    while every assertion still passed.
    """
    import yaml

    document = yaml.safe_load("on:\n  pull_request:\n  push:\n    branches: [main]\n")
    assert True in document, (
        "this case only means something while a resolving loader keys an "
        "unquoted `on:` under the boolean; if PyYAML changes, delete it"
    )
    assert triggers(document) == {"pull_request", "push"}, (
        "the reader must find the triggers under the boolean key too"
    )
