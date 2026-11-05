"""Drive one `dump-ir` invocation inside the pytest process.

The end-to-end suite spawns the command, so the parent process never imports
its modules and their branching stays invisible to the coverage ratchet. These
tests call the command in-process instead, and the helper that sets up its
streams is shared by every module that does so.
"""

import dataclasses as dc
import io
import typing as typ

from stilyagi import cli_dump_ir
from stilyagi.cli_args import DumpIrOptions

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


@dc.dataclass(frozen=True, slots=True)
class Stdin:
    """Piped bytes and the Markdown identity they report.

    The filename stays optional because rejecting piped bytes that name no
    source is itself a command branch worth exercising.
    """

    text: str
    filename: str | None = None


def run_dump_ir(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *arguments: str,
    stdin: Stdin | None = None,
) -> tuple[int, bytes, str]:
    """Run one invocation and return its exit status, stdout and stderr."""
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
