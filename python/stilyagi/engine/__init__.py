"""Execution-engine package boundary for Stilyagi."""

from .api import extract_document
from .extraction import BridgeExtractionError, supported_region_kinds
from .fixes import FixPlan
from .planner import ExecutionPlan
from .renderers import RendererRegistry
from .runner import EngineRunner

__all__ = [
    "BridgeExtractionError",
    "EngineRunner",
    "ExecutionPlan",
    "FixPlan",
    "RendererRegistry",
    "extract_document",
    "supported_region_kinds",
]
