"""Parsing for the records the recording probes append to their log.

A probe appends one JSON object per line. A live run polls that file while a
probe may be mid-write, so the final line can be incomplete; nothing else may
be. Parsing therefore has two modes, and the strict one is the default: a
completed run that cannot account for every line has lost a record, and an
assertion over the surviving records would then pass for the wrong reason.

The record shape is validated here rather than at each call site, so a
malformed line is a reading finding naming the log, not a `KeyError` or
`TypeError` from wherever the record happened to be read.
"""

import json
import typing as typ

from tests.support.build_standard import ToolInvocation
from tests.support.errors import ReadingError

if typ.TYPE_CHECKING:
    import pathlib

#: The reading these helpers report, as a failure names it.
READER: typ.Final = "probe_log"


def read_records(
    log: pathlib.Path, *, live: bool = False
) -> tuple[ToolInvocation, ...]:
    """Return the records a probe log holds, in the order they were appended.

    Parameters
    ----------
    log
        The probe log. A file that does not exist holds no records.
    live
        Whether Make may still be writing. When true, one unparsable final
        line is skipped as torn; when false, every line must parse.

    Returns
    -------
    tuple
        Each complete record, in order.

    Raises
    ------
    ReadingError
        If a line that must parse is not JSON, or decodes to something that is
        not a probe record.
    """
    if not log.exists():
        return ()
    lines = log.read_text(encoding="utf-8").splitlines()
    records: list[ToolInvocation] = []
    for number, line in enumerate(lines, start=1):
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as error:
            if live and number == len(lines):
                break
            message = f"probe log line {number} is not JSON: {error}"
            raise ReadingError(message, reader=READER, path=str(log)) from error
        records.append(_record(decoded, log, number))
    return tuple(records)


def identity(record: ToolInvocation) -> str:
    """Return the text a probe matches its block and fail selectors against."""
    return f"{record.program} {' '.join(record.args)}"


def _record(raw: object, log: pathlib.Path, number: int) -> ToolInvocation:
    """Return one decoded log line as an invocation, or reject its shape."""
    if not isinstance(raw, dict):
        raise _malformed(log, number, "a record must be an object")
    program = raw.get("program")
    args = raw.get("args")
    env = raw.get("env")
    phase = raw.get("phase", "start")
    if not isinstance(program, str):
        raise _malformed(log, number, "program must be a string")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        raise _malformed(log, number, "args must be a list of strings")
    if not isinstance(env, dict):
        raise _malformed(log, number, "env must be an object")
    if not isinstance(phase, str):
        raise _malformed(log, number, "phase must be a string")
    return ToolInvocation(program, tuple(args), dict(env), phase)


def _malformed(log: pathlib.Path, number: int, detail: str) -> ReadingError:
    """Return the finding for a line that decoded but is not a record."""
    message = f"probe log line {number} is not a record: {detail}"
    return ReadingError(message, reader=READER, path=str(log))
