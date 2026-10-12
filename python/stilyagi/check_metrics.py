"""Bounded metrics helpers used by the check command."""

import contextlib
import json
import sys
import time
import typing as typ

from stilyagi import model
from stilyagi._stilyagi_rs import (
    check_metrics_snapshot,
    record_check_run,
    record_checked_file,
    record_diagnostic_severity,
    record_operational_failure,
    record_phase_duration,
    record_skipped_candidates,
    record_unreadable_file,
    reset_check_metrics,
)

__all__ = [
    "record_operational_failure",
    "record_unreadable_file",
    "reset_check_metrics",
]

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.discovery_results import SkippedCandidateCount

_PHASES: typ.Final = frozenset({
    "discovery",
    "read",
    "extract",
    "config",
    "rules",
    "render",
    "total",
})
_METRIC_SYNTAX: typ.Final = {
    model.Syntax.MARKDOWN: "markdown",
    model.Syntax.PYTHON_DOCSTRING: "python",
    model.Syntax.RUST_DOC_COMMENT: "rust",
}


@contextlib.contextmanager
def _measure_phase(phase: str) -> cabc.Iterator[None]:
    """Record elapsed nanoseconds for one closed phase label."""
    if phase not in _PHASES:
        msg = f"unsupported check metric phase: {phase}"
        raise ValueError(msg)
    start = time.perf_counter_ns()
    try:
        yield
    finally:
        record_phase_duration(phase, time.perf_counter_ns() - start)


def _start_check() -> int:
    """Return the monotonic timestamp used to measure one whole check run."""
    return time.perf_counter_ns()


def _record_file(syntax: model.Syntax) -> None:
    """Record one input against its bounded registered syntax label."""
    record_checked_file(_METRIC_SYNTAX[syntax])


def _record_diagnostic_counts(error_count: int, warning_count: int) -> None:
    """Record diagnostic totals with the two fixed severity labels."""
    record_diagnostic_severity("error", error_count)
    record_diagnostic_severity("warning", warning_count)


def _record_skips(
    skipped_by_reason: cabc.Iterable[SkippedCandidateCount],
) -> None:
    """Record discovery's fixed skip-reason totals without path labels."""
    for skipped_count in skipped_by_reason:
        record_skipped_candidates(skipped_count.reason, skipped_count.count)


def _finish_check(
    exit_code: int,
    *,
    verbose: bool,
    started_at_ns: int,
) -> int:
    """Record run duration and outcome before optionally rendering metrics."""
    record_phase_duration("total", time.perf_counter_ns() - started_at_ns)
    outcome = {
        0: "success",
        1: "diagnostic_error",
        2: "operational_error",
    }[exit_code]
    record_check_run(outcome)
    if verbose:
        snapshot = check_metrics_snapshot()
        metrics_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        print(f"stilyagi check metrics: {metrics_json}", file=sys.stderr)
    return exit_code
