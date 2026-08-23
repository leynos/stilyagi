"""Compose fix selection, admissibility, conflict checks, and byte splicing."""

import dataclasses as dc
import typing as typ

from .admissibility import EditRejection, classify_edit
from .conflicts import coalesce_identical, first_overlap
from .selection import select_candidates
from .splice import apply_edits

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics, model
    from stilyagi.config import LintConfig
    from stilyagi.fixes import FixLevel, TextEdit


@dc.dataclass(frozen=True, slots=True)
class FixPlanRequest:
    """Inputs needed to plan one file's rule-authored source edits."""

    source_bytes: bytes
    document: model.Document
    diagnostics: tuple[diagnostics.Diagnostic, ...]
    level: FixLevel
    lint_config: LintConfig


@dc.dataclass(frozen=True, slots=True)
class FixPlan:
    """The accepted edits and refused edits for one source byte sequence."""

    edits: tuple[TextEdit, ...]
    fixed_codes: tuple[str, ...]
    rejections: tuple[EditRejection, ...]
    fixed_bytes: bytes | None


def plan_fixes(request: FixPlanRequest) -> FixPlan:
    """Plan an all-or-nothing, source-backed mutation for one file."""
    candidates = select_candidates(
        request.diagnostics, request.level, request.lint_config
    )
    accepted, rejections = _validate_candidates(candidates, request)
    if rejections:
        return FixPlan((), (), rejections, None)
    edits = coalesce_identical(edit for _code, edit in accepted)
    overlap = first_overlap(edits)
    if overlap is not None:
        return FixPlan((), (), (_overlap_rejection(overlap, accepted),), None)
    fixed_codes = tuple(dict.fromkeys(code for code, _edit in accepted))
    return FixPlan(edits, fixed_codes, (), apply_edits(request.source_bytes, edits))


def _validate_candidates(
    candidates: cabc.Iterable[diagnostics.Diagnostic],
    request: FixPlanRequest,
) -> tuple[tuple[tuple[str, TextEdit], ...], tuple[EditRejection, ...]]:
    """Keep only whole fixes whose edits all pass admissibility."""
    accepted: list[tuple[str, TextEdit]] = []
    rejections: list[EditRejection] = []
    for diagnostic in candidates:
        fix = diagnostic.fix
        if fix is None:
            continue
        fix_rejections = tuple(
            rejection
            for edit in fix.edits
            if (
                rejection := classify_edit(
                    edit, request.source_bytes, request.document, diagnostic.code
                )
            )
            is not None
        )
        if fix_rejections:
            rejections.extend(fix_rejections)
            continue
        accepted.extend((diagnostic.code, edit) for edit in fix.edits)
    return tuple(accepted), tuple(rejections)


def _overlap_rejection(
    overlap: tuple[TextEdit, TextEdit],
    accepted: tuple[tuple[str, TextEdit], ...],
) -> EditRejection:
    """Build one stable rejection that names the codes creating a conflict."""
    first, second = overlap
    codes = tuple(
        dict.fromkeys(code for code, edit in accepted if edit in {first, second})
    )
    detail = (
        f"edits overlap at bytes {first.byte_start}..{first.byte_end}; "
        f"rules {', '.join(codes)} cannot both apply"
    )
    return EditRejection("fix-error/overlapping-edits", ",".join(codes), detail)
