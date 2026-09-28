"""Report what a mutating `--fix` run did, and what it left standing.

This module owns the *reporting* half of `--fix`: which stream a mutating run
speaks on, the note that re-running may apply further fixes, the warning that
names the flag which would apply the withheld unsafe fixes, and the per-file
planning counters. It depends on `cli_pipeline`, `engine`, and `fix_execution`,
and it is imported by `cli` rather than importing it, so the dependency
direction runs inward.

`cli` keeps the decision of *when* to write and what exit status the result
implies. Nothing here computes an exit status or touches a file: a reporter
that could write would be a second mutation path beside `fix_execution`, and
an exit code decided here would be a second answer to a question D-13 already
answers at the command boundary.
"""

import logging
import sys
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import engine
    from stilyagi.cli_args import CheckOptions
    from stilyagi.cli_pipeline import CheckedFiles
    from stilyagi.engine.fix_pipeline import PlannedFile
    from stilyagi.fix_execution import FixOutcome

__all__ = [
    "RERUN_HINT",
    "UNSAFE_HINT",
    "emit_fixed_document",
    "log_fix_summary",
    "print_mutation_report",
    "print_unmodified_report",
    "warn_if_unsafe_withheld",
]

_LOGGER = logging.getLogger(__name__)

#: Printed whenever a run wrote at least one file. Applying a fix can expose
#: further fixable text -- an insertion shifts the spans after it -- so a clean
#: exit is not a promise that the source is now quiescent.
RERUN_HINT = "fixes were applied; re-running may apply further fixes"

#: Printed when a mutating run leaves diagnostics standing, naming the one flag
#: that would have widened the selection.
UNSAFE_HINT = "unsafe fixes were withheld; pass --unsafe-fixes to apply them as well"


def emit_fixed_document(
    plans: cabc.Sequence[PlannedFile],
    output: typ.TextIO,
) -> None:
    """Print the fixed document for a stream input, which is never written.

    D-05: `--stdin-filename` is a reporting identity, so the bytes a user piped
    in are theirs to capture. Standard output is the only channel that can
    carry the fixed document without touching a file this command never read.

    Only the first stream input is printed: `_parse_targets` rejects a stdin
    target combined with any file target, so at most one can exist.
    """
    for plan in plans:
        if plan.from_stdin and plan.fixed_bytes is not None:
            print(plan.fixed_bytes.decode("utf-8"), end="", file=output)
            return


def print_unmodified_report(
    checked: CheckedFiles,
    options: CheckOptions,
    renderer: engine.RendererRegistry,
    destination: typ.TextIO,
) -> None:
    """Report a mutating run that wrote nothing, on the normal stream.

    Nothing was written, so the diagnostics collected during planning are still
    an accurate description of the source. Reporting them on the normal stream
    keeps `--fix` on a clean tree byte-identical to a plain check.

    The caller chooses the stream, because only the command boundary knows
    whether standard output is already carrying a fixed document. A stream
    input breaks the equivalence above: its report would otherwise be appended
    to the very text the user is piping out.
    """
    rendered = renderer.render(
        checked.diagnostics_list,
        options.output_format,
        fix_errors=checked.fix_errors,
    )
    print(rendered, end="", file=destination)


def print_mutation_report(
    relinted: CheckedFiles,
    options: CheckOptions,
    renderer: engine.RendererRegistry,
    outcome: FixOutcome,
) -> None:
    """Report what a mutating run left standing, on standard error.

    A run that wrote files describes the source on disk now, not the source it
    read, so its diagnostics are the re-lint's.

    Refusals come from three places, and `outcome.fix_errors` is the only
    channel holding all of them. Phase one's planning refusals ride along in
    the plan and so also reach `checked`; phase two's do not, because a target
    that moved under its plan and a write the filesystem rejected are both
    discovered after every plan was read. Reporting `checked.fix_errors` here
    would therefore describe a refused write as a silent no-op -- and for a
    write failure the run would exit `2` while printing nothing that explains
    why -- while reporting both would duplicate every phase-one refusal.

    Standard error is the stream because standard output may already be
    carrying a fixed document.
    """
    print(f"{RERUN_HINT}\n", file=sys.stderr)
    rendered = renderer.render(
        relinted.diagnostics_list,
        options.output_format,
        fix_errors=outcome.fix_errors,
    )
    print(rendered, end="", file=sys.stderr)


def warn_if_unsafe_withheld(
    plans: cabc.Sequence[PlannedFile],
    options: CheckOptions,
) -> None:
    """Name the flag that would apply the unsafe fixes a run withheld (D-15).

    The text renderer's summary counts unsafe fixes, but a count is not advice.
    This speaks only for a mutating run that has not already opted in, so it
    never repeats what the user just typed.

    The evidence is `CandidatePartition.withheld_unsafe`, which is the planner's
    own record of the diagnostics it left out for this one reason. Scanning the
    raw diagnostics instead -- asking whether any carried an unsafe fix --
    answers a different question: an unsafe fix can exist and still be withheld
    for a reason that has nothing to do with `--unsafe-fixes`, because
    `lint.unfixable` excludes a code before the level is ever consulted. A
    diagnostic filtered that way is not eligible at either level, so advising
    the user to widen the selection would be advice that changes nothing.
    """
    if options.unsafe_fixes:
        return
    if any(plan.selected.withheld_unsafe for plan in plans):
        print(f"stilyagi check: {UNSAFE_HINT}", file=sys.stderr)


def log_fix_summary(
    plans: cabc.Sequence[PlannedFile],
    outcome: FixOutcome,
) -> None:
    """Log the per-file planning counts and the run's outcome.

    Everything here is at INFO because every per-stage record in the command
    module is at DEBUG and there is no command-line path to DEBUG: a fix
    summary logged below INFO could not be reached with `--verbose`.

    `files_aborted_on_conflict` is the counter that matters most. Without it a
    run that refused every edit looks identical to one that found nothing to
    do, and the user has no way to tell which happened.
    """
    for plan in plans:
        _LOGGER.info(
            "%s: spans=%d considered=%d unfixable=%d manual=%d "
            "withheld_unsafe=%d coalesced=%d rejected=%d planned=%d bytes_delta=%d",
            plan.reported_path,
            plan.source_backed_spans,
            len(plan.selected.eligible)
            + len(plan.selected.unfixable)
            + len(plan.selected.manual)
            + len(plan.selected.withheld_unsafe),
            len(plan.selected.unfixable),
            len(plan.selected.manual),
            len(plan.selected.withheld_unsafe),
            plan.coalesced,
            len(plan.fix_errors),
            plan.planned_edits,
            _bytes_delta(plan),
        )
    _LOGGER.info(
        "%d files fixed, %d fixes applied, %d files skipped (conflict), "
        "%d fixes rejected",
        outcome.files_written,
        outcome.applied_edits,
        outcome.files_aborted_on_conflict,
        outcome.refused_edits,
    )


def _bytes_delta(plan: PlannedFile) -> int:
    """Return how many bytes a plan would add to or remove from its file.

    Returns
    -------
    int
        The signed difference, or zero when the plan carries no replacement.
    """
    if plan.fixed_bytes is None:
        return 0
    return len(plan.fixed_bytes) - len(plan.source_bytes)
