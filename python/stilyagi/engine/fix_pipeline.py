"""Compose fix planning into command-line previews and source mutations."""

import dataclasses as dc
import typing as typ

from stilyagi import diagnostics
from stilyagi.engine.fix_planning.diff import unified_diff
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import FixLevel

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi import model
    from stilyagi.config import LintConfig
    from stilyagi.engine.fix_planning.admissibility import EditRejection
    from stilyagi.engine.fix_planning.selection import CandidatePartition


@dc.dataclass(frozen=True, slots=True)
class FixRequest:
    """Everything one checked file must hand to the planner.

    ``source_bytes`` is the exact byte sequence the IR offsets were derived
    from, so a plan made from this request is applicable to the file on disk
    and to nothing else -- which is what makes the conditional write in phase
    two meaningful.
    """

    source_bytes: bytes
    source_text: str
    reported_path: str
    resolved_path: pathlib.Path
    document: model.Document
    diagnostics: tuple[diagnostics.Diagnostic, ...]
    lint_config: LintConfig
    level: FixLevel
    from_stdin: bool = False


@dc.dataclass(frozen=True, slots=True)
class PlannedFile:
    """One file's plan, or the reason no plan was made.

    ``fixed_bytes`` is ``None`` when the plan produced no applicable edit -- a
    conflicting file, a file whose every fix was refused, or a file with no
    fixable diagnostics at all. The caller distinguishes those cases from the
    refusal channel and from ``selected`` rather than from the byte field.

    ``source_text`` is kept beside the bytes the planner might replace, because
    rendering a preview needs the original text and re-decoding the bytes would
    assume the file is valid UTF-8 in a module that already has the decoded
    form.
    """

    reported_path: str
    resolved_path: pathlib.Path
    source_bytes: bytes
    source_text: str
    fixed_bytes: bytes | None
    fix_errors: tuple[diagnostics.FixError, ...]
    selected: CandidatePartition
    source_backed_spans: int
    coalesced: int
    planned_edits: int
    from_stdin: bool = False


def plan_file_fixes(request: FixRequest) -> PlannedFile:
    """Plan one file's mutation at the requested fix level, without writing.

    This is the read-only half of `--fix`. Separating it is what makes D-16's
    two-phase execution possible: every file is planned before any file is
    written, so an interruption cannot leave a half-fixed repository with no
    record of where it stopped.

    Returns
    -------
    PlannedFile
        The planned replacement bytes, or ``None`` for those, together with
        any refused edits on the separate error channel and the selection
        counters the fix summary reports.
    """
    plan = plan_fixes(_plan_request(request, request.level))
    return PlannedFile(
        reported_path=request.reported_path,
        resolved_path=request.resolved_path,
        source_bytes=request.source_bytes,
        source_text=request.source_text,
        fixed_bytes=plan.fixed_bytes,
        fix_errors=as_fix_errors(request.reported_path, plan.rejections),
        selected=plan.selected,
        source_backed_spans=plan.source_backed_spans,
        coalesced=plan.coalesced,
        planned_edits=len(plan.edits),
        from_stdin=request.from_stdin,
    )


def preview_safe_fixes(request: FixRequest) -> PlannedFile:
    """Plan safe fixes at the safe level, ignoring any unsafe opt-in.

    A preview of an edit nobody has agreed to apply would be a patch that
    cannot be used, so `--diff` plans at `FixLevel.SAFE` however
    `--unsafe-fixes` is set.

    Returns
    -------
    PlannedFile
        The same plan shape a mutation produces, at the safe ceiling.
    """
    return plan_file_fixes(dc.replace(request, level=FixLevel.SAFE))


def patch_for(plan: PlannedFile) -> str:
    """Render a planned mutation as a unified diff against the original text.

    Returns
    -------
    str
        The patch, or the empty string when the plan has no replacement bytes.
        A header with no hunks is not a patch, so an empty result is what
        `--diff` output omits rather than prints blank.
    """
    if plan.fixed_bytes is None:
        return ""
    return unified_diff(
        plan.source_text,
        plan.fixed_bytes.decode("utf-8"),
        plan.reported_path,
    )


def _plan_request(request: FixRequest, level: FixLevel) -> FixPlanRequest:
    """Build the planner's own request at one applicability level."""
    return FixPlanRequest(
        source_bytes=request.source_bytes,
        document=request.document,
        diagnostics=request.diagnostics,
        level=level,
        lint_config=request.lint_config,
    )


def as_fix_errors(
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
