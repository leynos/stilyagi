"""Compose fix selection, admissibility, conflict checks, and byte splicing."""

import dataclasses as dc
import logging
import typing as typ

from stilyagi.engine import ir_view

from .admissibility import EditRejection, classify_edit
from .conflicts import coalesce_identical, first_overlap
from .selection import CandidatePartition, partition_candidates
from .splice import apply_edits

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics, model
    from stilyagi.config import LintConfig
    from stilyagi.fixes import FixLevel, TextEdit

_LOGGER = logging.getLogger(__name__)


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
    """The accepted edits and refused edits for one source byte sequence.

    ``fixed_bytes`` is ``None`` whenever applying ``edits`` would leave the
    source byte-identical: no edit survived planning -- in which case
    ``rejections`` carries the reason the file was left alone -- or the edits
    that did survive rewrite spans with the bytes already there. A caller that
    treats a non-``None`` replacement as "there is something to write" can
    therefore rely on that field alone. ``source_backed_spans`` and
    ``coalesced`` exist for the fix summary: they are counts no later stage can
    recover, because the source-backed span list is consumed by admissibility
    and the pre-coalesce edit list by conflict resolution.
    """

    edits: tuple[TextEdit, ...]
    fixed_codes: tuple[str, ...]
    rejections: tuple[EditRejection, ...]
    fixed_bytes: bytes | None
    selected: CandidatePartition
    source_backed_spans: int = 0
    coalesced: int = 0


def plan_fixes(request: FixPlanRequest) -> FixPlan:
    """Plan an all-or-nothing, source-backed mutation for one file.

    ``fixed_bytes`` is ``None`` whenever the planned edits would leave the
    source byte-identical -- no eligible diagnostic, every fix refused, or an
    edit that rewrites a span with the bytes it already holds. Callers use that
    one field to decide whether there is anything to write, so "no change" has
    to be reported as the absence of a replacement rather than as a replacement
    equal to the source.

    Returns
    -------
    FixPlan
        The accepted and refused edits, the replacement bytes when the plan
        changes the source, and the selection counters the fix summary reports.
    """
    selected = partition_candidates(
        request.diagnostics, request.level, request.lint_config
    )
    accepted, rejections = _validate_candidates(selected.eligible, request)
    if rejections:
        return _log_plan(
            FixPlan((), (), rejections, None, selected, _span_count(request)),
            selected,
        )
    edits = coalesce_identical(edit for _code, edit in accepted)
    overlap = first_overlap(edits)
    if overlap is not None:
        return _log_plan(
            FixPlan(
                (),
                (),
                (_overlap_rejection(overlap, accepted),),
                None,
                selected,
                _span_count(request),
            ),
            selected,
        )
    fixed_codes = tuple(dict.fromkeys(code for code, _edit in accepted))
    return _log_plan(
        FixPlan(
            edits,
            fixed_codes,
            (),
            _replacement(request.source_bytes, edits),
            selected,
            _span_count(request),
            coalesced=len(accepted) - len(edits),
        ),
        selected,
    )


def _log_plan(plan: FixPlan, selected: CandidatePartition) -> FixPlan:
    """Emit one INFO event describing how this file's plan was decided.

    One event per file per planning pass, so a run's fix behaviour can be
    reconstructed from the log without re-running it: the counters below are
    each consumed by a later stage and cannot be recovered from the returned
    plan alone.

    Returns
    -------
    FixPlan
        The plan, unchanged, so callers can wrap a return in this call without
        introducing a second name for it.

    Examples
    --------
    >>> _log_plan(
    ...     FixPlan((), (), (), None, CandidatePartition((), (), (), ())),
    ...     CandidatePartition((), (), (), ()),
    ... ).fixed_bytes is None
    True
    """
    _LOGGER.info(
        "fix plan decided",
        extra={
            "operation": "plan_fixes",
            "outcome": _plan_outcome(plan),
            "candidate_count": len(selected.eligible),
            "accepted_count": len(plan.edits),
            "coalesced_count": plan.coalesced,
            "rejection_count": len(plan.rejections),
            "rejection_category": plan.rejections[0].identifier
            if plan.rejections
            else None,
            "conflict_state": any(
                rejection.identifier == "fix-error/overlapping-edits"
                for rejection in plan.rejections
            ),
            "source_backed_spans": plan.source_backed_spans,
            "patch_byte_count": len(plan.fixed_bytes)
            if plan.fixed_bytes is not None
            else 0,
        },
    )
    return plan


def _plan_outcome(plan: FixPlan) -> str:
    """Name which of the planner's terminal paths produced this plan."""
    if plan.rejections:
        return "refused"
    if plan.fixed_bytes is None:
        return "unchanged"
    return "fixed"


def _replacement(source_bytes: bytes, edits: tuple[TextEdit, ...]) -> bytes | None:
    """Splice the accepted edits, or ``None`` when they would change nothing.

    ``fixed_bytes`` has to mean "bytes to write", not "bytes that came out of
    the splicing kernel". An empty edit list is an identity transformation, so
    a file with nothing fixable would otherwise carry a replacement equal to
    the source it was read from, and phase two would report a write of a file
    `write_source` correctly skips. An edit that replaces a span with the bytes
    already there is the same no-op reached through a non-empty list -- nothing
    forbids a rule from offering one -- so both are measured against the source
    rather than filtered by edit count.

    Returns
    -------
    bytes | None
        The changed bytes, or ``None`` when the result is byte-identical to the
        source and there is therefore nothing to write.

    Examples
    --------
    >>> from stilyagi.fixes import TextEdit
    >>> _replacement(b"one two", ())
    >>> _replacement(b"one two", (TextEdit(4, 7, "two"),))
    >>> _replacement(b"one two", (TextEdit(4, 7, "three"),))
    b'one three'
    """
    fixed_bytes = apply_edits(source_bytes, edits)
    return None if fixed_bytes == source_bytes else fixed_bytes


def _span_count(request: FixPlanRequest) -> int:
    """Return how many source-backed spans the file's IR claims.

    This is the denominator for the "considered / filtered" counters: a file
    with one fixable diagnostic out of forty source-backed spans is quiet,
    while the same diagnostic in a file with two spans is suspicious.

    Returns
    -------
    int
        How many merged source-backed spans the document carries.
    """
    return len(ir_view.source_backed_spans(request.document))


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
