"""GitHub Actions workflow parsing helpers for test contracts."""

import typing as typ

import yaml


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
