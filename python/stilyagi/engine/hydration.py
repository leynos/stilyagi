"""Restore typed documents from validated Rust-canonical IR JSON."""

from stilyagi._stilyagi_rs import hydrate_ir_json as hydrate_ir_json_bridge

from .bridge_adapter import adapt_bridge_payload
from .extraction import BridgeExtractionError, ExtractionResult


def hydrate_canonical_ir(canonical_json: str) -> ExtractionResult:
    """Hydrate one canonical payload through Rust's shared IR schema."""
    try:
        payload = hydrate_ir_json_bridge(canonical_json)
        document, _ = adapt_bridge_payload(payload)
    except (NotImplementedError, TypeError, ValueError, RuntimeError) as error:
        raise BridgeExtractionError(str(error)) from error
    return ExtractionResult(document, canonical_json)
