"""Encode, validate and hydrate canonical IR cache envelopes."""

import collections.abc as cabc
import hashlib
import json
import re
import typing as typ

from stilyagi import engine

from .model import CACHE_FORMAT_VERSION, ExtractionRequest

_ENVELOPE_FIELDS = frozenset({"format", "key", "ir_sha256", "ir_json"})
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class InvalidCacheEntryError(ValueError):
    """One serialized entry failed its format or request-identity checks."""


def _reject_cache_entry(message: str, cause: Exception | None = None) -> typ.NoReturn:
    """Raise a classified cache-entry failure with its validation detail."""
    if cause is None:
        raise InvalidCacheEntryError(message)
    raise InvalidCacheEntryError(message) from cause


def encode_cache_entry(key: str, canonical_json: str) -> bytes:
    """Serialize canonical IR with an independent checksum."""
    checksum = hashlib.sha256(canonical_json.encode()).hexdigest()
    envelope = {
        "format": CACHE_FORMAT_VERSION,
        "ir_json": canonical_json,
        "ir_sha256": checksum,
        "key": key,
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{encoded}\n".encode()


def _validate_ir_identity(
    result: engine.ExtractionResult,
    request: ExtractionRequest,
) -> None:
    """Reject hydrated IR whose source metadata disagrees with its cache key."""
    payload = result.document.ir
    if not isinstance(payload, cabc.Mapping):
        _reject_cache_entry("canonical IR has no document mapping")
    document = payload.get("document")
    if not isinstance(document, cabc.Mapping):
        _reject_cache_entry("canonical IR has no source identity")
    expected_hash = hashlib.sha256(request.source_text.encode()).hexdigest()
    if document.get("content_hash") != f"sha256:{expected_hash}":
        _reject_cache_entry("canonical IR source hash differs from its cache key")
    if document.get("syntax") != request.syntax:
        _reject_cache_entry("canonical IR syntax differs from its cache key")
    if document.get("path") != request.reported_identity:
        _reject_cache_entry("canonical IR path differs from its cache key")


def _parse_envelope(content: bytes, key: str) -> cabc.Mapping[str, object]:
    """Decode outer JSON and validate its version and key before IR parsing."""
    try:
        envelope = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _reject_cache_entry("cache envelope is not valid JSON", error)
    if not isinstance(envelope, dict) or set(envelope) != _ENVELOPE_FIELDS:
        _reject_cache_entry("cache envelope has unexpected fields")
    if (
        type(envelope.get("format")) is not int
        or envelope["format"] != CACHE_FORMAT_VERSION
    ):
        _reject_cache_entry("cache envelope format is unsupported")
    if envelope.get("key") != key:
        _reject_cache_entry("cache envelope key differs from its filename")
    return typ.cast("cabc.Mapping[str, object]", envelope)


def _canonical_ir(envelope: cabc.Mapping[str, object]) -> str:
    """Validate the serialized IR and its independent checksum."""
    checksum = envelope.get("ir_sha256")
    canonical_json = envelope.get("ir_json")
    if not isinstance(checksum, str) or _DIGEST_PATTERN.fullmatch(checksum) is None:
        _reject_cache_entry("cache envelope checksum is malformed")
    if not isinstance(canonical_json, str):
        _reject_cache_entry("cache envelope IR is not a string")
    actual_checksum = hashlib.sha256(canonical_json.encode()).hexdigest()
    if checksum != actual_checksum:
        _reject_cache_entry("cache envelope IR checksum does not match")
    return canonical_json


def decode_cache_entry(
    content: bytes,
    *,
    key: str,
    request: ExtractionRequest,
) -> engine.ExtractionResult:
    """Validate an outer envelope and hydrate its IR through Rust."""
    envelope = _parse_envelope(content, key)
    canonical_json = _canonical_ir(envelope)
    try:
        hydrated = engine.hydrate_ir_json(canonical_json)
    except (engine.BridgeExtractionError, TypeError, ValueError, RuntimeError) as error:
        _reject_cache_entry("Rust rejected cached canonical IR", error)
    _validate_ir_identity(hydrated, request)
    return hydrated
