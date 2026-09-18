"""Reading the CodeScene coverage shape CV-005 requires.

Separated from `test_codescene_coverage_contract` so the reading and
the assertions over it stay legible apart, and so neither module
outgrows the 400-line limit the lint gate enforces.

Every reader here answers a question about the repository's workflows
as a whole, and each is written so that finding nothing is an error
rather than a pass: the rules above are refusals, and a refusal over an
empty subject set is satisfied by any repository at all.
"""

import pathlib
import re
import typing as typ

from tests.support.workflows import (
    load_workflow,
    pushes_to_main,
    serves_pull_requests,
    workflow_steps,
)

#: Two levels up, because this module lives in `tests/support`. The
#: reader below asserts it found workflows, which is what turned a
#: wrong depth here into a failure rather than a silent pass.
REPOSITORY_ROOT: typ.Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS: typ.Final[pathlib.Path] = REPOSITORY_ROOT / ".github" / "workflows"


class WorkflowReadingError(RuntimeError):
    """Raised when a reader here finds nothing it must have found.

    Every rule built on these readers is a refusal, and a refusal over
    an empty subject set is satisfied by any repository at all. So an
    empty reading is reported as a fault of the reader rather than
    returned, and it is a distinct type so that "this reader is broken"
    and "this repository complies" cannot be confused by a caller or by
    whoever reads the failure.
    """


#: The action that talks to CodeScene, matched on its path rather than
#: on the word: the workflows discuss CodeScene in prose, and a comment
#: is not an invocation. A repin changes the SHA after the `@`, so the
#: path is what stays true.
CODESCENE_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/upload-codescene-coverage"
)

#: The coverage generator, which every lane may run.
COVERAGE_ACTION: typ.Final[str] = (
    "leynos/shared-actions/.github/actions/generate-coverage"
)

#: A full-length commit pin, which is the shape section 6f of the
#: developers' guide asks a contract to assert. The value is
#: deliberately not named: Dependabot owns these bumps, and a test
#: holding today's SHA turns every routine bump into a manual edit.
#:
#: What this branch needed the pin *for* is recorded in the workflows
#: and the pull request rather than here: `publish-artefact` arrives at
#: a5765019, and that commit carries the cs-coverage manifest pin that
#: fixed the cobertura parse break. The contract below holds the
#: property that survives a bump, which is that both coverage lanes
#: name the same commit.
PINNED_COMMIT: typ.Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

#: The command no pull-request lane may run.
CLI_COMMAND: typ.Final[str] = "cs-coverage"


def documents() -> dict[str, dict[str, object]]:
    """Return every workflow document, keyed by file name.

    Returns
    -------
    dict
        File name to parsed document. Both suffixes are read: GitHub
        runs a workflow named either way, so a sweep over one of them
        reports repository-wide coverage while ignoring half the places
        a lane can be declared.

    Raises
    ------
    WorkflowReadingError
        If no workflow document was read at all.
    """
    found = {
        path.name: load_workflow(path.read_text(encoding="utf-8"))
        for pattern in ("*.yml", "*.yaml")
        for path in sorted(WORKFLOWS.glob(pattern))
    }
    if not found:
        message = (
            f"no workflow documents were read from {WORKFLOWS}; every "
            f"assertion built on this reading is satisfied by finding "
            f"nothing, so this is the reader failing rather than the "
            f"repository complying"
        )
        raise WorkflowReadingError(message)
    return found


def pull_request_workflows() -> dict[str, dict[str, object]]:
    """Return the workflows that serve pull requests.

    Returns
    -------
    dict
        File name to parsed document.

    Raises
    ------
    WorkflowReadingError
        If none serves a pull request, which cannot be true of this
        repository. Reported rather than returned, and the message
        names the reader rather than the workflows, so "the reader is
        broken" and "the repository complies" stay distinguishable.
    """
    found = {
        name: document
        for name, document in documents().items()
        if serves_pull_requests(document)
    }
    if not found:
        message = (
            "this reading found no workflow serving a pull request, which "
            "cannot be true of this repository; the trigger reader is "
            "broken, not the workflows"
        )
        raise WorkflowReadingError(message)
    return found


def publishers() -> dict[str, dict[str, object]]:
    """Return the workflows allowed to upload to CodeScene.

    A publisher pushes to main *and serves no pull request*. Both halves
    are needed and the second is the one that is easy to drop: a
    repository's main workflow usually declares `pull_request` and
    `push: branches: [main]` together, so a predicate reading only the
    push makes that one file simultaneously required to upload and
    forbidden from uploading, and the contract contradicts itself
    rather than failing.

    Returns
    -------
    dict
        File name to parsed document.
    """
    return {
        name: document
        for name, document in documents().items()
        if pushes_to_main(document) and not serves_pull_requests(document)
    }


def coverage_steps() -> dict[str, dict[str, object]]:
    """Return each workflow's generate-coverage step, keyed by file name."""
    found: dict[str, dict[str, object]] = {}
    for name, document in documents().items():
        for step in workflow_steps(document):
            if COVERAGE_ACTION in str(step.get("uses", "")):
                found[name] = step
    return found
