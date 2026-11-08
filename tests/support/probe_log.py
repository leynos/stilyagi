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

import dataclasses as dc
import json
import typing as typ

from tests.support.build_standard import ToolInvocation
from tests.support.errors import ReadingError

if typ.TYPE_CHECKING:
    import pathlib

#: The reading these helpers report, as a failure names it.
READER: typ.Final = "probe_log"

#: Distinguishes an absent field from one whose value is null.
_UNSET: typ.Final = object()


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
        origin = _Origin(log, number)
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as error:
            if live and number == len(lines):
                break
            message = f"probe log line {number} is not JSON: {error}"
            raise ReadingError(message, reader=READER, path=str(log)) from error
        records.append(origin.invocation(decoded))
    return tuple(records)


def identity(record: ToolInvocation) -> str:
    """Return the text a probe matches its block and fail selectors against."""
    return f"{record.program} {' '.join(record.args)}"


@dc.dataclass(frozen=True, slots=True)
class _Origin:
    """The log and line a record came from, so a rejection can name them.

    Every shape check needs both, and a rejection reads better as a method on
    them than as two more parameters on each helper.
    """

    log: pathlib.Path
    number: int

    def reject(self, detail: str) -> typ.NoReturn:
        """Raise the finding for this line."""
        message = f"probe log line {self.number} is not a record: {detail}"
        raise ReadingError(message, reader=READER, path=str(self.log))

    def invocation(self, raw: object) -> ToolInvocation:
        """Return one decoded line as an invocation, or reject its shape."""
        if not isinstance(raw, dict):
            self.reject("a record must be an object")
        return ToolInvocation(
            program=self._text(raw, "program"),
            args=self._texts(raw, "args"),
            env=self._env(raw),
            phase=self._text(raw, "phase", default="start"),
        )

    def _text(
        self,
        raw: dict[str, object],
        field: str,
        *,
        default: object = _UNSET,
    ) -> str:
        """Return a field that must hold text, or its default when absent."""
        value = raw.get(field, default)
        if not isinstance(value, str):
            self.reject(f"{field} must be a string")
        return value

    def _texts(self, raw: dict[str, object], field: str) -> tuple[str, ...]:
        """Return a field that must hold a list of text."""
        value = raw.get(field)
        if not isinstance(value, list):
            self.reject(f"{field} must be a list of strings")
        for item in value:
            if not isinstance(item, str):
                self.reject(f"{field} must be a list of strings")
        return tuple(typ.cast("list[str]", value))

    def _env(self, raw: dict[str, object]) -> dict[str, str | None]:
        """Return the environment a record carries, keyed by variable name."""
        value = raw.get("env")
        if not isinstance(value, dict):
            self.reject("env must be an object")
        return {str(name): self._entry(entry) for name, entry in value.items()}

    def _entry(self, value: object) -> str | None:
        """Return one environment entry, which must be text or null."""
        if value is not None and not isinstance(value, str):
            self.reject("env entries must be text or null")
        return value if isinstance(value, str) else None
