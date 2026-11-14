"""Validation tests for the Rust bridge payload adapter.

The bridge is a trust boundary: a payload that does not match the documented
shape must fail with a named ``TypeError`` rather than reach the model layer
half-validated. The real extractor never emits these payloads, so the tests
inject them at the adapter seam.
"""

import logging

import pytest
from stilyagi import model
from stilyagi.engine import extraction

from tests.support.assertions import assert_with_context


def _extract_with(monkeypatch: pytest.MonkeyPatch, payload: object) -> model.Document:
    """Run ``extract_document`` against a fixed bridge payload."""
    # `_extract_bridge_payload` takes its reported path as a keyword-only
    # argument, so the double must accept keywords as well as positionals.
    monkeypatch.setattr(
        extraction,
        "_extract_bridge_payload",
        lambda _source, _syntax, *, source_path=None: payload,
    )
    return extraction.extract_document("text", model.Syntax.MARKDOWN)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param(
            [],
            "expected dict payload from Rust bridge",
            id="non-dict-payload",
        ),
        pytest.param(
            {"regions": []},
            "to be str",
            id="missing-syntax",
        ),
        pytest.param(
            {"syntax": "markdown", "regions": "nope"},
            "to be list",
            id="non-list-regions",
        ),
        pytest.param(
            {"syntax": "markdown", "regions": [], "ir_json": 1},
            "to be str when present",
            id="non-string-ir-json",
        ),
        pytest.param(
            {"syntax": "markdown", "regions": [42]},
            "to be dict, got int",
            id="non-dict-region",
        ),
        pytest.param(
            {"syntax": "markdown", "regions": [{"text": "x"}]},
            "to be str",
            id="non-string-region-kind",
        ),
        pytest.param(
            {"syntax": "markdown", "regions": [{"kind": "paragraph"}]},
            "to be str",
            id="non-string-region-text",
        ),
        pytest.param(
            {"syntax": "markdown", "regions": [], "ir_json": "[]"},
            "to decode to dict",
            id="non-dict-ir-json",
        ),
    ],
)
def test_a_malformed_bridge_payload_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
    message: str,
) -> None:
    """A payload outside the documented shape fails with a named error."""
    with pytest.raises(TypeError, match=message):
        _extract_with(monkeypatch, payload)


def test_an_absent_ir_payload_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A payload without ``ir_json`` yields a document with no canonical IR."""
    document = _extract_with(
        monkeypatch,
        {"syntax": "markdown", "regions": [{"kind": "paragraph", "text": "x"}]},
    )

    assert document.ir is None, "expected an absent ir_json to yield no IR"


def test_unknown_region_kinds_are_ignored_when_absent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Absent or non-list region data produces no warning."""
    with caplog.at_level(logging.WARNING):
        extraction.warn_unknown_ir_region_kinds(None, operation="test")
        extraction.warn_unknown_ir_region_kinds({"regions": "nope"}, operation="test")

    assert not caplog.records, "expected no warning for absent region data"


def test_an_unknown_region_kind_is_warned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-mapping entry is skipped and an unknown kind is reported."""
    payload = {"regions": [42, {"kind": "mystery"}]}

    with caplog.at_level(logging.WARNING):
        extraction.warn_unknown_ir_region_kinds(payload, operation="test")

    assert len(caplog.records) == 1, "expected exactly one unknown-kind warning"
    assert_with_context(
        "mystery" in caplog.records[0].getMessage(),
        "expected the warning to name the unknown region kind",
    )
