"""Rejection contracts for serialized cache envelopes and extraction identities."""

import dataclasses as dc
import hashlib
import json
import typing as typ

import pytest
from stilyagi.cache.model import (
    CACHE_FORMAT_VERSION,
    CacheFileKind,
    ExtractionRequest,
    cache_key,
    classify_cache_filename,
)
from stilyagi.cache.storage_primitives import CacheStorageError

if typ.TYPE_CHECKING:
    import pathlib


def _request(source_text: str = "# Title\n") -> ExtractionRequest:
    """Build one minimal extraction identity for envelope validation."""
    return ExtractionRequest(
        source_text=source_text,
        syntax="markdown",
        reported_identity="notes.md",
        effective_config={},
        native_extension_digest="native-a",
        package_version="1.2.3",
        builtin_pack_signature="builtin-a",
    )


def _identity() -> dict[str, object]:
    """Return source metadata that matches the request's extraction identity."""
    request = _request()
    return {
        "content_hash": "sha256:"
        + hashlib.sha256(request.source_text.encode()).hexdigest(),
        "syntax": request.syntax,
        "path": request.reported_identity,
    }


def _envelope(**overrides: object) -> str:
    """Return one valid envelope with the requested fields replaced."""
    ir_json = json.dumps({"document": {}})
    fields: dict[str, object] = {
        "format": CACHE_FORMAT_VERSION,
        "ir_json": ir_json,
        "ir_sha256": hashlib.sha256(ir_json.encode()).hexdigest(),
        "key": "0" * 64,
    }
    fields.update(overrides)
    if "ir_json" in overrides and "ir_sha256" not in overrides:
        ir_text = str(fields["ir_json"])
        fields["ir_sha256"] = hashlib.sha256(ir_text.encode()).hexdigest()
    return json.dumps(fields)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # The model module's classifier is certified over its own forms. These
        # two name shapes only cleanup depends on: the ownership marker it must
        # leave alone, and a foreign suffix beside a genuine digest.
        pytest.param("owner.json", None, id="owner-marker"),
        pytest.param("0" * 64 + ".json.bak", None, id="unexpected-suffix"),
    ],
)
def test_classify_cache_filename_refuses_names_cleanup_must_not_remove(
    name: str,
    expected: CacheFileKind | None,
) -> None:
    """Recognize only the exact entry and temporary filename shapes."""
    assert classify_cache_filename(name) is expected, (
        "cleanup must distinguish owned leaves from foreign names"
    )


def test_canonical_identity_rejects_non_json_configuration() -> None:
    """Refuse effective configuration the cache cannot hash deterministically."""
    request = dc.replace(_request(), effective_config={"broken": object()})

    with pytest.raises(ValueError, match="finite JSON data"):
        cache_key(request)


def _decode(content: str | bytes, key: str = "0" * 64) -> object:
    """Decode one cache envelope, returning the raised error for inspection."""
    from stilyagi.cache.ir import decode_cache_entry

    payload = content.encode() if isinstance(content, str) else content
    return decode_cache_entry(payload, key=key, request=_request())


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param(b"\xff\xfe", "not valid JSON", id="undecodable"),
        pytest.param("{", "not valid JSON", id="truncated-json"),
        pytest.param(json.dumps({}), "unexpected fields", id="missing-fields"),
        pytest.param(
            json.dumps({
                "format": CACHE_FORMAT_VERSION,
                "ir_json": "{}",
                "ir_sha256": "0" * 64,
                "key": "0" * 64,
                "extra": 1,
            }),
            "unexpected fields",
            id="extra-field",
        ),
        pytest.param(
            _envelope(format="1"), "format is unsupported", id="string-format"
        ),
        pytest.param(
            _envelope(format=99), "format is unsupported", id="unknown-format"
        ),
        pytest.param(_envelope(key="1" * 64), "key differs", id="wrong-key"),
        pytest.param(
            _envelope(ir_sha256="short"), "checksum is malformed", id="digest"
        ),
        pytest.param(
            _envelope(ir_sha256=42), "checksum is malformed", id="digest-type"
        ),
        pytest.param(_envelope(ir_json=42), "IR is not a string", id="ir-type"),
        pytest.param(
            _envelope(ir_sha256="0" * 64),
            "checksum does not match",
            id="mismatch",
        ),
        pytest.param(
            _envelope(ir_json="{"), "Rust rejected cached canonical IR", id="bad-ir"
        ),
        pytest.param(
            _envelope(ir_json="[]"), "Rust rejected cached canonical IR", id="ir-root"
        ),
        # A JSON document may escape an unpaired surrogate, and `json.loads`
        # accepts it. Summing the checksum then has to encode it, which UTF-8
        # refuses. That must classify as a malformed entry so the caller
        # extracts afresh instead of failing the whole command.
        pytest.param(
            # The raw bytes must carry the escape sequence, because the
            # surrogate cannot be encoded here to build the envelope.
            b'{"format": 1, "ir_json": "\\ud800", "ir_sha256": "'
            + b"0" * 64
            + b'", "key": "'
            + b"0" * 64
            + b'"}',
            "IR is not UTF-8 encodable",
            id="unpaired-surrogate",
        ),
    ],
)
def test_decode_cache_entry_rejects_invalid_envelopes(
    content: str | bytes,
    expected: str,
) -> None:
    """Report every malformed envelope as one classified cache-entry failure."""
    from stilyagi.cache.ir import InvalidCacheEntryError

    with pytest.raises(InvalidCacheEntryError, match=expected):
        _decode(content)


@pytest.mark.parametrize(
    ("ir_payload", "expected"),
    [
        pytest.param([], "no document mapping", id="ir-not-a-mapping"),
        pytest.param({"regions": []}, "no source identity", id="missing-document"),
        pytest.param(
            {"document": []}, "no source identity", id="document-not-a-mapping"
        ),
        pytest.param(
            {"document": {"content_hash": "sha256:0"}},
            "source hash differs from its cache key",
            id="wrong-hash",
        ),
        # The hash has to match here, or the hash check fires first and this
        # case never reaches the syntax comparison it exists to exercise.
        pytest.param(
            {"document": {**_identity(), "syntax": "python_docstring"}},
            "syntax differs from its cache key",
            id="wrong-syntax",
        ),
        pytest.param(
            {"document": {**_identity(), "path": "other.md"}},
            "path differs from its cache key",
            id="wrong-path",
        ),
    ],
)
def test_decode_cache_entry_rejects_mismatched_source_identity(
    ir_payload: object,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject hydrated IR whose source metadata disagrees with its cache key.

    Each case names the specific reason, because a shared prefix would accept a
    regression that makes one case fail for a different reason than the one it
    was written to pin.
    """
    from stilyagi.cache import ir
    from stilyagi.cache.ir import InvalidCacheEntryError

    monkeypatch.setattr(
        ir.engine,
        "hydrate_ir_json",
        lambda _canonical: typ.cast("object", _Hydrated(ir_payload)),
    )

    with pytest.raises(InvalidCacheEntryError, match=expected):
        _decode(_envelope())


class _Hydrated:
    """Stand in for one hydrated extraction result with a chosen IR payload."""

    def __init__(self, ir_payload: object) -> None:
        """Wrap the IR payload in the document shape hydration returns."""
        self.document = typ.cast("object", _Document(ir_payload))


class _Document:
    """Hold exactly the IR payload the identity check inspects."""

    def __init__(self, ir_payload: object) -> None:
        """Store the payload as the hydrated document's IR."""
        self.ir = ir_payload


def _true_ir_payload() -> dict[str, object]:
    """Return the IR payload whose metadata matches the request identity."""
    return {"document": _identity()}


def test_decode_cache_entry_accepts_a_matching_source_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept hydrated IR whose metadata matches its request identity."""
    from stilyagi.cache import ir

    hydrated = _Hydrated(_true_ir_payload())
    monkeypatch.setattr(
        ir.engine, "hydrate_ir_json", lambda _canonical: typ.cast("object", hydrated)
    )

    assert _decode(_envelope()) is hydrated, (
        "a self-consistent cached entry must hydrate unchanged"
    )


def test_storage_error_carries_its_original_cause(tmp_path: pathlib.Path) -> None:
    """Retain the underlying failure when a cache operation is refused."""
    from stilyagi.cache import storage_primitives as primitives

    cause = OSError("underlying")
    with pytest.raises(CacheStorageError) as raised:
        primitives._raise_storage_error("cache root was replaced", cause)

    assert raised.value.__cause__ is cause, (
        "a classified cache failure must retain its original OS error"
    )
