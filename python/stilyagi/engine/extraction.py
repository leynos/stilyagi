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
import logging
import typing as typ
from functools import cache

from stilyagi import model
from stilyagi._stilyagi_rs import (
    extract_document as extract_document_bridge,
)
from stilyagi._stilyagi_rs import (
    supported_region_kinds as bridge_supported_region_kinds,
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
_LOGGER = logging.getLogger(__name__)

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


@cache
def _supported_region_kinds() -> tuple[str, ...]:
    """Return bridge region kinds, loaded lazily to keep imports side-effect free."""
    return bridge_supported_region_kinds()


@cache
def _known_ir_region_kinds() -> frozenset[str]:
    """Return the cached canonical region-kind lookup set."""
    return frozenset(_supported_region_kinds())


def supported_region_kinds() -> tuple[str, ...]:
    """Return the stable IR region-kind spellings advertised by the bridge.

    Returns
    -------
    tuple[str, ...]
        Canonical region-kind spellings in bridge order.
    """
    return _supported_region_kinds()


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
    ir_payload = _parse_ir_json(bridge_document.get("ir_json"))
    if ir_payload is not None:
        _warn_unknown_ir_region_kinds(ir_payload)
    return model.Document(
        syntax=model.Syntax(bridge_document["syntax"]),
        regions=tuple(
            model.Region(kind=region["kind"], text=region["text"])
            for region in bridge_document["regions"]
        ),
        ir=ir_payload,
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


def _assert_str_region_field(
    region_dict: dict[str, object], index: int, field: str
) -> str:
    """Return ``region_dict[field]`` as ``str``, or raise ``TypeError``."""
    value = region_dict.get(field)
    if not isinstance(value, str):
        msg = f"expected Rust bridge payload['regions'][{index}][{field!r}] to be str"
        raise TypeError(msg)
    return value


def _coerce_bridge_region(index: int, region: object) -> _BridgeRegion:
    """Validate one raw bridge region before adapting it to Python models."""
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


def _parse_ir_json(ir_json: str | None) -> cabc.Mapping[str, typ.Any] | None:
    """Parse the optional canonical IR JSON bridge field."""
    if ir_json is None:
        return None
    parsed = json.loads(ir_json)
    if not isinstance(parsed, dict):
        msg = "expected Rust bridge payload['ir_json'] to decode to dict"
        raise TypeError(msg)
    return typ.cast("cabc.Mapping[str, typ.Any]", parsed)


def _iter_unknown_region_kinds(
    regions: list[object],
    known_region_kinds: frozenset[str],
) -> cabc.Iterator[tuple[int, str]]:
    """Yield ``(index, kind)`` for every unknown region kind."""
    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            continue
        kind = typ.cast("dict[str, object]", region).get("kind")
        if isinstance(kind, str) and kind not in known_region_kinds:
            yield index, kind


def _warn_unknown_ir_region_kinds(ir_payload: cabc.Mapping[str, typ.Any]) -> None:
    """Warn when canonical IR includes a region kind unknown to this adapter."""
    regions = ir_payload.get("regions")
    if not isinstance(regions, list):
        return
    regions = typ.cast("list[object]", regions)
    for index, _kind in _iter_unknown_region_kinds(regions, _known_ir_region_kinds()):
        _LOGGER.warning(
            "Unknown IR region kind from Rust bridge at index %s",
            index,
        )
