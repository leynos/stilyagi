"""Write a mutating run's planned fixes, re-lint, and report the outcome.

`cli_run` sweeps a collection of files and collects what each one said; this
module is the only place in the check command that changes a file on disk. The
seam is the one that matters most for review: everything above this module reads
and describes, everything here writes, and the split keeps the read path free of
any code that could mutate a user's source.

The two phases are ordered deliberately. Every plan is already in hand by the
time the first write happens, so an interruption leaves a partially written tree
with a complete record of what was planned -- but the run is *not* atomic across
files, and `apply_planned_fixes` says so in its own docstring. Claims of a
half-fixed tree being prevented belong there, not here.

The exit status stays at the command boundary. This module reports what
happened and hands back the evidence; `cli` decides what that means for the
process, the same way it does for a non-mutating run.
"""

import dataclasses as dc
import logging
import sys
import time
import typing as typ

from stilyagi import cli_fix
from stilyagi.cli_run import (
    aggregate_checked_files,
    reconcile_written_files,
    relint_written_files,
)
from stilyagi.fix_execution import apply_planned_fixes, deferred_plans

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli import CheckCollaborators
    from stilyagi.cli_args import CheckOptions
    from stilyagi.cli_pipeline import CheckedFile, CheckRun
    from stilyagi.cli_run import CheckedFiles
    from stilyagi.fix_execution import FixOutcome

__all__ = ["AppliedRun", "apply_fixes", "elapsed_ms"]

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class AppliedRun:
    """What a mutating run leaves behind for the command boundary to judge.

    Both fields are needed to state the exit policy, and keeping them paired is
    what stops a caller from reading the diagnostics without also seeing whether
    a write failed. `checked` is the re-lint for every file this run wrote and
    the planning pass's own result for every file it did not, so it describes
    the tree as it stands now rather than as it was read.
    """

    checked: CheckedFiles
    outcome: FixOutcome


def elapsed_ms(started: float) -> int:
    """Return whole milliseconds elapsed since one ``perf_counter`` reading.

    Returns
    -------
    int
        The elapsed milliseconds, rounded, never negative.
    """
    return round((time.perf_counter() - started) * 1000)


def apply_fixes(
    checked_files: cabc.Sequence[CheckedFile],
    run: CheckRun,
    options: CheckOptions,
    resolved_collaborators: CheckCollaborators,
) -> AppliedRun:
    """Write every planned fix, re-lint what changed, and report the outcome.

    Every file is planned before the first write, so an interruption leaves a
    partial tree with a complete record of what was planned. The run is not
    atomic across files: files written before the interruption keep their new
    bytes.

    Returns
    -------
    AppliedRun
        The re-linted diagnostics and the execution outcome. What those imply
        for the process is the caller's decision, not this module's.
    """
    plans = tuple(
        checked.result.planned
        for checked in checked_files
        if checked.result.planned is not None
    )
    cli_fix.warn_if_unsafe_withheld(plans, options)
    started = time.perf_counter()
    outcome = apply_planned_fixes(tuple(deferred_plans(plan) for plan in plans))
    _LOGGER.info(
        "fix execution finished",
        extra={
            "operation": "apply_planned_fixes",
            "elapsed_ms": elapsed_ms(started),
            "files_written": outcome.files_written,
            "files_aborted": outcome.files_aborted_on_conflict,
            "refused_edits": outcome.refused_edits,
        },
    )
    cli_fix.log_fix_summary(plans, outcome)
    emitted = cli_fix.emit_fixed_document(plans, resolved_collaborators.output)

    checked = aggregate_checked_files(checked_files)
    if not outcome.changed_anything:
        # A stream input's document already owns standard output, so its report
        # has to go to standard error instead. Routing on what was *emitted*
        # rather than on whether a stream input existed matters now that a
        # refused or unchanged plan emits nothing: keying on `from_stdin` alone
        # would send the report to standard error for a stream input that
        # produced no document, and a user capturing stdout would see an empty
        # file where the report should have been.
        cli_fix.print_unmodified_report(
            cli_fix.MutationReport(
                checked,
                options,
                resolved_collaborators.renderer,
                outcome,
                sys.stderr if emitted else resolved_collaborators.output,
            )
        )
        return AppliedRun(checked, outcome)

    # The re-lint is authoritative only for the files this run wrote; every
    # other file still holds the bytes the planning pass read, so its planning
    # diagnostics stand. Overlaying keeps both, and keeps file order.
    relinted = aggregate_checked_files(
        reconcile_written_files(
            checked_files,
            relint_written_files(outcome.applied, run),
            outcome.applied,
        )
    )
    cli_fix.print_mutation_report(
        cli_fix.MutationReport(
            relinted,
            options,
            resolved_collaborators.renderer,
            outcome,
            resolved_collaborators.output,
        )
    )
    return AppliedRun(relinted, outcome)
