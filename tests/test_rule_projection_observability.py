"""Observability tests for the rule projection's recoverable IR anomalies.

A projection that drops malformed IR must not do so silently: the check would
otherwise report success while a rule never saw the region it was meant to
inspect. These tests pin the fixed metric labels and the single aggregated log
line that make that degradation diagnosable.
"""

import logging
import typing as typ

import pytest
from stilyagi import check_metrics, model
from stilyagi.engine import rule_projection

_LOGGER_NAME = "stilyagi.engine.projection_anomalies"
_ANOMALY_METRIC = "stilyagi_check_projection_anomalies_total"


class _AnomalyCase(typ.NamedTuple):
    """One recoverable anomaly: its fixed label and the IR that provokes it."""

    label: str
    ir: dict[str, object]
    source_bytes: bytes


_ANOMALY_CASES: typ.Final = (
    _AnomalyCase(
        label="malformed_node",
        ir={"nodes": ["not-a-node"]},
        source_bytes=b"# Title\n",
    ),
    _AnomalyCase(
        label="invalid_node_span",
        ir={"nodes": [{"id": "n1", "span": {"byte_start": 0, "byte_end": 99}}]},
        source_bytes=b"# Title\n",
    ),
    _AnomalyCase(
        label="malformed_region",
        ir={"regions": ["not-a-region"]},
        source_bytes=b"",
    ),
    _AnomalyCase(
        label="malformed_segment",
        ir={
            "regions": [
                {"id": "r1", "kind": "paragraph", "segments": ["not-a-segment"]}
            ]
        },
        source_bytes=b"",
    ),
    _AnomalyCase(
        label="invalid_segment_span",
        ir={
            "regions": [
                {
                    "id": "r1",
                    "kind": "paragraph",
                    "segments": [
                        {"text": "x", "source": {"byte_start": 3, "byte_end": 1}}
                    ],
                }
            ]
        },
        source_bytes=b"x",
    ),
    _AnomalyCase(
        label="source_mismatch",
        ir={
            "regions": [
                {
                    "id": "r1",
                    "kind": "paragraph",
                    "segments": [
                        {"text": "other", "source": {"byte_start": 0, "byte_end": 5}}
                    ],
                }
            ]
        },
        source_bytes=b"hello",
    ),
)


def _anomaly_counts() -> dict[str, int]:
    """Return the recorded projection anomaly counts."""
    snapshot = check_metrics.check_metrics_snapshot()
    return typ.cast("dict[str, int]", snapshot[_ANOMALY_METRIC])


def _project_document(
    ir: dict[str, object],
    source_bytes: bytes,
    *,
    should_report: bool = True,
) -> rule_projection.DocumentRegionView:
    """Project one handwritten IR envelope under the given reporting choice."""
    document = model.Document(syntax=model.Syntax.MARKDOWN, ir=ir)
    return rule_projection.project(
        document, source_bytes=source_bytes, should_report=should_report
    )


def _anomaly_records(
    caplog: pytest.LogCaptureFixture,
) -> list[logging.LogRecord]:
    """Return the aggregation lines this module logged."""
    return [record for record in caplog.records if record.name == _LOGGER_NAME]


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case.label) for case in _ANOMALY_CASES],
)
def test_projection_counts_each_recoverable_anomaly(case: _AnomalyCase) -> None:
    """Count every recoverable anomaly under its own fixed label."""
    check_metrics.reset_check_metrics()

    _project_document(case.ir, case.source_bytes)

    counts = _anomaly_counts()
    assert counts[case.label] == 1, (
        f"expected one {case.label} anomaly, got {counts[case.label]}"
    )
    assert sum(counts.values()) == 1, (
        f"expected {case.label} to be the only anomaly, got {counts}"
    )


def test_projection_logs_one_aggregated_line_per_document(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Aggregate a document's anomalies into one path-free log line."""
    check_metrics.reset_check_metrics()
    ir: dict[str, object] = {
        "nodes": [
            "not-a-node",
            {"id": "n1", "span": {"byte_start": 0, "byte_end": 99}},
        ],
        "regions": ["not-a-region"],
    }

    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        _project_document(ir, b"# Title\n")

    records = _anomaly_records(caplog)
    assert len(records) == 1, f"expected one aggregated record, got {len(records)}"
    message = records[0].getMessage()
    for expected in ("malformed_node=1", "invalid_node_span=1", "malformed_region=1"):
        assert expected in message, f"expected {expected!r} in {message!r}"
    assert "Title" not in message, "the log must not quote document content"
    assert sum(_anomaly_counts().values()) == 3, "each anomaly is counted once"


def test_projection_can_suppress_duplicate_reporting(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Report nothing when the caller is re-projecting an already-reported file."""
    check_metrics.reset_check_metrics()

    with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
        _project_document({"nodes": ["not-a-node"]}, b"# Title\n", should_report=False)

    assert sum(_anomaly_counts().values()) == 0, "a silent projection records nothing"
    assert not _anomaly_records(caplog), "a silent projection logs nothing"


def test_recovered_anomalies_still_drop_or_demote_safely() -> None:
    """Reporting must not change the safe-skip and synthetic-segment contract."""
    check_metrics.reset_check_metrics()
    ir: dict[str, object] = {
        "regions": [
            {"id": "bad", "kind": None},
            {
                "id": "r1",
                "kind": "paragraph",
                "segments": [
                    {"text": "other", "source": {"byte_start": 0, "byte_end": 5}}
                ],
            },
        ]
    }

    view = _project_document(ir, b"hello")

    assert [region.region_id for region in view.regions] == ["r1"], (
        "the malformed region is dropped rather than guessed at"
    )
    (segment,) = view.regions[0].segments
    assert segment.span is None, "a mismatched span is demoted, never trusted"
    assert segment.synthetic_reason == "source_mismatch", (
        "the demotion reason should name the mismatch that caused it"
    )
