"""Helpers for normalising canonical IR snapshots."""

from __future__ import annotations

import json
import typing as typ

type JSONType = dict[str, JSONType] | list[JSONType] | str | int | float | bool | None

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


def load_insta_json_snapshot(path: pathlib.Path) -> dict[str, JSONType]:
    """Load the JSON payload stored after an insta snapshot metadata header."""
    _header, json_payload = path.read_text(encoding="utf-8").split(
        "\n---\n", maxsplit=1
    )
    parsed = json.loads(json_payload)
    if not isinstance(parsed, dict):
        raise TypeError
    return typ.cast("dict[str, JSONType]", parsed)


def normalize_ir_identity(
    ir: cabc.Mapping[str, JSONType],
    *,
    producer_name: str,
    producer_version_placeholder: str,
) -> dict[str, JSONType]:
    """Normalise volatile producer and source-identity fields for snapshots."""
    normalized = json.loads(json.dumps(ir))
    if not isinstance(normalized, dict):
        raise TypeError

    document = typ.cast("dict[str, JSONType]", normalized["document"])
    document["content_hash"] = "<content-hash>"
    document["path"] = "<normalized>"
    document["uri"] = "<normalized>"

    for producer in typ.cast("list[dict[str, JSONType]]", normalized["producers"]):
        if producer["name"] == producer_name:
            producer["version"] = producer_version_placeholder

    return typ.cast("dict[str, JSONType]", normalized)
