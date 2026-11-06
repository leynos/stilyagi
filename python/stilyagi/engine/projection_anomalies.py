"""Bounded reporting for the IR anomalies the rule projection recovers from.

The projection drops an IR entry it cannot use and demotes a segment whose
advertised span does not address its text. Neither is silent: this module owns
the fixed vocabulary those recoveries are counted under, and the one place a
document's tally becomes a metric and a log line.

Keeping the vocabulary here, rather than at each drop site, is what lets a
caller add a recovery path without inventing an unbounded label. The metric
labels stay fixed and path-free; the log line names the document by the path
the user already supplied, so a degraded check can be traced to the file it
under-read. Neither carries IR or segment text.

Reporting happens once per document, at the rule runner. The projection itself
only builds the snapshot, so a read-only query can never count the same
document twice.
"""

import collections as col
import logging
import typing as typ

from stilyagi import check_metrics

__all__ = [
    "ANOMALY_KINDS",
    "AnomalyCounts",
    "AnomalyTally",
    "anomaly_snapshot",
    "report_anomalies",
]

_LOGGER = logging.getLogger(__name__)

#: Every recoverable anomaly, as its fixed metric label, in reporting order.
ANOMALY_KINDS: typ.Final = (
    "malformed_node",
    "invalid_node_span",
    "malformed_region",
    "malformed_segment",
    "invalid_segment_span",
    "source_mismatch",
)

#: Anomaly counts for one projection, keyed by their fixed metric label while
#: the projection is still being built.
AnomalyTally = col.Counter[str]

#: An immutable anomaly snapshot in reporting order, as ``(label, count)``.
type AnomalyCounts = tuple[tuple[str, int], ...]


def anomaly_snapshot(anomalies: AnomalyTally) -> AnomalyCounts:
    """Return one projection's non-zero counts in fixed reporting order.

    Parameters
    ----------
    anomalies:
        The tally a projection accumulated while recovering from its IR.

    Returns
    -------
    AnomalyCounts
        Every label that was counted, ordered by :data:`ANOMALY_KINDS` so two
        projections of the same document produce the same snapshot.

    Examples
    --------
    >>> anomaly_snapshot(col.Counter({"source_mismatch": 2}))
    (('source_mismatch', 2),)
    """
    return tuple((kind, anomalies[kind]) for kind in ANOMALY_KINDS if anomalies[kind])


def report_anomalies(counts: AnomalyCounts, *, document_id: str) -> None:
    """Count and log what one document's projection recovered from.

    This is the reporting boundary: one call per document, from the rule
    runner, which is the only place that knows both the snapshot and the path
    the user supplied.

    Parameters
    ----------
    counts:
        One document's anomaly snapshot.
    document_id:
        The reported path of the document. It is the caller's own spelling, so
        it names the file without exposing anything the user did not provide.

    Examples
    --------
    >>> report_anomalies((), document_id="docs/example.md")
    """
    if not counts:
        return
    check_metrics._record_projection_anomalies(dict(counts))
    total = sum(count for _, count in counts)
    detail = ", ".join(f"{kind}={count}" for kind, count in counts)
    _LOGGER.info(
        "projection recovered anomalies: total=%d; %s",
        total,
        detail,
        extra={"operation": "projection_anomalies", "path": document_id},
    )
