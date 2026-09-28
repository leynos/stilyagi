"""Two-phase `--fix` execution: plan every file, then write the planned ones.

This module owns the mutating half of the fix workflow. It is deliberately
separate from `cli_pipeline`, which owns the read-only per-file check: the
pipeline never writes, and this module never re-derives a plan it was handed.

The shape follows D-16. Phase one wraps every plan so that no write can be
attempted before every file has been planned, and so that a plan which must not
be written -- one with no surviving edit, or one read from a stream -- is
carried as an explicit refusal rather than dropped. Phase two then writes what
remains, each write conditional on the target still holding the bytes its plan
was derived from, and reports every refusal it produced.

D-13 lives at the command boundary, which re-lints the files that were actually
mutated and derives the exit status from that re-lint rather than from assuming
that applying a fix removed its diagnostic.
"""

import dataclasses as dc
import logging
import typing as typ

from stilyagi import diagnostics
from stilyagi.engine.fix_planning.write import (
    SourceChangedOnDiskError,
    write_source,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

    from stilyagi.engine.fix_pipeline import PlannedFile

__all__ = [
    "AppliedFix",
    "FixOutcome",
    "apply_planned_fixes",
    "deferred_plans",
    "summarise_fix_errors",
]

_LOGGER = logging.getLogger(__name__)

#: Suffix every planner refusal already carries, and which the collapsed report
#: re-appends so each line states the file is untouched.
_UNMODIFIED_SUFFIX = "; file was not modified"

#: Added to a refusal that phase one raised, naming why no write was attempted.
_DEFERRED_SUFFIX = "; no edits were applied to this file"


@dc.dataclass(frozen=True, slots=True)
class AppliedFix:
    """One file whose planned bytes were written to disk."""

    reported_path: str
    resolved_path: pathlib.Path
    bytes_before: int
    bytes_after: int
    edits: int

    @property
    def bytes_delta(self) -> int:
        """How many bytes the applied fixes added or removed."""
        return self.bytes_after - self.bytes_before


@dc.dataclass(frozen=True, slots=True)
class FixOutcome:
    """Everything one `--fix` run did, and everything it declined to do.

    Parameters
    ----------
    applied:
        The files written, in the order they were planned.
    fix_errors:
        Every refusal from both phases, collapsed to one entry per file per
        identifier.
    files_written:
        How many files were rewritten.
    files_aborted_on_conflict:
        How many files were left completely untouched because their edits
        conflicted, or because a write was refused. This is the counter that
        matters most: without it, `--fix` appears to do nothing and the user
        cannot tell why.
    """

    applied: tuple[AppliedFix, ...]
    fix_errors: tuple[diagnostics.FixError, ...]
    files_written: int
    files_aborted_on_conflict: int
    refused_edits: int

    @property
    def changed_anything(self) -> bool:
        """Whether any file was written."""
        return self.files_written > 0

    @property
    def applied_edits(self) -> int:
        """How many planned edits reached the filesystem."""
        return sum(applied.edits for applied in self.applied)


def deferred_plans(planned: PlannedFile) -> PlannedFile:
    """Prepare one phase-one plan for a possible phase-two write.

    Two plans become refusals here rather than being silently dropped, because
    a caller must be able to say why a file it planned is not in the write list:

    * a plan with no replacement bytes, because nothing survived planning;
    * a plan whose input came from a stream, because D-05 says
      ``--stdin-filename`` is a reporting identity and the bytes never came from
      that file.

    Returns
    -------
    PlannedFile
        The plan, or an equivalent with no replacement bytes and a refusal
        naming the reason.
    """
    if planned.fixed_bytes is None:
        return planned
    if planned.from_stdin:
        # D-05: writing these bytes back would replace a file the command never
        # read. The fixed document still reaches the user, on standard output.
        return dc.replace(
            planned,
            fixed_bytes=None,
            fix_errors=(
                diagnostics.FixError(
                    path=planned.reported_path,
                    identifier="fix-error/standard-input",
                    rule_codes=(),
                    message=(
                        "input came from standard input"
                        f"{_UNMODIFIED_SUFFIX}{_DEFERRED_SUFFIX}"
                    ),
                ),
            ),
        )
    return planned


def apply_planned_fixes(
    plans: cabc.Sequence[PlannedFile],
) -> FixOutcome:
    """Write every plan that produced replacement bytes, in planning order.

    Phase two of D-16. Each write is conditional on the target still holding
    the bytes the plan was derived from, so a file edited during phase one is
    refused rather than silently overwritten. The run is not atomic across
    files -- D-16 chooses file atomicity plus a complete plan over cross-file
    atomicity -- but every refusal is reported, so a partially applied run can
    say exactly what it left behind.

    Returns
    -------
    FixOutcome
        The files written and the refusals, with abandoned files counted
        separately.
    """
    applied: list[AppliedFix] = []
    fix_errors: list[diagnostics.FixError] = []
    aborted = 0
    for plan in plans:
        fix_errors.extend(plan.fix_errors)
        if plan.fixed_bytes is None:
            if plan.fix_errors:
                # A file with nothing fixable at all is quiet; a file whose
                # plan was refused is not, and is counted.
                aborted += 1
            continue
        written = _write_one(plan)
        if written is None:
            fix_errors.append(_changed_on_disk_error(plan))
            aborted += 1
            continue
        applied.append(written)
    return FixOutcome(
        applied=tuple(applied),
        fix_errors=summarise_fix_errors(fix_errors),
        files_written=len(applied),
        files_aborted_on_conflict=aborted,
        refused_edits=len(fix_errors),
    )


def _write_one(plan: PlannedFile) -> AppliedFix | None:
    """Write one planned file, returning ``None`` if the target changed.

    Returns
    -------
    AppliedFix | None
        The applied fix, or ``None`` when the target no longer holds the bytes
        the plan was derived from and the write was refused.
    """
    fixed_bytes = typ.cast("bytes", plan.fixed_bytes)
    try:
        write_source(
            plan.resolved_path,
            fixed_bytes,
            original_bytes=plan.source_bytes,
        )
    except SourceChangedOnDiskError as exc:
        _LOGGER.warning("%s", exc)
        return None
    _LOGGER.info(
        "wrote %s (%d -> %d bytes)",
        plan.reported_path,
        len(plan.source_bytes),
        len(fixed_bytes),
    )
    return AppliedFix(
        reported_path=plan.reported_path,
        resolved_path=plan.resolved_path,
        bytes_before=len(plan.source_bytes),
        bytes_after=len(fixed_bytes),
        edits=plan.planned_edits,
    )


def _changed_on_disk_error(plan: PlannedFile) -> diagnostics.FixError:
    """Build the refusal for a plan whose target was edited before phase two."""
    identifier = "fix-error/changed-on-disk"
    return diagnostics.FixError(
        path=plan.reported_path,
        identifier=identifier,
        rule_codes=(),
        message=(
            f"the file changed on disk after it was planned, so the planned "
            f"edits were not written{_UNMODIFIED_SUFFIX}{_DEFERRED_SUFFIX}"
        ),
    )


def summarise_fix_errors(
    fix_errors: cabc.Iterable[diagnostics.FixError],
) -> tuple[diagnostics.FixError, ...]:
    """Collapse refusals to one report per file per identifier with a count.

    A buggy rule emitting one bad edit per paragraph would otherwise produce
    hundreds of warnings on a large file. One line saying "3 refused edits,
    file left unmodified" is auditable where five hundred lines is not (D-07).

    Returns
    -------
    tuple[diagnostics.FixError, ...]
        One entry per ``(path, identifier)`` pair, in first-seen order, with
        the codes unioned and the count recorded in the message.
    """
    counts: dict[tuple[str, str], int] = {}
    codes: dict[tuple[str, str], list[str]] = {}
    details: dict[tuple[str, str], str] = {}
    for fix_error in fix_errors:
        key = (fix_error.path, fix_error.identifier)
        counts[key] = counts.get(key, 0) + 1
        details.setdefault(key, _detail_for(fix_error))
        known = codes.setdefault(key, [])
        for code in fix_error.rule_codes:
            if code not in known:
                known.append(code)
    collapsed: list[diagnostics.FixError] = []
    for (path, identifier), count in counts.items():
        collapsed.append(
            diagnostics.FixError(
                path=path,
                identifier=identifier,
                rule_codes=tuple(codes[path, identifier]),
                message=(
                    f"{details[path, identifier]} ({count} refused edit(s))"
                    f"{_UNMODIFIED_SUFFIX}"
                ),
            )
        )
    return tuple(collapsed)


def _detail_for(fix_error: diagnostics.FixError) -> str:
    """Return one refusal's own detail, with its outcome clauses stripped.

    The collapsed line is the single place that states the outcome for the
    file, so each detail is reduced to the reason itself; otherwise the
    remainder would appear once per contributing edit.

    Returns
    -------
    str
        The refusal's reason, without its file-outcome clauses.
    """
    detail = fix_error.message.removesuffix(_DEFERRED_SUFFIX)
    return detail.removesuffix(_UNMODIFIED_SUFFIX)
