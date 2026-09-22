"""GitHub Actions workflow parsing helpers for test contracts.

Pure readings over a parsed document. Nothing here touches the
filesystem: a caller supplies the text or the mapping, which is what
lets a contract ask what a reading makes of a workflow this repository
does not contain. The real files all use one spelling of everything, so
they cannot tell a working reader from a broken one.

The trigger reader lives here rather than beside any one contract,
because more than one rule derives its subject from a workflow's
triggers and a reader that quietly finds nothing makes every such rule
pass over an empty set.
"""

import typing as typ

import yaml

#: A parsed workflow document.
#:
#: The key type is `str | bool` rather than `str`, and that is a
#: statement about YAML rather than defensiveness. YAML 1.1 resolves an
#: unquoted `on:` to a boolean, so a loader that resolves scalars keys
#: every workflow in this estate under `True`. `load_workflow` uses
#: `yaml.BaseLoader` and keeps the string, but a reader that declared
#: `dict[str, object]` and then looked under `True` would be claiming
#: something the type says cannot happen.
type WorkflowDocument = dict[str | bool, object]

#: Triggers that mean a workflow serves pull requests. `pull_request`
#: and `pull_request_target` both run with a pull request's head in
#: view, and the second runs with the base repository's secrets, which
#: is the more dangerous of the two to give a token to.
PULL_REQUEST_TRIGGERS: typ.Final[frozenset[str]] = frozenset({
    "pull_request",
    "pull_request_target",
})


def load_workflow(workflow: str) -> WorkflowDocument:
    r"""Parse a GitHub Actions workflow while retaining scalar strings.

    Parameters
    ----------
    workflow
        YAML document containing a GitHub Actions workflow.

    Returns
    -------
    WorkflowDocument
        The workflow's top-level mapping, with every YAML scalar
        represented as a string.

    Raises
    ------
    TypeError
        If the YAML document does not parse to a top-level mapping.

    Examples
    --------
    >>> load_workflow("on:\\n  push:\\n")
    {'on': {'push': ''}}
    """
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    match parsed:
        case dict() as document:
            return typ.cast("WorkflowDocument", document)
        case _:
            message = "A workflow must parse to a top-level mapping"
            raise TypeError(message)


def triggers(document: WorkflowDocument) -> frozenset[str]:
    """Return the trigger names a workflow declares.

    `on` is read through both the string key and the boolean `True`,
    and this is not defensive noise. YAML 1.1 resolves an unquoted
    `on:` to a boolean, so a loader that resolves scalars gives every
    workflow in this estate a `True` key and none at all named `on`. A
    reader looking only for the string then reports every workflow as
    having no triggers, which makes every rule built on it iterate an
    empty set and pass. `load_workflow` keeps the string, but the
    failure is silent and inverts the contract, so the reading does not
    depend on that staying true.

    Parameters
    ----------
    document : WorkflowDocument
        A parsed workflow.

    Returns
    -------
    frozenset of str
        Its trigger names. The mapping, list and bare-string forms are
        all spellings GitHub accepts.
    """
    declared = document.get("on", document.get(True))
    match declared:
        case dict():
            return frozenset(str(name) for name in declared)
        case list():
            return frozenset(str(name) for name in declared)
        case str():
            return frozenset({declared})
        case _:
            return frozenset()


def trigger_filters(document: WorkflowDocument, trigger: str) -> dict[str, object]:
    """Return one trigger's filter mapping, or an empty one.

    Parameters
    ----------
    document : WorkflowDocument
        A parsed workflow.
    trigger : str
        The trigger whose filters are wanted, such as ``push``.

    Returns
    -------
    dict
        The filters that trigger declares. Empty when the trigger is
        absent, or is declared with no filters at all, which the list
        and bare-string forms of `on` both are.
    """
    declared = document.get("on", document.get(True))
    if not isinstance(declared, dict):
        return {}
    filters = declared.get(trigger)
    return filters if isinstance(filters, dict) else {}


def serves_pull_requests(document: WorkflowDocument) -> bool:
    """Return whether a workflow runs for a pull request.

    Parameters
    ----------
    document : WorkflowDocument
        A parsed workflow.

    Returns
    -------
    bool
        True when it declares `pull_request` or `pull_request_target`.
    """
    return bool(triggers(document) & PULL_REQUEST_TRIGGERS)


def _names(value: object) -> list[str]:
    """Return a filter's entries, which GitHub spells as a list or a scalar."""
    match value:
        case list():
            return [str(entry) for entry in value]
        case str():
            return [value]
        case _:
            return []


def pushes_to_main(document: WorkflowDocument) -> bool:
    """Return whether a workflow runs on a push to the main branch.

    Every filter form GitHub accepts is answered, and an unrecognised
    one is answered `False` rather than `True`. Failing closed is the
    safe direction here: this reading decides which workflow is allowed
    to publish coverage, so a shape it cannot understand must not be
    granted that permission by default.

    A bare `push:` with no filters does push to main, so that answers
    True. `branches` must name main. `branches-ignore` must not.
    `tags` or `tags-ignore` alone restrict the trigger to tag pushes,
    which are not branch pushes at all, so those answer False.

    Parameters
    ----------
    document : WorkflowDocument
        A parsed workflow.

    Returns
    -------
    bool
        True when a push to `main` runs this workflow.
    """
    if "push" not in triggers(document):
        return False
    filters = trigger_filters(document, "push")
    if not filters:
        return True
    if "branches" in filters:
        return "main" in _names(filters["branches"])
    if "branches-ignore" in filters:
        return "main" not in _names(filters["branches-ignore"])
    # A tag filter alone leaves the trigger firing for tag pushes only,
    # and a tag push is not a branch push. Every other filter, `paths`
    # among them, narrows which pushes run the workflow without
    # excluding main, so the answer there is still yes.
    return not {"tags", "tags-ignore"} & set(filters)


def workflow_steps(document: WorkflowDocument) -> list[dict[str, object]]:
    """Return every step of every job in one workflow.

    A job or step that is not a mapping is dropped rather than raising.
    A malformed fragment is not this reading's subject, and refusing the
    whole document over one would let an unrelated workflow fail a
    contract about coverage.

    Parameters
    ----------
    document : WorkflowDocument
        A parsed workflow.

    Returns
    -------
    list of dict
        Every step, in the order the document declares them, flattened
        across jobs.
    """
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return []
    return [
        step
        for job in jobs.values()
        if isinstance(job, dict)
        for step in (job.get("steps") or [])
        if isinstance(step, dict)
    ]
