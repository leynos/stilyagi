"""Drive one `dump-ir` invocation inside the pytest process.

The end-to-end suite spawns the command, so the parent process never imports
its modules and their branching stays invisible to the coverage ratchet. These
tests call the command in-process instead, and the helper that sets up its
streams is shared by every module that does so.

The snapshot normalizers live here for a different reason. A producer version
is the dependency pin, not this command's shape, so a bump would churn every
IR snapshot for no reviewer-useful reason. Blanking it keeps the snapshots
about structure and leaves its meaning to
`tests/test_markdown_producer_version_contract.py`.
"""

import copy
import dataclasses as dc
import io
import re
import typing as typ

from stilyagi import cli_dump_ir
from stilyagi.cli_args import DumpIrOptions

if typ.TYPE_CHECKING:
    import pathlib

    import pytest

#: Stands in for each producer's version so a dependency bump does not churn
#: the snapshots. `test_markdown_producer_version_contract` pins that value's
#: meaning; the snapshots pin the surrounding shape.
PRODUCER_VERSION_PLACEHOLDER = "<producer-version>"

RELEASE_TRIPLE_RE = re.compile(r"^\d+\.\d+\.\d+$")


def documents(payload: object) -> list[dict[str, typ.Any]]:
    """Return a payload's documents, whether it is one object or an array."""
    entries = payload if isinstance(payload, list) else [payload]
    return [entry for entry in entries if isinstance(entry, dict)]


def producer_versions(payload: object) -> list[str]:
    """Return every producer version the payload reports."""
    return [
        str(producer["version"])
        for document in documents(payload)
        for producer in document.get("producers", ())
    ]


def without_producer_versions(payload: object) -> object:
    """Return a copy with each producer version blanked for snapshotting."""
    normalized = copy.deepcopy(payload)
    for document in documents(normalized):
        for producer in document.get("producers", ()):
            producer["version"] = PRODUCER_VERSION_PLACEHOLDER
    return normalized


@dc.dataclass(frozen=True, slots=True)
class Stdin:
    """Piped bytes and the Markdown identity they report.

    The filename stays optional because rejecting piped bytes that name no
    source is itself a command branch worth exercising.

    Attributes
    ----------
    text:
        The bytes the command reads from standard input.
    filename:
        The Markdown identity the caller claims for those bytes, or ``None``
        when the case deliberately names no source.
    """

    text: str
    filename: str | None = None


def run_dump_ir(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *arguments: str,
    stdin: Stdin | None = None,
) -> tuple[int, bytes, str]:
    """Run one invocation and return its exit status, stdout and stderr.

    Parameters
    ----------
    tmp_path:
        The directory the invocation runs in; it is also where relative
        targets are resolved from.
    monkeypatch:
        The pytest patcher used to set the working directory and, when a case
        pipes bytes, the command's standard input.
    *arguments:
        The positional targets to hand the command.
    stdin:
        Bytes to pipe, or ``None`` to leave standard input untouched.

    Returns
    -------
    tuple
        The exit status, the captured standard output and the captured
        standard error, in that order.
    """
    monkeypatch.chdir(tmp_path)
    output = io.BytesIO()
    error = io.StringIO()
    if stdin is not None:
        monkeypatch.setattr(cli_dump_ir.sys, "stdin", io.StringIO(stdin.text))
    options = DumpIrOptions(
        targets=arguments,
        stdin_filename=None if stdin is None else stdin.filename,
    )
    exit_code = cli_dump_ir.run_dump_ir(options, output=output, error=error)
    return exit_code, output.getvalue(), error.getvalue()
