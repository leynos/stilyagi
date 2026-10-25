"""Immutable request identity and owned cache-filename contracts."""

import dataclasses as dc
import enum
import hashlib
import json
import re
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = [
    "CACHE_FORMAT_VERSION",
    "CACHE_NAMESPACE_NAME",
    "OWNER_MARKER_BYTES",
    "OWNER_MARKER_NAME",
    "CacheFileKind",
    "ExtractionRequest",
    "cache_entry_name",
    "cache_key",
    "classify_cache_filename",
]

CACHE_FORMAT_VERSION = 1
CACHE_NAMESPACE_NAME = "stilyagi-v1"
OWNER_MARKER_NAME = "owner.json"
OWNER_MARKER_BYTES = b'{"owner":"stilyagi","format":1}\n'
_ENTRY_PATTERN = re.compile(r"[0-9a-f]{64}\.json\Z")
_TEMP_PATTERN = re.compile(r"\.tmp-[0-9a-f]{32}\Z")
_FRONTMATTER_POLICY = "included-v1"


class CacheFileKind(enum.StrEnum):
    """Identify one disposable filename owned by Stilyagi's cache."""

    ENTRY = enum.auto()
    TEMP = enum.auto()


@dc.dataclass(frozen=True, slots=True)
class ExtractionRequest:
    """Describe every input that can change a cached extraction.

    Parameters
    ----------
    source_text
        Exact UTF-8-decoded source text. Encoding it as UTF-8 preserves the
        original source bytes and line endings read by the CLI.
    syntax
        Stable syntax spelling passed to the Rust bridge.
    reported_identity
        User-visible source identity embedded in canonical IR metadata.
    effective_config
        Normalized configuration values without provenance metadata.
    native_extension_digest
        Digest of the loaded native extension binary for this invocation.
    package_version
        Installed Stilyagi package version.
    builtin_pack_signature
        Signature for the enabled built-in rule pack.
    nlp_signature
        Active NLP implementation signature, or ``"inactive"`` when no NLP
        implementation participates in extraction.
    """

    source_text: str
    syntax: str
    reported_identity: str
    effective_config: cabc.Mapping[str, object]
    native_extension_digest: str
    package_version: str
    builtin_pack_signature: str
    nlp_signature: str = "inactive"


def _canonical_json_bytes(value: object) -> bytes:
    """Return compact, key-sorted JSON for normalized identity values."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        message = "cache identity values must be finite JSON data"
        raise ValueError(message) from error


def cache_key(request: ExtractionRequest) -> str:
    """Return the full SHA-256 key for one extraction request.

    The effective values are hashed separately from provenance, and sorted JSON
    keeps equivalent mapping insertion orders on the same key.

    Returns
    -------
    str
        A lowercase SHA-256 digest covering every extraction-affecting input.

    Examples
    --------
    >>> request = ExtractionRequest(
    ...     "# Title", "markdown", "README.md", {}, "native", "1.0", "builtin"
    ... )
    >>> len(cache_key(request))
    64
    """
    source_digest = hashlib.sha256(request.source_text.encode("utf-8")).hexdigest()
    config_digest = hashlib.sha256(
        _canonical_json_bytes(request.effective_config)
    ).hexdigest()
    identity = {
        "builtin_pack_signature": request.builtin_pack_signature,
        "cache_format": CACHE_FORMAT_VERSION,
        "effective_config_sha256": config_digest,
        "frontmatter_policy": _FRONTMATTER_POLICY,
        "native_extension_digest": request.native_extension_digest,
        "nlp_signature": request.nlp_signature,
        "package_version": request.package_version,
        "reported_identity": request.reported_identity,
        "source_sha256": source_digest,
        "syntax": request.syntax,
    }
    return hashlib.sha256(_canonical_json_bytes(identity)).hexdigest()


def cache_entry_name(key: str) -> str:
    """Return the owned JSON filename for a valid lowercase SHA-256 key.

    Returns
    -------
    str
        The exact lowercase-key filename owned by the cache namespace.

    Raises
    ------
    ValueError
        If *key* is not 64 lowercase hexadecimal characters.
    """
    if re.fullmatch(r"[0-9a-f]{64}", key) is None:
        msg = "cache key must be 64 lowercase hexadecimal characters"
        raise ValueError(msg)
    return f"{key}.json"


def classify_cache_filename(filename: str) -> CacheFileKind | None:
    """Classify an exact entry or exclusive temporary filename.

    Returns
    -------
    CacheFileKind or None
        The owned entry kind, or ``None`` for every other filename.
    """
    if _ENTRY_PATTERN.fullmatch(filename):
        return CacheFileKind.ENTRY
    if _TEMP_PATTERN.fullmatch(filename):
        return CacheFileKind.TEMP
    return None
