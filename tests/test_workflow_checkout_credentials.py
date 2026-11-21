"""Hold every workflow's checkout to the rule that it keeps no token.

``actions/checkout`` writes the job's token into ``.git/config`` by default,
and it stays there for the rest of the job. Every later step can read it, and
so can every third-party action, whether or not that action was meant to have
it. A workflow that publishes from a tag therefore hands a ``contents: write``
token to whatever else it runs unless it opts out.

None of this repository's workflows pushes from a checked-out tree: the
publishing jobs pass paths and tags to ``gh``, and the build jobs only compile
and upload artefacts, which use their own token and no Git credential. So
``persist-credentials: false`` costs nothing and removes the exposure
everywhere.

The rule is asserted over the whole directory rather than the release workflow
alone. It is a property of the tool, not of one file, and a workflow added
later inherits it by being read here.
"""

import typing as typ

import pytest

from tests.conftest import WORKFLOWS
from tests.support.workflow_files import read_workflows

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument

CHECKOUT: typ.Final = "actions/checkout@"


def _checkouts(document: WorkflowDocument) -> list[tuple[str, dict[str, object]]]:
    """Return every checkout step in `document` as its job name and mapping."""
    jobs = document.get("jobs")
    assert isinstance(jobs, dict), "a workflow must declare jobs as a mapping"
    found: list[tuple[str, dict[str, object]]] = []
    for job, body in jobs.items():
        assert isinstance(body, dict), job
        for entry in body.get("steps") or []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("uses", "")).startswith(CHECKOUT):
                found.append((str(job), entry))
    return found


def _inputs(entry: dict[str, object]) -> dict[str, object]:
    """Return a step's ``with:`` inputs, or an empty mapping when it has none."""
    declared = entry.get("with")
    return declared if isinstance(declared, dict) else {}


@pytest.fixture(scope="module")
def workflows() -> dict[str, WorkflowDocument]:
    """Return every workflow document, keyed by file name.

    Returns
    -------
    dict
        File name to parsed document.
    """
    return read_workflows(WORKFLOWS)


def test_every_workflow_declares_the_checkouts_it_makes(
    workflows: dict[str, WorkflowDocument],
) -> None:
    """A reading that finds no checkout at all would pass vacuously."""
    checkouts = [name for name, document in workflows.items() if _checkouts(document)]
    assert checkouts, "no workflow checks anything out; this reading is blind"


def test_every_checkout_leaves_no_credential_behind(
    workflows: dict[str, WorkflowDocument],
) -> None:
    """Only ``persist-credentials: false`` is accepted, on every checkout."""
    offenders = [
        f"{name}:{job}"
        for name, document in workflows.items()
        for job, entry in _checkouts(document)
        if _inputs(entry).get("persist-credentials") != "false"
    ]
    assert not offenders, f"these checkouts persist their credentials: {offenders}"
