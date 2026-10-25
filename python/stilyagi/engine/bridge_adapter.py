"""Validate and adapt typed payloads shared by extraction and hydration."""

import json
import typing as typ

from stilyagi import model

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _BridgeRegion(typ.TypedDict):
    """One validated region returned by the Rust bridge."""

    kind: str
    text: str


class _BridgeDocument(typ.TypedDict):
    """One validated document returned by the Rust bridge."""

    syntax: str
    regions: list[_BridgeRegion]
    ir_json: typ.NotRequired[str]


def adapt_bridge_payload(
    payload: object,
) -> tuple[model.Document, str | None]:
    """Validate one bridge payload and adapt it to the shared Python model."""
    bridge_document = _coerce_bridge_document(payload)
    canonical_json = bridge_document.get("ir_json")
    ir_payload = _parse_ir_json(canonical_json)
    document = model.Document(
        syntax=model.Syntax(bridge_document["syntax"]),
        regions=tuple(
            model.Region(kind=region["kind"], text=region["text"])
            for region in bridge_document["regions"]
        ),
        ir=ir_payload,
    )
    return document, canonical_json


def _extract_syntax_field(payload_dict: dict[str, object]) -> str:
    """Return the required string syntax field."""
    syntax = payload_dict.get("syntax")
    if not isinstance(syntax, str):
        msg = "expected Rust bridge payload['syntax'] to be str"
        raise TypeError(msg)
    return syntax


def _extract_regions_field(payload_dict: dict[str, object]) -> list[object]:
    """Return the required list of bridge regions."""
    regions = payload_dict.get("regions")
    if not isinstance(regions, list):
        msg = "expected Rust bridge payload['regions'] to be list"
        raise TypeError(msg)
    return typ.cast("list[object]", regions)


def _extract_ir_json_field(payload_dict: dict[str, object]) -> str | None:
    """Return optional canonical JSON when the bridge supplied a string."""
    ir_json = payload_dict.get("ir_json")
    if ir_json is not None and not isinstance(ir_json, str):
        msg = "expected Rust bridge payload['ir_json'] to be str when present"
        raise TypeError(msg)
    return ir_json


def _coerce_bridge_document(payload: object) -> _BridgeDocument:
    """Validate bridge fields before adapting the typed model."""
    if not isinstance(payload, dict):
        msg = f"expected dict payload from Rust bridge, got {type(payload).__name__}"
        raise TypeError(msg)
    payload_dict = typ.cast("dict[str, object]", payload)
    syntax = _extract_syntax_field(payload_dict)
    regions = _extract_regions_field(payload_dict)
    ir_json = _extract_ir_json_field(payload_dict)
    normalized_regions = list(
        map(_coerce_bridge_region, range(len(regions)), regions, strict=True),
    )
    document: _BridgeDocument = {"syntax": syntax, "regions": normalized_regions}
    if ir_json is not None:
        document["ir_json"] = ir_json
    return document


def _assert_str_region_field(
    region_dict: dict[str, object], index: int, field: str
) -> str:
    """Return one bridge region field after checking its string type."""
    value = region_dict.get(field)
    if not isinstance(value, str):
        msg = f"expected Rust bridge payload['regions'][{index}][{field!r}] to be str"
        raise TypeError(msg)
    return value


def _coerce_bridge_region(index: int, region: object) -> _BridgeRegion:
    """Validate the kind and text fields for one bridge region."""
    if not isinstance(region, dict):
        msg = (
            "expected Rust bridge payload['regions']["
            f"{index}] to be dict, got {type(region).__name__}"
        )
        raise TypeError(msg)
    region_dict = typ.cast("dict[str, object]", region)
    return {
        "kind": _assert_str_region_field(region_dict, index, "kind"),
        "text": _assert_str_region_field(region_dict, index, "text"),
    }


def _parse_ir_json(ir_json: str | None) -> cabc.Mapping[str, object] | None:
    """Decode the optional canonical IR object from the bridge payload."""
    if ir_json is None:
        return None
    parsed = json.loads(ir_json)
    if not isinstance(parsed, dict):
        msg = "expected Rust bridge payload['ir_json'] to decode to dict"
        raise TypeError(msg)
    return typ.cast("cabc.Mapping[str, object]", parsed)
