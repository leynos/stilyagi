"""Reading the CodeScene coverage shape CV-005 requires.

Separated from `test_codescene_coverage_contract` so the reading and
the assertions over it stay legible apart, and so neither module
outgrows the 400-line limit the lint gate enforces.

The acquisition is one function and everything above it is pure. Only
`read_workflows` touches the filesystem, and it takes the directory to
read rather than finding one, so every policy reading below can be
driven with supplied documents. That is what lets a contract ask what
these rules make of a workflow this repository does not contain: the
real files use one spelling of everything and cannot tell a working
reader from a broken one.

Each policy reading treats finding nothing as a fault rather than an
answer. The rules built on them are refusals, and a refusal over an
empty subject set is satisfied by any repository at all.
"""

import re
import typing as typ

import yaml

from tests.support import SupportError
from tests.support.workflows import (
    load_workflow,
    pushes_to_main,
    serves_pull_requests,
    workflow_steps,
)

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.workflows import WorkflowDocument

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
#: fixed the cobertura parse break. The contract holds the property
#: that survives a bump, which is that both coverage lanes name the
#: same commit.
PINNED_COMMIT: typ.Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

#: The command no pull-request lane may run.
CLI_COMMAND: typ.Final[str] = "cs-coverage"


class WorkflowReadingError(SupportError):
    """Raised when a reading here finds nothing it must have found.

    Every rule built on these readings is a refusal, and a refusal over
    an empty subject set is satisfied by any repository at all. So an
    empty reading is reported as a fault of the reader rather than
    returned, and it is a distinct type so that "this reader is broken"
    and "this repository complies" cannot be confused by a caller or by
    whoever reads the failure.

    Attributes
    ----------
    path : str or None
        What the reading was over, when it was over something nameable:
        a directory for the acquisition, a workflow's file name for a
        reading of one document. None when the fault is about the whole
        set rather than one member.
    """

    def __init__(self, message: str, *, reader: str, path: str | None = None) -> None:
        """Record the message, the reading, and what it was over.

        Parameters
        ----------
        message : str
            What went wrong, for a person reading the failure.
        reader : str
            The reading that failed.
        path : str or None
            The directory or file name the fault is about, when it has
            one.
        """
        super().__init__(message, reader=reader)
        self.path = path


def _read_one(path: pathlib.Path) -> WorkflowDocument:
    """Return one workflow's parsed document, naming the file on failure.

    Parameters
    ----------
    path : pathlib.Path
        The workflow to read.

    Returns
    -------
    WorkflowDocument
        The parsed document.

    Raises
    ------
    WorkflowReadingError
        If the file cannot be read or is not a workflow document.
        Reported with the file's name rather than surfacing as a bare
        `OSError` naming an errno, or a `TypeError` from inside a
        helper whose return type promises a mapping.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"{path} could not be read: {error}"
        raise WorkflowReadingError(
            message, reader="read_workflows", path=str(path)
        ) from error
    try:
        return load_workflow(text)
    except (TypeError, ValueError, yaml.YAMLError) as error:
        # `yaml.YAMLError` as well as the shape errors. Syntactically
        # invalid YAML raises from the parser before `load_workflow`
        # reaches its mapping check, so without it the parser's message
        # escapes with a line and column but no file name, from inside a
        # helper whose return type promises a mapping.
        message = f"{path} is not a workflow document: {error}"
        raise WorkflowReadingError(
            message, reader="read_workflows", path=str(path)
        ) from error


def read_workflows(directory: pathlib.Path) -> dict[str, WorkflowDocument]:
    """Return every workflow document under one directory.

    The only filesystem access in this module. It takes the directory
    rather than finding one, so a caller can point it at a fixture tree
    and every reading below can be driven without it at all.

    Parameters
    ----------
    directory : pathlib.Path
        The directory to read.

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
        If the directory holds no workflow at all, or one of them
        cannot be read, is not valid YAML, or is not a mapping. Each
        is reported with the file's name rather than surfacing as a
        bare `OSError` naming an errno, or a parser error naming a line
        and column but no file.
    """
    found = {
        path.name: _read_one(path)
        for pattern in ("*.yml", "*.yaml")
        for path in sorted(directory.glob(pattern))
    }
    if not found:
        message = (
            f"no workflow documents were read from {directory}; every "
            f"assertion built on this reading is satisfied by finding "
            f"nothing, so this is the reader failing rather than the "
            f"repository complying"
        )
        raise WorkflowReadingError(
            message, reader="read_workflows", path=str(directory)
        )
    return found


def pull_request_workflows(
    documents: dict[str, WorkflowDocument],
) -> dict[str, WorkflowDocument]:
    """Return the workflows that serve pull requests.

    Parameters
    ----------
    documents : dict
        File name to parsed document.

    Returns
    -------
    dict
        The subset serving pull requests.

    Raises
    ------
    WorkflowReadingError
        If none serves a pull request, which cannot be true of a
        repository with a pull-request lane. Reported rather than
        returned, and the message names the reading rather than the
        workflows, so "the reader is broken" and "the repository
        complies" stay distinguishable.
    """
    found = {
        name: document
        for name, document in documents.items()
        if serves_pull_requests(document)
    }
    if not found:
        message = (
            "this reading found no workflow serving a pull request; the "
            "trigger reader is broken, not the workflows"
        )
        raise WorkflowReadingError(message, reader="pull_request_workflows")
    return found


def publishers(
    documents: dict[str, WorkflowDocument],
) -> dict[str, WorkflowDocument]:
    """Return the workflows allowed to upload coverage.

    A publisher pushes to main *and serves no pull request*. Both
    halves are needed and the second is the one that is easy to drop: a
    repository's main workflow usually declares `pull_request` and
    `push: branches: [main]` together, so a predicate reading only the
    push makes that one file simultaneously required to upload and
    forbidden from uploading, and the contract contradicts itself
    rather than failing.

    Parameters
    ----------
    documents : dict
        File name to parsed document.

    Returns
    -------
    dict
        The subset allowed to publish. Empty is a legitimate answer
        here rather than a fault, because "no publisher" is one of the
        states the contract above exists to refuse.
    """
    return {
        name: document
        for name, document in documents.items()
        if pushes_to_main(document) and not serves_pull_requests(document)
    }


def coverage_steps(
    documents: dict[str, WorkflowDocument],
) -> dict[str, dict[str, object]]:
    """Return each workflow's generate-coverage step, keyed by file name.

    Parameters
    ----------
    documents : dict
        File name to parsed document.

    Returns
    -------
    dict
        File name to the single coverage step that workflow declares.

    Raises
    ------
    WorkflowReadingError
        If a workflow invokes the coverage action more than once.
        Keeping the last would let a compliant second invocation hide a
        non-compliant first, and every assertion built on this reading
        inspects one step per workflow, so the ambiguity is refused
        rather than resolved arbitrarily.
    """
    found: dict[str, dict[str, object]] = {}
    for name, document in documents.items():
        for step in workflow_steps(document):
            if COVERAGE_ACTION not in str(step.get("uses", "")):
                continue
            if name in found:
                message = (
                    f"{name} invokes {COVERAGE_ACTION} more than once; this "
                    f"reading returns one step per workflow, so a second "
                    f"would hide the first from every assertion over it"
                )
                raise WorkflowReadingError(message, reader="coverage_steps", path=name)
            found[name] = step
    return found
