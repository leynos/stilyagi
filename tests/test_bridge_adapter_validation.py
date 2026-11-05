"""Validation contracts for Rust bridge payload adaptation boundaries."""

import json

import pytest
from stilyagi import model
from stilyagi.engine import bridge_adapter

_REGION: dict[str, object] = {"kind": "prose", "text": "Hello"}


def _payload(**overrides: object) -> dict[str, object]:
    """Return a valid bridge payload with the requested fields replaced."""
    payload: dict[str, object] = {
        "syntax": "markdown",
        "regions": [dict(_REGION)],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param([], "expected dict payload", id="non-dict-root"),
        pytest.param(
            _payload(syntax=42), r"payload\['syntax'\] to be str", id="syntax-type"
        ),
        pytest.param(
            _payload(regions="prose"),
            r"payload\['regions'\] to be list",
            id="regions-type",
        ),
        pytest.param(
            _payload(ir_json=42),
            r"payload\['ir_json'\] to be str",
            id="ir-json-type",
        ),
        pytest.param(
            _payload(regions=["prose"]),
            r"payload\['regions'\]\[0\] to be dict",
            id="region-not-a-mapping",
        ),
        pytest.param(
            _payload(regions=[{"kind": 1, "text": "x"}]),
            r"payload\['regions'\]\[0\]\['kind'\] to be str",
            id="region-kind-type",
        ),
        pytest.param(
            _payload(regions=[{"kind": "prose", "text": None}]),
            r"payload\['regions'\]\[0\]\['text'\] to be str",
            id="region-text-type",
        ),
        pytest.param(_payload(ir_json="[]"), "decode to dict", id="ir-json-not-object"),
    ],
)
def test_adapt_bridge_payload_rejects_ill_typed_fields(
    payload: object,
    expected: str,
) -> None:
    """Report each bridge field that cannot be adapted to the shared model."""
    with pytest.raises(TypeError, match=expected):
        bridge_adapter.adapt_bridge_payload(payload)


def test_adapt_bridge_payload_accepts_an_absent_ir_json() -> None:
    """Adapt a payload whose extractor supplied no canonical IR."""
    document, canonical_json = bridge_adapter.adapt_bridge_payload(_payload())

    assert canonical_json is None, "an absent IR must stay absent after adaptation"
    assert document.ir is None, "an absent IR must produce a document without one"
    assert document.regions == (model.Region(kind="prose", text="Hello"),), (
        "the supplied region must adapt unchanged"
    )


def test_adapt_bridge_payload_accepts_a_canonical_ir_object() -> None:
    """Adapt a payload whose canonical IR decodes to one document mapping."""
    canonical = json.dumps({"document": {"path": "notes.md"}})
    payload = _payload(ir_json=canonical)
    payload["regions"] = [dict(_REGION), {"kind": "code", "text": "print()"}]

    document, canonical_json = bridge_adapter.adapt_bridge_payload(payload)

    assert canonical_json == canonical, "the canonical IR text must be preserved"
    assert document.ir == {"document": {"path": "notes.md"}}, (
        "the decoded IR mapping must be attached to the document"
    )
    assert len(document.regions) == 2, "every supplied region must adapt in order"
    assert document.regions[1].kind == "code", "region kinds must be preserved"
