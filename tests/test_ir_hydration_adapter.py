"""Public engine hydration keeps Rust's canonical IR contract intact."""

import json

import pytest
from stilyagi import engine, model


def test_hydrate_ir_json_roundtrips_typed_document_and_canonical_bytes() -> None:
    """Restore the typed document and retain Rust's canonical JSON bytes."""
    extracted = engine.extract_document_result(
        "# Café\r\n",
        model.Syntax.MARKDOWN,
        source_path="docs/guide.md",
    )
    assert extracted.canonical_json is not None, (
        "Rust extraction must provide canonical IR"
    )

    hydrated = engine.hydrate_ir_json(extracted.canonical_json)

    assert hydrated.document == extracted.document, (
        "hydration must restore the same typed IR"
    )
    assert hydrated.canonical_json == extracted.canonical_json, (
        "hydration must retain Rust's exact canonical bytes"
    )


@pytest.mark.parametrize(
    "canonical_json",
    [
        pytest.param("{", id="truncated-json"),
        pytest.param("[]", id="wrong-json-root"),
    ],
)
def test_hydrate_ir_json_rejects_malformed_payloads(
    canonical_json: str,
) -> None:
    """Reject malformed JSON and roots that cannot describe an IR document."""
    with pytest.raises(engine.BridgeExtractionError):
        engine.hydrate_ir_json(canonical_json)


def test_hydrate_ir_json_rejects_malformed_known_region_fields() -> None:
    """Reject malformed values for fields in the currently supported IR."""
    original = engine.extract_document_result("# Title", model.Syntax.MARKDOWN)
    assert original.canonical_json is not None, (
        "the source payload must be canonical IR"
    )
    payload = json.loads(original.canonical_json)
    payload["regions"][0]["kind"] = 42

    with pytest.raises(engine.BridgeExtractionError):
        engine.hydrate_ir_json(json.dumps(payload))
