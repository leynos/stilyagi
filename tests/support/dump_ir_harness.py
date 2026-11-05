"""Drive one `dump-ir` invocation inside the pytest process.

The end-to-end suite spawns the command, so the parent process never imports
its modules and their branching stays invisible to the coverage ratchet. These
tests call the command in-process instead, and the helper that sets up its
streams is shared by every module that does so.
"""

import io
import typing as typ

from stilyagi import cli_dump_ir
from stilyagi.cli_args import DumpIrOptions

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


def run_dump_ir(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *arguments: str,
    stdin_text: str | None = None,
    stdin_filename: str | None = None,
) -> tuple[int, bytes, str]:
    """Run one invocation and return its exit status, stdout and stderr."""
    monkeypatch.chdir(tmp_path)
    output = io.BytesIO()
    error = io.StringIO()
    stdin = io.StringIO(stdin_text) if stdin_text is not None else None
    if stdin is not None:
        monkeypatch.setattr(cli_dump_ir.sys, "stdin", stdin)
    options = DumpIrOptions(targets=arguments, stdin_filename=stdin_filename)
    exit_code = cli_dump_ir.run_dump_ir(options, output=output, error=error)
    return exit_code, output.getvalue(), error.getvalue()
