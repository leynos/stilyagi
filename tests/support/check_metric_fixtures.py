"""Shared helpers for the `stilyagi check` operational-metrics tests.

The metrics payload is a single JSON line on standard error, so reading it is
the same three steps wherever a test needs it: find the lines carrying the
prefix, take the last one, and decode what follows. Those steps live here
because every metrics test would otherwise spell them out again, and a change
to the prefix or to which record is authoritative would have to be found in
each copy.

The module-level file writer is here for the same reason: several metrics
tests need one Markdown file to check, and writing it is not what any of them
is about.
"""

import json
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

#: The prefix every verbose metrics record is written under.
METRIC_PREFIX = "stilyagi check metrics: "


def metric_lines(stderr: str) -> tuple[str, ...]:
    """Return verbose metrics records from captured stderr."""
    return tuple(line for line in stderr.splitlines() if line.startswith(METRIC_PREFIX))


def metric_payload(records: cabc.Sequence[str]) -> dict[str, typ.Any]:
    """Parse the metrics record a run published last.

    The last record carries the run's final accounting: a verbose run emits a
    metrics line per command, and the assertions here describe the end state,
    so reading the first would measure the process before it finished.
    ``records`` is any sequence of metrics lines in emission order, which lets
    a caller pass captured stderr's lines or a substituted stream's.

    Returns
    -------
    dict[str, Any]
        The decoded final metrics payload.

    Examples
    --------
    >>> record = METRIC_PREFIX + json.dumps({"errors": 1})
    >>> metric_payload([record])
    {'errors': 1}
    """
    return json.loads(records[-1].removeprefix(METRIC_PREFIX))


def recorded_metrics(stderr: str) -> dict[str, typ.Any]:
    """Parse the final metrics payload from captured stderr.

    Returns
    -------
    dict[str, Any]
        The decoded final metrics payload.
    """
    return metric_payload(metric_lines(stderr))


def write_markdown(path: pathlib.Path, title: str) -> None:
    """Write one tiny Markdown file for a metrics test to check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")
