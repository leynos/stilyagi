"""What the single CodeScene publisher must look like.

Separated from `test_codescene_coverage_contract`, whose subject is
which workflow may upload at all, so neither module outgrows the
400-line limit the lint gate enforces. The subject here is the one that
may: what its upload step is guarded on, what it passes, and what stops
two of its runs racing.

Each assertion is proved by putting the forbidden element back.

Run via `make test`.
"""

import pathlib
import re
import typing as typ

import pytest

from tests.support.codescene_coverage import (
    CODESCENE_ACTION,
    publishers,
    read_workflows,
)
from tests.support.workflows import workflow_steps

if typ.TYPE_CHECKING:
    from tests.support.workflows import WorkflowDocument

REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"

#: The ref the publisher's upload step must be guarded on. A
#: `workflow_dispatch` can be aimed at any branch, so the token alone
#: does not establish that what is being uploaded is the trunk's
#: coverage.
MAIN_REF: typ.Final[str] = "github.ref == 'refs/heads/main'"

#: The repository variable this adoption retires. `installer-checksum`
#: is rejected when non-empty from the pinned uploader, and the value
#: this variable holds is the installer script's digest rather than the
#: manifest archive's, so it cannot be carried across under
#: `archive-checksum` either. The action pins the CLI through its own
#: manifest now.
RETIRED_VARIABLE: typ.Final[str] = "CODESCENE_CLI_SHA256"


@pytest.fixture(scope="module")
def documents() -> dict[str, WorkflowDocument]:
    """Return this repository's workflows, parsed once.

    Returns
    -------
    dict
        File name to parsed document.
    """
    return read_workflows(WORKFLOWS)


def _publisher_inputs(documents: dict[str, WorkflowDocument]) -> dict[str, object]:
    """Return the publisher's CodeScene step inputs."""
    ((name, document),) = publishers(documents).items()
    steps = [
        step
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    ]
    assert len(steps) == 1, f"{name} must invoke the action once; found {len(steps)}"
    inputs = steps[0].get("with") or {}
    assert isinstance(inputs, dict), (
        f"{name}'s CodeScene step declares a `with:` block that is not a "
        f"mapping: {inputs!r}"
    )
    return inputs


def test_the_publisher_uploads_rather_than_checks(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The mode is named, not left to the action's default.

    `mode` decides whether the step uploads a report or gates a pull
    request against one, and the default has changed before. Naming it
    is how this file's reader knows which of the two this step does
    without reading the action.
    """
    inputs = _publisher_inputs(documents)
    assert inputs.get("mode") == "upload", (
        f"the publisher's CodeScene step must name `mode: upload`; it names "
        f"{inputs.get('mode')!r}"
    )


def test_the_publisher_passes_no_deprecated_checksum(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The old checksum input fails the run outright.

    `installer-checksum` is rejected when non-empty from this pin, and
    `archive-checksum` is not a rename of it: it digests the manifest
    archive, while the repository variable the old input carried holds
    the installer script's digest. Carrying the value across under the
    new name would fail every run, so neither input is passed and the
    action's own manifest pins the CLI instead.
    """
    inputs = _publisher_inputs(documents)
    for rejected in ("installer-checksum", "archive-checksum"):
        assert rejected not in inputs, (
            f"the publisher passes {rejected!r}; `installer-checksum` is "
            f"rejected when non-empty and `archive-checksum` digests a "
            f"different artefact from the variable this repository holds, "
            f"so neither carries the old value safely"
        )


def test_the_publisher_uploads_only_from_main(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The token is not enough; the ref has to be checked too.

    `workflow_dispatch` is on this workflow deliberately, because an
    automerged change to main fires no push event and can only be
    measured on demand. A dispatch can be aimed at any branch, and the
    upload carries no ref, so CodeScene has no way to tell that what
    arrived was not the trunk. Without this guard, one dispatch from a
    feature branch replaces the baseline every pull request ratchets
    against, and nothing reports that it happened.

    The condition is asserted as a conjunct of the step's own `if`
    rather than by equality, so adding a further guard beside it does
    not fail this test while removing this one does.
    """
    ((name, document),) = publishers(documents).items()
    ((condition,),) = (
        (str(step.get("if", "")),)
        for step in workflow_steps(document)
        if CODESCENE_ACTION in str(step.get("uses", ""))
    )
    assert MAIN_REF in condition, (
        f"{name}'s upload step must be guarded on {MAIN_REF}; a dispatch "
        f"from a feature branch would otherwise publish that branch's "
        f"coverage as the trunk's. It is guarded on {condition!r}"
    )


def test_the_publisher_runs_one_at_a_time(
    documents: dict[str, WorkflowDocument],
) -> None:
    """Two publisher runs racing decide the baseline by finishing order.

    The baseline this workflow writes is what every pull request
    ratchets against, so a superseded run finishing last makes its
    figures the trunk's. A concurrency group with cancellation makes the
    newest run the only one that can write.
    """
    ((name, document),) = publishers(documents).items()
    concurrency = document.get("concurrency")
    assert isinstance(concurrency, dict), (
        f"{name} must declare a concurrency block; two publisher runs "
        f"otherwise race on the ratchet baseline. It declares "
        f"{concurrency!r}"
    )
    assert concurrency.get("group"), (
        f"{name}'s concurrency block must name a group: {concurrency!r}"
    )
    assert concurrency.get("cancel-in-progress") == "true", (
        f"{name} must cancel a superseded publisher run; without it the "
        f"older run can still write the baseline after the newer one. It "
        f"sets {concurrency.get('cancel-in-progress')!r}"
    )


def test_no_workflow_reads_the_retired_variable(
    documents: dict[str, WorkflowDocument],
) -> None:
    """The variable this adoption retires must have no readers left.

    Asserted on expressions rather than on the word. Both workflows
    explain in prose why the checksum input is gone, and that
    explanation names the variable; a sweep over the raw text would read
    the explanation as a reader and push the next person into deleting
    the reason rather than the reference.

    What counts as reading it is an expression: `${{ vars.NAME }}` or
    its `env` and `secrets` spellings, which is the only way a workflow
    can get the value at all. Prose naming the variable matches
    nothing, because prose carries no `${{ }}`.
    """
    reference = re.compile(
        rf"\$\{{\{{[^}}]*\b(?:vars|env|secrets)\.{re.escape(RETIRED_VARIABLE)}\b[^}}]*\}}\}}"
    )
    offenders = sorted(
        f"{name}: {match.group(0)}"
        for name in documents
        for match in reference.finditer((WORKFLOWS / name).read_text(encoding="utf-8"))
    )
    assert not offenders, (
        f"these workflows still read {RETIRED_VARIABLE}; the uploader "
        f"rejects the input it fed and the action pins the CLI through "
        f"its own manifest now: {offenders}"
    )
