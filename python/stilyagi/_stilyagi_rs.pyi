"""Typing stub for the package-scoped Rust extension."""

import typing as typ

class ExtractRegion(typ.TypedDict):
    """Bridge payload for one extracted prose region."""

    kind: str
    text: str

class ExtractDocumentPayload(typ.TypedDict):
    """Bridge payload for one extracted document."""

    syntax: str
    regions: list[ExtractRegion]
    ir_json: typ.NotRequired[str]

def extract_document(
    _source: str,
    _syntax: str,
    _source_path: str | None = None,
    /,
) -> ExtractDocumentPayload:
    """Extract structured document data with an optional reported path.

    Returns an ``ExtractDocumentPayload`` containing ``syntax``, ``regions``,
    and optional canonical IR JSON in ``ir_json``. The optional *source_path*
    is copied into canonical IR while its URI remains absent.

    Raises ``ValueError`` when *syntax* is invalid, ``NotImplementedError``
    when it is recognised but unavailable, and ``TypeError`` for invalid
    argument types.
    """

def hydrate_ir_json(_canonical_json: str, /) -> ExtractDocumentPayload:
    """Restore a validated canonical IR document through Rust's schema types.

    Returns an ``ExtractDocumentPayload`` with the original canonical IR JSON.
    Cache callers must verify the cache key and checksum before hydration.

    Raises ``ValueError`` when the JSON, known field types, schema version, or
    syntax is unsupported.
    """

def hello() -> str: ...
def authored_directive_error_codes() -> tuple[str, ...]: ...
def supported_region_kinds() -> tuple[str, ...]: ...
def supported_syntaxes() -> tuple[str, ...]: ...
def reset_check_metrics() -> None: ...
def record_check_run(_outcome: str, /) -> None: ...
def record_checked_file(_syntax: str, /) -> None: ...
def record_diagnostic_severity(_severity: str, _count: int, /) -> None: ...
def record_skipped_candidates(_reason: str, _count: int, /) -> None: ...
def record_unreadable_file() -> None: ...
def record_operational_failure(_kind: str, /) -> None: ...
def record_phase_duration(_phase: str, _duration_nanoseconds: int, /) -> None: ...
def check_metrics_snapshot() -> dict[str, object]: ...
