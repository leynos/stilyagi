"""Reading the CodeScene coverage shape CV-005 requires.

Separated from `test_codescene_coverage_contract` so the reading and
the assertions over it stay legible apart, and so neither module
outgrows the 400-line limit the lint gate enforces.

Everything here is pure. The acquisition is in `workflow_files`, and
it takes the directory to read rather than finding one, so every policy
reading below can be driven with supplied documents. That is what lets
a contract ask what these rules make of a workflow this repository does
not contain: the real files use one spelling of everything and cannot
tell a working reader from a broken one.

Each policy reading treats finding nothing as a fault rather than an
answer. The rules built on them are refusals, and a refusal over an
empty subject set is satisfied by any repository at all.
"""

import re
import typing as typ

from tests.support.workflow_files import WorkflowReadingError
from tests.support.workflows import (
    pushes_to_main,
    serves_pull_requests,
    workflow_jobs,
    workflow_steps,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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


#: Where a same-repository reusable workflow lives, relative to the
#: repository root. GitHub resolves `./.github/workflows/x.yml` from
#: there, and a workflow outside this directory cannot be called at all.
WORKFLOW_DIRECTORY: typ.Final[str] = ".github/workflows/"


def _local_workflow(
    reference: object, documents: dict[str, WorkflowDocument]
) -> str | None:
    """Return the file a `uses:` value names in this tree, if any.

    Matched by shape rather than by an enumerated prefix list: strip a
    leading `./` and ask whether what remains is a file directly under
    the workflow directory. A list of accepted spellings drops every
    spelling nobody thought to list, silently, while a pull request
    still runs the workflow it names; a cross-repository reference
    (`owner/repo/.github/workflows/x.yml@ref`) fails the shape because
    it does not start at the workflow directory.

    Returns
    -------
    str or None
        The called file's name, or None when the value is not a call to
        a workflow held here.
    """
    if not isinstance(reference, str):
        return None
    path = reference.removeprefix("./")
    if not path.startswith(WORKFLOW_DIRECTORY):
        return None
    name = path.removeprefix(WORKFLOW_DIRECTORY)
    return name if name in documents else None


def called_workflows(
    document: WorkflowDocument, documents: dict[str, WorkflowDocument]
) -> frozenset[str]:
    """Return the same-repository reusable workflows one document calls.

    A reference to another repository is not followed. Its content is
    not in this tree, so nothing here could read it, and claiming to
    have checked it would be worse than saying plainly that it is out
    of scope.

    Parameters
    ----------
    document : WorkflowDocument
        The calling workflow.
    documents : dict
        Every workflow document, by file name, so a call can be
        resolved to one this reading already holds.

    Returns
    -------
    frozenset of str
        The file names it calls, limited to documents present here.
    """
    names = (
        _local_workflow(job.get("uses"), documents)
        for job in workflow_jobs(document).values()
    )
    return frozenset(name for name in names if name is not None)


def _reachable(
    seeds: list[str], documents: dict[str, WorkflowDocument]
) -> dict[str, WorkflowDocument]:
    """Return the seeds and every workflow they call, transitively."""
    found: dict[str, WorkflowDocument] = {}
    pending = list(seeds)
    while pending:
        name = pending.pop()
        if name not in found:
            found[name] = documents[name]
            pending.extend(called_workflows(documents[name], documents) - found.keys())
    return found


def pull_request_workflows(
    documents: dict[str, WorkflowDocument],
) -> dict[str, WorkflowDocument]:
    """Return every workflow a pull request can reach.

    A closure rather than a trigger list, and the difference is the
    whole point. A workflow declaring only `workflow_call` still runs
    on a pull request when a pull-request workflow calls it, and
    `secrets: inherit` hands it the token, so a reading that enumerated
    triggers alone could not see it at all: every refusal below would
    pass over it while it did the forbidden thing.

    Measured rather than argued, on episodic: a `workflow_call`
    workflow curling the CodeScene project API with an inherited
    `CS_ACCESS_TOKEN`, called from a pull-request job, passed every
    clause of the equivalent contract there.

    Parameters
    ----------
    documents : dict
        File name to parsed document.

    Returns
    -------
    dict
        Every workflow reachable from a pull request: the ones
        declaring a pull-request trigger, and everything they call,
        transitively.

    Raises
    ------
    WorkflowReadingError
        If none serves a pull request, which cannot be true of a
        repository with a pull-request lane. Reported rather than
        returned, and the message names the reading rather than the
        workflows, so "the reader is broken" and "the repository
        complies" stay distinguishable.
    """
    found = _reachable(
        [
            name
            for name, document in documents.items()
            if serves_pull_requests(document)
        ],
        documents,
    )
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


#: The service itself. A pull-request lane that reaches it by any other
#: road than the action (`curl` in a script, a third-party action's
#: input, a URL in an environment variable or a reusable workflow's
#: input) escapes the action and command clauses alike, and escapes the
#: secret clause too when the credential travels under another name.
CODESCENE_HOST: typ.Final[str] = "codescene.io"


def _scalars(value: object, where: str) -> cabc.Iterator[tuple[str, str]]:
    """Yield every scalar in a parsed document with the path that reaches it."""
    match value:
        case dict():
            for key, child in value.items():
                yield from _scalars(child, f"{where}.{key}" if where else str(key))
        case list():
            for index, child in enumerate(value):
                yield from _scalars(child, f"{where}[{index}]")
        case _:
            yield where, str(value)


def codescene_contacts(name: str, document: WorkflowDocument) -> list[str]:
    r"""Return every place in one workflow that names the CodeScene host.

    Every value in the parsed document is read, at every scope, rather
    than a list of the places a contact is expected. A URL can reach a
    step through the workflow's `env`, a job's `env`, a step's script,
    inputs or `env`, or a reusable-workflow call's `with`, and a reading
    that enumerated some of those scopes left the rest as a way round
    the rule. A comment explaining why a lane no longer talks to
    CodeScene is not read as the lane talking to it, because the parser
    discards comments.

    Parameters
    ----------
    name : str
        The workflow's file name, for the message.
    document : WorkflowDocument
        The parsed workflow.

    Returns
    -------
    list of str
        One entry per value naming the host, with its path.

    Examples
    --------
    >>> from tests.support.workflows import load_workflow
    >>> body = "jobs:\n  a:\n    steps:\n      - run: curl https://api.codescene.io\n"
    >>> codescene_contacts("ci.yml", load_workflow(body))
    ['ci.yml: jobs.a.steps[0].run']
    """
    return [
        f"{name}: {where}"
        for where, text in _scalars(document, "")
        if CODESCENE_HOST in text
    ]
