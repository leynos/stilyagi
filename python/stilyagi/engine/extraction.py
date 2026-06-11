"""Typed adapter for the narrow Rust extraction bridge.

Use this module when Python code needs typed `stilyagi.model` documents backed
by the embedded Rust extractor instead of the raw PyO3 payload. It validates
the bridge payload, converts each region into `model.Region`, and returns a
`model.Document` for the requested syntax. Call `extract_document` when you
want the public typed API rather than the raw extension payload.

Example: `from stilyagi import model`
`from stilyagi.engine.extraction import extract_document`
`result = extract_document("# Heading", model.Syntax.MARKDOWN)`
"""

import json
import typing as typ

from stilyagi import model
from stilyagi._stilyagi_rs import (
    extract_document as extract_document_bridge,
)
from stilyagi._stilyagi_rs import supported_syntaxes as bridge_supported_syntaxes


class _BridgeRegion(typ.TypedDict):
    """Internal shape returned by the PyO3 bridge for one region."""

    kind: str
    text: str


class _BridgeDocument(typ.TypedDict):
    """Internal shape returned by the PyO3 bridge for one document."""

    syntax: str
    regions: list[_BridgeRegion]
    ir_json: typ.NotRequired[str]


_PYTHON_SYNTAX_SPELLINGS = frozenset(syntax.value for syntax in model.Syntax)
_SYNTAX_VOCAB_VALIDATED = False

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def _validate_syntax_vocab_once() -> None:
    """Fail fast if the Python and Rust syntax vocabularies drift apart."""
    global _SYNTAX_VOCAB_VALIDATED
    if _SYNTAX_VOCAB_VALIDATED:
        return

    rust_syntax_spellings = frozenset(bridge_supported_syntaxes())
    if rust_syntax_spellings != _PYTHON_SYNTAX_SPELLINGS:
        msg = (
            "Python and Rust syntax spellings differ: "
            f"python={sorted(_PYTHON_SYNTAX_SPELLINGS)!r}, "
            f"rust={sorted(rust_syntax_spellings)!r}"
        )
        raise RuntimeError(msg)
    _SYNTAX_VOCAB_VALIDATED = True


def extract_document(source: str, syntax: model.Syntax) -> model.Document:
    """Extract one minimal document payload through the Rust extension.

    Parameters
    ----------
    source:
        Source text to extract.
    syntax:
        Source syntax understood by the extractor.

    Returns
    -------
    model.Document
        Narrow document payload adapted onto the Python model surface.
    """
    _validate_syntax_vocab_once()
    bridge_document = _coerce_bridge_document(
        extract_document_bridge(source, syntax.value),
    )
    return model.Document(
        syntax=model.Syntax(bridge_document["syntax"]),
        regions=tuple(
            model.Region(kind=region["kind"], text=region["text"])
            for region in bridge_document["regions"]
        ),
        ir=_parse_ir_json(bridge_document.get("ir_json")),
    )


def _extract_syntax_field(payload_dict: dict[str, object]) -> str:
    """Extract and type-check the ``syntax`` field from a raw bridge payload dict."""
    syntax = payload_dict.get("syntax")
    if not isinstance(syntax, str):
        msg = "expected Rust bridge payload['syntax'] to be str"
        raise TypeError(msg)
    return syntax


def _extract_regions_field(payload_dict: dict[str, object]) -> list[object]:
    """Extract and type-check the ``regions`` field from a raw bridge payload dict."""
    regions = payload_dict.get("regions")
    if not isinstance(regions, list):
        msg = "expected Rust bridge payload['regions'] to be list"
        raise TypeError(msg)
    return typ.cast("list[object]", regions)


def _extract_ir_json_field(payload_dict: dict[str, object]) -> str | None:
    """Extract and type-check optional ``ir_json`` from a raw bridge payload dict."""
    ir_json = payload_dict.get("ir_json")
    if ir_json is not None and not isinstance(ir_json, str):
        msg = "expected Rust bridge payload['ir_json'] to be str when present"
        raise TypeError(msg)
    return ir_json


def _coerce_bridge_document(payload: object) -> _BridgeDocument:
    """Validate the raw bridge payload before adapting it to Python models."""
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


def _coerce_bridge_region(index: int, region: object) -> _BridgeRegion:
    """Validate one raw bridge region before adapting it to Python models."""
    if not isinstance(region, dict):
        msg = (
            "expected Rust bridge payload['regions']["
            f"{index}] to be dict, got {type(region).__name__}"
        )
        raise TypeError(msg)
    region_dict = typ.cast("dict[str, object]", region)

    kind = region_dict.get("kind")
    text = region_dict.get("text")
    if not isinstance(kind, str):
        msg = f"expected Rust bridge payload['regions'][{index}]['kind'] to be str"
        raise TypeError(msg)
    if not isinstance(text, str):
        msg = f"expected Rust bridge payload['regions'][{index}]['text'] to be str"
        raise TypeError(msg)

    return {"kind": kind, "text": text}


def _parse_ir_json(ir_json: str | None) -> cabc.Mapping[str, typ.Any] | None:
    """Parse the optional canonical IR JSON bridge field."""
    if ir_json is None:
        return None
    parsed = json.loads(ir_json)
    if not isinstance(parsed, dict):
        msg = "expected Rust bridge payload['ir_json'] to decode to dict"
        raise TypeError(msg)
    return typ.cast("cabc.Mapping[str, typ.Any]", parsed)
