"""Typed adapter for the narrow Rust extraction bridge."""

import typing as typ

from stilyagi import model
from stilyagi._stilyagi_rs import extract_document as extract_document_bridge


class _BridgeRegion(typ.TypedDict):
    """Internal shape returned by the PyO3 bridge for one region."""

    kind: str
    text: str


class _BridgeDocument(typ.TypedDict):
    """Internal shape returned by the PyO3 bridge for one document."""

    syntax: str
    regions: list[_BridgeRegion]


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
    bridge_document = typ.cast(
        "_BridgeDocument",
        extract_document_bridge(source, syntax.value),
    )
    return model.Document(
        syntax=model.Syntax(bridge_document["syntax"]),
        regions=tuple(
            model.Region(kind=region["kind"], text=region["text"])
            for region in bridge_document["regions"]
        ),
    )
