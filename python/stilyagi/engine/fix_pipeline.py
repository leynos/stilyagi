"""Compose safe-fix planning into non-mutating command-line diff previews."""

import dataclasses as dc
import typing as typ

from stilyagi import diagnostics
from stilyagi.engine.fix_planning.diff import unified_diff
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import FixLevel

if typ.TYPE_CHECKING:
    from stilyagi import model
    from stilyagi.config import LintConfig
    from stilyagi.engine.fix_planning.admissibility import EditRejection


@dc.dataclass(frozen=True, slots=True)
class DiffRequest:
    """Inputs required to preview safe edits for one checked source file."""

    source_bytes: bytes
    source_text: str
    reported_path: str
    document: model.Document
    diagnostics: tuple[diagnostics.Diagnostic, ...]
    lint_config: LintConfig


@dc.dataclass(frozen=True, slots=True)
class DiffPreview:
    """The patch and planning rejections produced for one source file."""

    patch: str
    fix_errors: tuple[diagnostics.FixError, ...]


def preview_safe_fixes(request: DiffRequest) -> DiffPreview:
    """Plan safe fixes and render a non-mutating unified diff preview."""
    plan = plan_fixes(
        FixPlanRequest(
            source_bytes=request.source_bytes,
            document=request.document,
            diagnostics=request.diagnostics,
            level=FixLevel.SAFE,
            lint_config=request.lint_config,
        )
    )
    if plan.fixed_bytes is None:
        return DiffPreview("", _as_fix_errors(request.reported_path, plan.rejections))
    return DiffPreview(
        unified_diff(
            request.source_text,
            plan.fixed_bytes.decode("utf-8"),
            request.reported_path,
        ),
        _as_fix_errors(request.reported_path, plan.rejections),
    )


def _as_fix_errors(
    reported_path: str,
    rejections: tuple[EditRejection, ...],
) -> tuple[diagnostics.FixError, ...]:
    """Translate planner rejections into the separate public error channel."""
    return tuple(
        diagnostics.FixError(
            path=reported_path,
            identifier=rejection.identifier,
            rule_codes=tuple(rejection.rule_code.split(",")),
            message=f"{rejection.detail}; file was not modified",
        )
        for rejection in rejections
    )
