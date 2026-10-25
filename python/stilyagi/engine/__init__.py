"""Execution-engine package boundary for Stilyagi."""

from .api import extract_document, extract_document_result, hydrate_ir_json
from .extraction import BridgeExtractionError, ExtractionResult, supported_region_kinds
from .planner import ExecutionPlan
from .renderers import RendererRegistry, RunSummary
from .runner import EngineRunner

__all__ = [
    "BridgeExtractionError",
    "EngineRunner",
    "ExecutionPlan",
    "ExtractionResult",
    "RendererRegistry",
    "RunSummary",
    "extract_document",
    "extract_document_result",
    "hydrate_ir_json",
    "supported_region_kinds",
]
