"""Bounded reporting for the IR anomalies the rule projection recovers from.

The projection drops an IR entry it cannot use and demotes a segment whose
advertised span does not address its text. Neither is silent: this module owns
the fixed vocabulary those recoveries are counted under, and the one place a
document's tally becomes a metric and a log line.

Keeping the vocabulary here, rather than at each drop site, is what lets a
caller add a recovery path without inventing an unbounded label. The metric and
the log carry counts only, never IR, segment text, or a path.
"""

import collections as col
import logging
import typing as typ

from stilyagi import check_metrics

__all__ = ["ANOMALY_KINDS", "AnomalyTally", "report_anomalies"]

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

#: Anomaly counts for one projection, keyed by their fixed metric label.
AnomalyTally = col.Counter[str]


def report_anomalies(anomalies: AnomalyTally) -> None:
    """Count and log what one projection recovered from, without its contents.

    Parameters
    ----------
    anomalies:
        One document's anomaly counts, keyed by their fixed metric label.

    Examples
    --------
    >>> report_anomalies(col.Counter())
    """
    if not anomalies:
        return
    check_metrics._record_projection_anomalies(dict(anomalies))
    _LOGGER.debug(
        "projection recovered %d anomalies: %s",
        sum(anomalies.values()),
        ", ".join(
            f"{kind}={anomalies[kind]}" for kind in ANOMALY_KINDS if kind in anomalies
        ),
    )
