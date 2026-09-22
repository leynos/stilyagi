"""The workflow readers, driven on documents this repository does not have.

Every rule in `test_codescene_coverage_contract` derives its subject
from these readings, and each of those rules is a refusal. A refusal
over an empty subject set is satisfied by any repository at all, so a
reader that quietly finds nothing does not report an error and does not
report zero: it reports compliance.

The real workflows cannot catch that. They use one spelling of
`on:`, one push filter and one job shape, so they exercise one path
through each reader and agree with a broken one as readily as with a
working one. These cases are constructed for that reason, and the error
paths are here too, since a reading that raises where it should answer
is the same defect pointing the other way.

Run via `make test`.
"""

import typing as typ

if typ.TYPE_CHECKING:
    import pathlib

import pytest

from tests.support.codescene_coverage import (
    WorkflowReadingError,
    coverage_steps,
    publishers,
    pull_request_workflows,
    read_workflows,
)
from tests.support.workflows import (
    load_workflow,
    pushes_to_main,
    serves_pull_requests,
    triggers,
    workflow_steps,
)

#: A minimal workflow body, so each case below varies one thing.
JOBS: typ.Final[str] = "jobs:\n  a:\n    steps: []\n"


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        pytest.param("on:\n  pull_request:\n", {"pull_request"}, id="mapping"),
        pytest.param("'on':\n  pull_request:\n", {"pull_request"}, id="quoted-key"),
        pytest.param("on: [pull_request, push]", {"pull_request", "push"}, id="list"),
        pytest.param("on: pull_request", {"pull_request"}, id="bare-string"),
        pytest.param("on:\n  push:\n    branches: [main]\n", {"push"}, id="push-only"),
        pytest.param("name: x\n", set(), id="no-triggers"),
    ],
)
def test_the_trigger_reader_handles_every_spelling(
    document: str, expected: set[str]
) -> None:
    """Assert the reader on documents this repository does not contain.

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
    a one-word change that would otherwise empty every rule built on
    these readings while every assertion still passed.
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


@pytest.mark.parametrize(
    ("filters", "expected", "why"),
    [
        pytest.param("", True, "a bare push runs for every branch", id="bare"),
        pytest.param(
            "\n    branches: [main]", True, "main is named", id="branches-main"
        ),
        pytest.param(
            "\n    branches: main", True, "a scalar names main", id="branches-scalar"
        ),
        pytest.param(
            "\n    branches: [release]", False, "main is not named", id="branches-other"
        ),
        pytest.param(
            "\n    branches-ignore: [main]",
            False,
            "main is excluded",
            id="branches-ignore-main",
        ),
        pytest.param(
            "\n    branches-ignore: [wip]",
            True,
            "main is not excluded",
            id="branches-ignore-other",
        ),
        pytest.param(
            "\n    tags: ['v*']", False, "a tag push is not a branch push", id="tags"
        ),
        pytest.param(
            "\n    tags-ignore: ['v*']",
            False,
            "a tag filter alone still leaves tag pushes",
            id="tags-ignore",
        ),
        pytest.param(
            "\n    paths: ['src/**']",
            True,
            "a path filter narrows without excluding main",
            id="paths",
        ),
    ],
)
def test_the_push_reader_answers_every_filter_form(
    filters: str, *, expected: bool, why: str
) -> None:
    """Which workflow may publish turns on this reading.

    `publishers` grants the CodeScene upload to a workflow that pushes
    to main, so a reader answering True for a shape that never runs on
    a main push hands that permission to the wrong file, and the whole
    contract passes while the wrong workflow uploads.

    The tag forms are the ones a naive reading gets wrong. A `push`
    filtered to tags alone fires for tag pushes and never for a branch,
    so it is not a main publisher however much it looks like one.
    """
    document = load_workflow(f"on:\n  push:{filters}\n{JOBS}")
    assert pushes_to_main(document) is expected, (
        f"push{filters!r}: {why}, so the reader must answer {expected}"
    )


def test_a_workflow_with_no_push_trigger_never_publishes() -> None:
    """Assert the push reader is narrow as well as broad.

    A reading that answered True whenever it could not find a reason to
    say no would satisfy most of the table above and make every
    pull-request workflow a candidate publisher.
    """
    assert not pushes_to_main(load_workflow(f"on:\n  pull_request:\n{JOBS}")), (
        "a workflow declaring no push trigger cannot push to main"
    )


@pytest.mark.parametrize(
    "document",
    [
        pytest.param("- a\n- b\n", id="a-list"),
        pytest.param("just a string\n", id="a-scalar"),
        pytest.param("", id="empty"),
    ],
)
def test_a_document_that_is_not_a_workflow_is_refused(document: str) -> None:
    """A workflow is a mapping, and anything else is not one.

    Returning an empty mapping instead would make every reading over it
    find nothing, which each rule built on them reads as compliance.
    """
    with pytest.raises(TypeError, match="top-level mapping"):
        load_workflow(document)


def test_an_empty_workflow_directory_is_a_reader_fault(
    tmp_path: pathlib.Path,
) -> None:
    """Finding no workflow at all is never an answer.

    Every rule built on the acquisition is a refusal over its result, so
    an empty reading satisfies all of them. The fault names the reading
    and the directory rather than leaving a caller to parse a message.
    """
    with pytest.raises(WorkflowReadingError) as raised:
        read_workflows(tmp_path)
    assert raised.value.reader == "read_workflows", raised.value
    assert raised.value.path == str(tmp_path), raised.value


@pytest.mark.parametrize(
    ("body", "why"),
    [
        pytest.param("- not a mapping\n", "parses, but not to a mapping", id="shape"),
        pytest.param("a: [1, 2\n", "does not parse at all", id="syntax"),
        pytest.param("a: b\n  c: d\n", "is badly indented", id="indent"),
    ],
)
def test_an_unreadable_workflow_names_its_file(
    tmp_path: pathlib.Path, body: str, why: str
) -> None:
    """A file that is not a workflow is reported with its name.

    Both failures are covered, and the second is the one the first
    version of this case missed. `- not a mapping` parses perfectly
    well and only exercises the mapping check; syntactically invalid
    YAML raises from the parser before that check is reached, and
    without `yaml.YAMLError` in the translation it escaped with a line
    and column but no file name, from inside a helper whose return type
    promises a mapping.
    """
    (tmp_path / "broken.yml").write_text(body, encoding="utf-8")
    with pytest.raises(WorkflowReadingError) as raised:
        read_workflows(tmp_path)
    assert raised.value.reader == "read_workflows", f"{why}: {raised.value}"
    assert "broken.yml" in (raised.value.path or ""), f"{why}: {raised.value}"


def test_no_pull_request_workflow_is_a_reader_fault() -> None:
    """The same argument one layer up.

    A repository with a pull-request lane that reads as having none is a
    broken reading, and the rules refusing things on that lane would all
    pass over the empty set.
    """
    documents = {"main-only.yml": load_workflow(f"on:\n  push:\n{JOBS}")}
    with pytest.raises(WorkflowReadingError) as raised:
        pull_request_workflows(documents)
    assert raised.value.reader == "pull_request_workflows", raised.value


def test_a_duplicate_coverage_step_is_refused() -> None:
    """One step per workflow, or the second hides the first.

    Every assertion over a coverage step inspects one per workflow. Were
    the reading to keep the last, a compliant second invocation would
    hide a non-compliant first from all of them, and the contract would
    certify a lane it had not read.
    """
    from tests.support.codescene_coverage import COVERAGE_ACTION

    document = load_workflow(
        f"on:\n  push:\njobs:\n  a:\n    steps:\n"
        f"      - uses: {COVERAGE_ACTION}@{'a' * 40}\n"
        f"      - uses: {COVERAGE_ACTION}@{'b' * 40}\n"
    )
    with pytest.raises(WorkflowReadingError) as raised:
        coverage_steps({"twice.yml": document})
    assert raised.value.reader == "coverage_steps", raised.value
    assert raised.value.path == "twice.yml", raised.value


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("jobs: not-a-mapping\n", id="jobs-not-a-mapping"),
        pytest.param("jobs:\n  a: not-a-mapping\n", id="job-not-a-mapping"),
        pytest.param("jobs:\n  a:\n    steps: not-a-list\n", id="steps-not-a-list"),
        pytest.param("jobs:\n  a:\n    steps:\n      - a-string\n", id="step-a-string"),
        pytest.param("name: x\n", id="no-jobs"),
    ],
)
def test_a_malformed_job_shape_yields_no_steps(body: str) -> None:
    """A fragment this reading cannot use contributes nothing.

    Refusing the whole document instead would let a workflow with
    nothing to do with coverage fail a contract about coverage, which
    is the wrong failure in the wrong place.
    """
    assert workflow_steps(load_workflow(f"on:\n  push:\n{body}")) == [], (
        f"a malformed job shape yields no steps: {body!r}"
    )


def test_a_publisher_serving_pull_requests_is_not_a_publisher() -> None:
    """Both halves of the predicate, and the second is the one that is dropped.

    A repository's main workflow usually declares `pull_request` and
    `push: branches: [main]` together. A predicate reading only the push
    makes that one file simultaneously required to upload and forbidden
    from uploading, so the contract contradicts itself rather than
    failing.
    """
    both = load_workflow(f"on:\n  pull_request:\n  push:\n    branches: [main]\n{JOBS}")
    assert publishers({"smoke.yml": both}) == {}, (
        "a workflow serving pull requests is not a publisher, whatever else "
        "it is triggered by"
    )
    assert serves_pull_requests(both), "the fixture must serve pull requests"
