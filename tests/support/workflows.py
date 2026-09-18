"""GitHub Actions workflow parsing helpers for test contracts.

The trigger reader lives here rather than beside any one contract,
because more than one rule derives its subject from a workflow's
triggers and a reader that quietly finds nothing makes every such rule
pass over an empty set.
"""

import typing as typ

import yaml

#: Triggers that mean a workflow serves pull requests. `pull_request`
#: and `pull_request_target` both run with a pull request's head in
#: view, and the second runs with the base repository's secrets, which
#: is the more dangerous of the two to give a token to.
PULL_REQUEST_TRIGGERS: typ.Final[frozenset[str]] = frozenset({
    "pull_request",
    "pull_request_target",
})


def load_workflow(workflow: str) -> dict[str, object]:
    r"""Parse a GitHub Actions workflow while retaining scalar strings.

    Parameters
    ----------
    workflow
        YAML document containing a GitHub Actions workflow.

    Returns
    -------
    dict[str, object]
        The workflow's top-level mapping, with every YAML scalar represented as
        a string.

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
            return typ.cast("dict[str, object]", document)
        case _:
            message = "A workflow must parse to a top-level mapping"
            raise TypeError(message)


def triggers(document: dict[str, object]) -> frozenset[str]:
    """Return the trigger names a workflow declares.

    `on` is read through both the string key and the boolean `True`,
    and this is not defensive noise. YAML 1.1 resolves an unquoted
    `on:` to a boolean, so a loader that resolves scalars gives every
    workflow in this estate a `True` key and none at all named `on`. A
    reader looking only for the string then reports every workflow as
    having no triggers, which makes every rule below iterate an empty
    set and pass. The repository's own `load_workflow` uses
    `yaml.BaseLoader` and so keeps the string, but the failure is
    silent and inverts the contract, so the reading does not depend on
    that staying true.

    Parameters
    ----------
    document : dict
        A parsed workflow.

    Returns
    -------
    frozenset of str
        Its trigger names. The mapping, list and bare-string forms are
        all spellings GitHub accepts.
    """
    triggers = document.get("on", document.get(True))
    match triggers:
        case dict():
            return frozenset(str(name) for name in triggers)
        case list():
            return frozenset(str(name) for name in triggers)
        case str():
            return frozenset({triggers})
        case _:
            return frozenset()


def serves_pull_requests(document: dict[str, object]) -> bool:
    """Return whether a workflow runs for a pull request."""
    return bool(triggers(document) & PULL_REQUEST_TRIGGERS)


def pushes_to_main(document: dict[str, object]) -> bool:
    """Return whether a workflow runs on a push to main."""
    # Named `declared` rather than `triggers`, which is the function
    # this one calls two lines down.
    declared = document.get("on", document.get(True))
    if not isinstance(declared, dict):
        return False
    push = declared.get("push")
    if not isinstance(push, dict):
        return "push" in triggers(document)
    branches = push.get("branches")
    match branches:
        case list():
            return "main" in [str(branch) for branch in branches]
        case str():
            return branches == "main"
        case _:
            return True


def workflow_steps(document: dict[str, object]) -> list[dict[str, object]]:
    """Return every step of every job in one workflow."""
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
