"""Acquiring the workflow files these contracts read.

Separated from `coverage_workflows` so the acquisition and the reading
over it stay legible apart, and so neither module outgrows the 400-line
limit the lint gate enforces. `workflow_documents` is re-exported from
`coverage_workflows`, because a reader of a coverage lane wants one
import rather than two.

Acquisition fails in ways a reading does not, and the two failures want
different answers. A document that is not a mapping declares no jobs and
contributes no lane, so it is skipped; a file that cannot be read at all
could hold the very lane the contract exists to bound, so it is
reported.
"""

import typing as typ
from pathlib import Path

import yaml

from tests.support.workflow_shapes import WorkflowDocument, WorkflowReadingError

WORKFLOWS_DIRECTORY: typ.Final[Path] = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows"
)


def workflow_documents(
    directory: Path = WORKFLOWS_DIRECTORY,
) -> dict[str, WorkflowDocument]:
    """Return every workflow document in a directory, keyed by file name.

    Both extensions are read. A coverage lane in the other one would
    otherwise escape every assertion below without failing anything.

    The directory is a parameter so this acquisition can be pointed at a
    temporary tree. A document that is not a mapping is skipped rather
    than raising: a workflow file holding a list or a bare scalar
    declares no jobs, so it contributes no lane, and failing here would
    fail the whole contract on a file that has nothing to do with
    coverage. A file that cannot be read at all is a different matter,
    and is reported rather than skipped: a workflow the reading never
    saw could hold the lane the contract exists to bound.

    Parameters
    ----------
    directory : Path
        Directory of workflow files. Defaults to the repository's own.

    Returns
    -------
    dict[str, WorkflowDocument]
        File name to parsed document.
    """
    documents: dict[str, WorkflowDocument] = {}
    for pattern in ("*.yml", "*.yaml"):
        for path in sorted(directory.glob(pattern)):
            match _parsed_workflow(path):
                case dict() as document:
                    documents[path.name] = typ.cast("WorkflowDocument", document)
                case _:
                    continue
    return documents


def _parsed_workflow(path: Path) -> object:
    """Return one workflow file's parsed contents.

    Parameters
    ----------
    path : Path
        The workflow file to read.

    Returns
    -------
    object
        Whatever the file holds, which need not be a mapping.

    Raises
    ------
    WorkflowReadingError
        If the file cannot be read, if its bytes are not UTF-8, or if
        its text is not YAML.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        # UnicodeDecodeError descends from ValueError, not OSError, so a
        # workflow holding bytes that are not UTF-8 would otherwise
        # escape this boundary and surface as a decoding error naming a
        # byte offset, with nothing saying which workflow it came from.
        message = f"{path} could not be read: {exc}"
        raise WorkflowReadingError(message, path=path) from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        message = f"{path} is not YAML: {exc}"
        raise WorkflowReadingError(message, path=path) from exc
