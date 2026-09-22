"""Reading the repository's files: the one filesystem boundary.

Every contract reading in this package is pure over supplied text or
documents, and everything that touches the disk is here. Each function
takes the path to read rather than finding one, so a caller can point it
at a fixture tree, and each reports a failure as a `ReadingError`
naming the reading and the file rather than letting an `OSError` or a
parser error escape with an errno or a line number and no file name.
"""

import typing as typ

import yaml

from tests.support.errors import ReadingError
from tests.support.workflows import load_workflow

if typ.TYPE_CHECKING:
    import pathlib

    from tests.support.workflows import WorkflowDocument


class WorkflowReadingError(ReadingError):
    """Raised when a workflow reading finds nothing it must have found.

    Every rule built on these readings is a refusal, and a refusal over
    an empty subject set is satisfied by any repository at all. So an
    empty reading is reported as a fault of the reader rather than
    returned, and it is a distinct type so that "this reader is broken"
    and "this repository complies" cannot be confused by a caller or by
    whoever reads the failure. A workflow that does not parse is
    reported the same way, with its file.
    """


def read_text(path: pathlib.Path, *, reader: str) -> str:
    """Return one file's text, naming the file and the reading on failure.

    Parameters
    ----------
    path : pathlib.Path
        The file to read.
    reader : str
        The reading on whose behalf it is read, for the error.

    Returns
    -------
    str
        The file's text.

    Raises
    ------
    ReadingError
        If the file cannot be read.
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        message = f"{path} could not be read: {error}"
        raise ReadingError(message, reader=reader, path=str(path)) from error


def _workflow_texts(directory: pathlib.Path, *, reader: str) -> dict[str, str]:
    """Return every workflow file's text under one directory, by file name.

    Both suffixes are read: GitHub runs a workflow named either way, so
    a sweep over one of them reports repository-wide coverage while
    ignoring half the places a lane can be declared.

    Returns
    -------
    dict
        File name to text.

    Raises
    ------
    WorkflowReadingError
        If the directory holds no workflow, which is a fault of the
        reader for the reason the error type gives.
    """
    found = {
        path.name: read_text(path, reader=reader)
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
        raise WorkflowReadingError(message, reader=reader, path=str(directory))
    return found


def read_workflow_texts(directory: pathlib.Path) -> dict[str, str]:
    """Return every workflow's raw text under one directory, by file name.

    For a rule that must see the text as written, including places no
    structured reading visits, such as an expression under a key none
    of them looks at. An empty directory raises `WorkflowReadingError`,
    and a file that cannot be read raises `ReadingError`.

    Parameters
    ----------
    directory : pathlib.Path
        The directory to read.

    Returns
    -------
    dict
        File name to text.
    """
    return _workflow_texts(directory, reader="read_workflow_texts")


def read_workflows(directory: pathlib.Path) -> dict[str, WorkflowDocument]:
    """Return every workflow document under one directory.

    An empty directory, or a workflow that is not valid YAML, declares a
    key twice in one mapping, or is not a mapping, raises
    `WorkflowReadingError` naming the file; one that cannot be read at
    all raises `ReadingError`.

    Parameters
    ----------
    directory : pathlib.Path
        The directory to read.

    Returns
    -------
    dict
        File name to parsed document.
    """
    texts = _workflow_texts(directory, reader="read_workflows")
    return {name: _parse(directory / name, text) for name, text in texts.items()}


def _parse(path: pathlib.Path, text: str) -> WorkflowDocument:
    """Return one workflow's parsed document, naming the file on failure."""
    try:
        return load_workflow(text)
    except (TypeError, ValueError, yaml.YAMLError) as error:
        # `yaml.YAMLError` as well as the shape errors. Syntactically
        # invalid YAML raises from the parser before `load_workflow`
        # reaches its mapping check, so without it the parser's message
        # escapes with a line and column but no file name.
        message = f"{path} is not a workflow document: {error}"
        raise WorkflowReadingError(
            message, reader="read_workflows", path=str(path)
        ) from error
