"""Execution-engine package boundary for Stilyagi."""

from .extraction import extract_document, supported_region_kinds
from .fixes import FixPlan
from .planner import ExecutionPlan
from .renderers import RendererRegistry
from .runner import EngineRunner

__all__ = [
    "EngineRunner",
    "ExecutionPlan",
    "FixPlan",
    "RendererRegistry",
    "extract_document",
    "supported_region_kinds",
]
