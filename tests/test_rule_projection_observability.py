"""Observability tests for the rule projection's recoverable IR anomalies.

A projection that drops malformed IR must not do so silently: the check would
otherwise report success while a rule never saw the region it was meant to
inspect. These tests pin the fixed metric labels, the immutable snapshot the
projection returns, and the single per-document record the rule runner emits.

They also pin the other half of that contract: projecting and querying a view
are read-only. A query that recorded a metric would count one document's
recoveries again every time a caller asked for a different slice of it.
"""

import io
import logging
import typing as typ

import pytest
from stilyagi import check_metrics, cli, cli_log, config, engine, model
from stilyagi.engine import rule_projection, rule_view
from stilyagi.rules import registry as rules_registry
from stilyagi.rules.base import RegionTarget

if typ.TYPE_CHECKING:
    import pathlib

    from syrupy.assertion import SnapshotAssertion

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

#: One document that provokes three different recoveries at once.
_MIXED_IR: typ.Final[dict[str, object]] = {
    "nodes": [
        "not-a-node",
        {"id": "n1", "span": {"byte_start": 0, "byte_end": 99}},
    ],
    "regions": ["not-a-region"],
}


def _anomaly_counts() -> dict[str, int]:
    """Return the recorded projection anomaly counts."""
    snapshot = check_metrics.check_metrics_snapshot()
    return typ.cast("dict[str, int]", snapshot[_ANOMALY_METRIC])


def _document(ir: dict[str, object]) -> model.Document:
    """Return a Markdown document carrying the given handwritten IR."""
    return model.Document(syntax=model.Syntax.MARKDOWN, ir=ir)


def _project(
    ir: dict[str, object],
    source_bytes: bytes,
) -> rule_projection.DocumentRegionView:
    """Project one handwritten IR envelope."""
    return rule_projection.project(_document(ir), source_bytes=source_bytes)


def _run_rules(ir: dict[str, object], source_bytes: bytes) -> None:
    """Run the builtin pack over one handwritten IR envelope."""
    rules_registry.run_rules(
        rules_registry.RuleRunRequest(
            config=config.StilyagiConfig(),
            config_path=None,
            source_bytes=source_bytes,
            reported_path="docs/example.md",
            document=_document(ir),
        )
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
def test_projection_snapshots_each_recoverable_anomaly(case: _AnomalyCase) -> None:
    """Return every recoverable anomaly under its own fixed label."""
    view = _project(case.ir, case.source_bytes)

    assert view.anomaly_counts == ((case.label, 1),), (
        f"expected one {case.label} anomaly, got {view.anomaly_counts}"
    )


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=case.label) for case in _ANOMALY_CASES],
)
def test_the_boundary_counts_each_anomaly_once(case: _AnomalyCase) -> None:
    """Count every recoverable anomaly once, at the rule runner."""
    check_metrics.reset_check_metrics()

    _run_rules(case.ir, case.source_bytes)

    counts = _anomaly_counts()
    assert counts[case.label] == 1, (
        f"expected one {case.label} anomaly, got {counts[case.label]}"
    )
    assert sum(counts.values()) == 1, (
        f"expected {case.label} to be the only anomaly, got {counts}"
    )


def test_view_queries_leave_metrics_and_logs_unchanged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Projecting and querying a view records nothing, however often it runs."""
    check_metrics.reset_check_metrics()
    document = _document(_MIXED_IR)

    with caplog.at_level(logging.DEBUG):
        for _ in range(2):
            tuple(rule_view.iter_regions(document, source_bytes=b"# Title\n"))
            rule_view.regions_for_target(
                document, RegionTarget(kinds=("heading",)), source_bytes=b"# Title\n"
            )
            rule_view.inline_code_spans(document)
            rule_view.ignore_next_units(document)
            rule_view.project(document, source_bytes=b"# Title\n")

    recorded = _anomaly_counts()
    assert not any(recorded.values()), (
        f"a read-only query must not record a metric, got {recorded}"
    )
    assert not _anomaly_records(caplog), "a read-only query must not log"


def test_the_boundary_logs_one_record_per_document(
    caplog: pytest.LogCaptureFixture,
    snapshot: SnapshotAssertion,
) -> None:
    """Aggregate a document's anomalies into one path-bearing INFO record."""
    check_metrics.reset_check_metrics()

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        _run_rules(_MIXED_IR, b"# Title\n")

    records = _anomaly_records(caplog)
    assert len(records) == 1, f"expected one aggregated record, got {len(records)}"
    record = records[0]
    assert record.levelno == logging.INFO, (
        "the record must be visible at the CLI's supported verbose level"
    )
    assert getattr(record, "path", None) == "docs/example.md", (
        f"expected the reported path, got {getattr(record, 'path', None)!r}"
    )
    message = record.getMessage()
    for expected in ("malformed_node=1", "invalid_node_span=1", "malformed_region=1"):
        assert expected in message, f"expected {expected!r} in {message!r}"
    assert "Title" not in message, "the log must not quote document content"
    assert sum(_anomaly_counts().values()) == 3, "each anomaly is counted once"

    # The user guide documents this record as the reader sees it, so pin the
    # rendered line rather than only the attributes behind it. The CLI's
    # handler is what appends the structured fields, so apply it here. The
    # line itself lives in a snapshot: it is a rendering contract, and a
    # snapshot diff shows a format change far more plainly than a wrapped
    # literal would.
    cli_log.append_structured_fields(record)
    rendered = logging.Formatter(cli_log.LOG_FORMAT).format(record)
    assert rendered == snapshot, (
        f"expected the rendered verbose record, got {rendered!r}"
    )


def test_the_check_command_reports_projection_anomalies(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A verbose check names the document whose IR the projection recovered from."""
    (tmp_path / "doc.md").write_text("# Title\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        engine,
        "extract_document",
        lambda *_args, **_kwargs: _document({"nodes": ["not-a-node"]}),
    )

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        exit_code = cli.run_check(
            cli.CheckOptions(targets=("doc.md",), verbose=True),
            collaborators=cli.CheckCollaborators(output=io.StringIO()),
        )

    assert exit_code == 0, "a recovered anomaly is not itself a finding"
    records = _anomaly_records(caplog)
    assert len(records) == 1, f"expected one record, got {len(records)}"
    assert getattr(records[0], "path", None) == "doc.md", (
        f"expected the checked path, got {getattr(records[0], 'path', None)!r}"
    )
    assert "malformed_node=1" in records[0].getMessage(), (
        "the command-level record must name the anomaly category"
    )


def test_recovered_anomalies_still_drop_or_demote_safely() -> None:
    """Reporting must not change the safe-skip and synthetic-segment contract."""
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

    view = _project(ir, b"hello")

    assert [region.region_id for region in view.regions] == ["r1"], (
        "the malformed region is dropped rather than guessed at"
    )
    (segment,) = view.regions[0].segments
    assert segment.span is None, "a mismatched span is demoted, never trusted"
    assert segment.synthetic_reason == "source_mismatch", (
        "the demotion reason should name the mismatch that caused it"
    )
