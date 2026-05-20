"""Tests for private golden IR, CLI snapshot, and round-trip helpers."""

from __future__ import annotations

import dataclasses as dc
import typing as typ

import pytest
from pytest_bdd import given, scenario, then, when
from stilyagi import cli
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.golden_ir import golden_markdown_ir_fixture
from tests.support.round_trip import (
    OverlappingEditError,
    SourceEdit,
    SyntheticEdit,
    SyntheticSpanError,
    apply_round_trip_edits,
)

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


@scenario(
    "../features/stilyagi_round_trip_helpers.feature",
    "Source-backed edits preserve untouched text",
)
def test_source_backed_edits_preserve_untouched_text() -> None:
    """Run the private round-trip helper BDD scenario."""


@pytest.fixture
def round_trip_state() -> dict[str, object]:
    """Return scenario state for round-trip BDD steps."""
    return {}


@given("a source document for round-trip testing")
def source_document_for_round_trip_testing(
    round_trip_state: dict[str, object],
) -> None:
    """Store a simple source document with a distinct editable middle."""
    round_trip_state["source"] = "before middle after"


@when("I replace the editable middle span")
def replace_the_editable_middle_span(round_trip_state: dict[str, object]) -> None:
    """Apply a single source-backed edit through the private helper."""
    source = round_trip_state["source"]
    assert isinstance(source, str)
    round_trip_state["result"] = apply_round_trip_edits(
        source,
        (SourceEdit(7, 13, "CENTER"),),
    )


@then("the round-trip helper preserves the surrounding text")
def round_trip_helper_preserves_surrounding_text(
    round_trip_state: dict[str, object],
) -> None:
    """Assert the scenario-visible edit result."""
    result = typ.cast("object", round_trip_state["result"])
    assert result == apply_round_trip_edits(
        "before middle after",
        (SourceEdit(7, 13, "CENTER"),),
    )


def test_golden_markdown_ir_matches_json_snapshot(
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the private Python golden IR shape for the shared Markdown fixture."""
    document = golden_markdown_ir_fixture()

    assert document.as_snapshot_payload() == snapshot(
        extension_class=JSONSnapshotExtension,
    )


def test_cli_placeholder_output_matches_snapshot(
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
) -> None:
    """Pin the current placeholder CLI contract without volatile values."""
    exit_code = cli.main()
    captured = capsys.readouterr()

    assert {
        "exit_code": exit_code,
        "stdout": captured.out,
        "stderr": captured.err,
    } == snapshot(extension_class=JSONSnapshotExtension)


def test_round_trip_edits_apply_source_backed_replacements() -> None:
    """Apply valid source-backed edits in byte-order-equivalent string order."""
    result = apply_round_trip_edits(
        "alpha beta gamma",
        (
            SourceEdit(0, 5, "ALPHA"),
            SourceEdit(11, 16, "GAMMA"),
        ),
    )

    assert result == dc.replace(result, after="ALPHA beta GAMMA")


def test_round_trip_edits_accept_adjacent_ranges() -> None:
    """Adjacent source ranges are deterministic and safe to apply."""
    result = apply_round_trip_edits(
        "abcdef",
        (
            SourceEdit(0, 3, "ABC"),
            SourceEdit(3, 6, "DEF"),
        ),
    )

    assert result.after == "ABCDEF"


def test_round_trip_edits_reject_synthetic_spans() -> None:
    """Synthetic spans cannot be edited because they are not source-backed."""
    with pytest.raises(SyntheticSpanError, match="synthetic segment"):
        apply_round_trip_edits(
            "source",
            (SyntheticEdit("inserted separator", "replacement"),),
        )


def test_round_trip_edits_reject_overlapping_non_identical_ranges() -> None:
    """Overlapping source edits are ambiguous and must fail before mutation."""
    with pytest.raises(OverlappingEditError, match="overlapping edit spans"):
        apply_round_trip_edits(
            "abcdef",
            (
                SourceEdit(1, 4, "BCD"),
                SourceEdit(3, 5, "DE"),
            ),
        )


def test_round_trip_edits_preserve_untouched_ranges() -> None:
    """Source text outside edited ranges remains byte-for-byte identical."""
    result = apply_round_trip_edits(
        "before middle after",
        (SourceEdit(7, 13, "CENTER"),),
    )

    assert result.before == "before middle after"
    assert result.after == "before CENTER after"
    assert result.applied_edits == (SourceEdit(7, 13, "CENTER"),)
