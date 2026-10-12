"""Report what a mutating `--fix` run did, and what it left standing.

This module owns the *reporting* half of `--fix`: which stream a mutating run
speaks on, the note that re-running may apply further fixes, the warning that
names the flag which would apply the withheld unsafe fixes, and the per-file
planning counters. It depends on `cli_pipeline`, `cli_run`, `engine`, and
`fix_execution`, and it is imported by `cli` rather than importing it, so the
dependency direction runs inward.

`cli` keeps the decision of *when* to write and what exit status the result
implies. Nothing here computes an exit status or touches a file: a reporter
that could write would be a second mutation path beside `fix_execution`, and
an exit code decided here would be a second answer to a question D-13 already
answers at the command boundary.
"""

import dataclasses as dc
import logging
import sys
import typing as typ

from stilyagi.cli_io import write_artefact

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import engine
    from stilyagi.cli_args import CheckOptions
    from stilyagi.cli_run import CheckedFiles
    from stilyagi.engine.fix_pipeline import PlannedFile
    from stilyagi.fix_execution import FixOutcome

__all__ = [
    "RERUN_HINT",
    "UNSAFE_HINT",
    "MutationReport",
    "emit_fixed_document",
    "fix_summary_line",
    "log_fix_summary",
    "print_mutation_report",
    "print_unmodified_report",
    "summarises_on_the_report",
    "warn_if_unsafe_withheld",
]

_LOGGER = logging.getLogger(__name__)


@dc.dataclass(frozen=True, slots=True)
class MutationReport:
    """One mutating run's results, and how to render them.

    Every field is caller-owned: the run decides which diagnostics are current,
    how they should be serialized, what the executor recorded, and where the
    output belongs. They travel together because both reporters need exactly
    this set and nothing else, and because a report is a single object rather
    than four arguments a caller can transpose -- `renderer` and `outcome` are
    adjacent and both non-obvious, which is how a swapped pair would survive
    review.

    `destination` is the caller's because only the command boundary knows
    whether standard output is already carrying a stream input's document.
    """

    checked: CheckedFiles
    options: CheckOptions
    renderer: engine.RendererRegistry
    outcome: FixOutcome
    destination: typ.TextIO


def summarises_on_the_report(output_format: str) -> bool:
    """Say whether a run's summary sentence belongs on the report stream.

    It does for text. It must not for JSON, because that stream is a document
    a consumer parses *whole*: the users' guide pairs the summary line with
    `--output-format text` and promises `--output-format json` yields a stable
    JSON document. Appending the sentence leaves trailing data after the
    closing brace, so `json.loads` on the complete report raises instead of
    returning the run's diagnostics and refusals.

    Suppressing the copy costs nothing, because the same sentence is not lost:
    `log_fix_summary` logs it at INFO, which is the level `--verbose` selects.

    Returns
    -------
    bool
        True when the summary may share a stream with the rendered report.

    Examples
    --------
    >>> summarises_on_the_report("text")
    True
    >>> summarises_on_the_report("json")
    False
    """
    return output_format != "json"


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
) -> bool:
    """Emit the document for a stream input, which is never written.

    D-05: `--stdin-filename` is a reporting identity, so the bytes a user piped
    in are theirs to capture. Standard output is the only channel that can
    carry the document without touching a file this command never read.

    Three outcomes are distinguished, because the planner uses a null
    `fixed_bytes` for two of them and they are not the same event:

    * a replacement is emitted when planning changed the source;
    * *nothing* is emitted when the plan is refused -- no surviving edits and
      at least one recorded refusal. The refusal already travels on its own
      channel, and emitting the source here would present a run that fixed
      nothing as though it had returned a fixed document. The caller reports
      instead, which is why the return value distinguishes this case;
    * the original bytes are emitted when the plan is unchanged -- a clean
      input, or a set of fixes that would rewrite spans with the bytes already
      there. The planner reports both as a null replacement, and for a stream
      input that reads as "emit the source", not "emit nothing".

    Only the first stream input is emitted: `_parse_targets` rejects a stdin
    target combined with any file target, so at most one can exist.

    Returns
    -------
    bool
        Whether anything was written, so the caller can tell whether standard
        output is now occupied and the report belongs on standard error.

    Examples
    --------
    >>> import io
    >>> from stilyagi.engine.fix_pipeline import PlannedFile
    >>> from stilyagi.engine.fix_planning.selection import CandidatePartition
    >>> empty = CandidatePartition((), (), (), ())
    >>> plan = PlannedFile(
    ...     reported_path="notes.md",
    ...     resolved_path=__import__("pathlib").Path("notes.md"),
    ...     source_bytes=b"Clean text.",
    ...     source_text="Clean text.",
    ...     fixed_bytes=None,
    ...     fix_errors=(),
    ...     selected=empty,
    ...     source_backed_spans=1,
    ...     coalesced=0,
    ...     planned_edits=0,
    ...     from_stdin=True,
    ... )
    >>> sink = io.StringIO()
    >>> emit_fixed_document([plan], sink)
    True
    >>> sink.getvalue()
    'Clean text.'
    """
    for plan in plans:
        if not plan.from_stdin:
            continue
        document = _document_bytes(plan)
        if document is None:
            # A refused plan: the planner has already said, on the refusal
            # channel, that this input was left alone. Emitting the source here
            # would look like a successful fix, so the caller reports instead.
            return False
        write_artefact(output, document)
        return True
    return False


def _document_bytes(plan: PlannedFile) -> bytes | None:
    """Return the bytes a stream plan contributes, or ``None`` when refused."""
    if plan.fixed_bytes is not None:
        return plan.fixed_bytes
    return None if plan.fix_errors else plan.source_bytes


def fix_summary_line(outcome: FixOutcome) -> str:
    """Render the run-level summary the execplan requires on the report.

    The same sentence is logged at INFO, but a log line is invisible without
    `--verbose` and the console default is WARNING. This is the copy the
    command boundary prints unconditionally.

    Returns
    -------
    str
        One line naming files fixed, fixes applied, files skipped because their
        plan conflicted or was refused, and fixes rejected.

    Examples
    --------
    >>> from stilyagi.fix_execution import FixOutcome
    >>> fix_summary_line(FixOutcome((), (), 0, 0, 0))
    '0 files fixed, 0 fixes applied, 0 files skipped (conflict), 0 fixes rejected'
    """
    return (
        f"{outcome.files_written} files fixed, "
        f"{outcome.applied_edits} fixes applied, "
        f"{outcome.files_aborted_on_conflict} files skipped (conflict), "
        f"{outcome.refused_edits} fixes rejected"
    )


def print_unmodified_report(report: MutationReport) -> None:
    """Report a mutating run that wrote nothing, on the normal stream.

    Nothing was written, so the diagnostics collected during planning are still
    an accurate description of the source. Reporting them on the normal stream
    keeps `--fix` on a clean tree byte-identical to a plain check.

    The diagnostics stay the planning pass's, because no file changed. The
    refusals do not: they come from `outcome`, and that is the *only* channel
    holding all of them. A target that changed between the plan and the write,
    or one the filesystem would not accept, never reaches `checked`, so
    rendering that field instead would describe both as a silent no-op -- for a
    write failure the run would exit `2` with nothing printed that explains
    why. It would also lose the executor's collapse, which is what turns a
    per-edit refusal stream into one auditable line per file per identifier.

    The stream comes from `report.destination`, because only the command
    boundary knows whether standard output is already carrying a stream input's
    document.
    """
    rendered = report.renderer.render(
        report.checked.diagnostics_list,
        report.options.output_format,
        fix_errors=report.outcome.fix_errors,
    )
    print(rendered, end="", file=report.destination)
    if summarises_on_the_report(report.options.output_format):
        print(fix_summary_line(report.outcome), file=report.destination)


def print_mutation_report(report: MutationReport) -> None:
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

    The summary line goes on the report as well as the log for text output,
    because the log's copy is reached only through `--verbose`. JSON is the
    exception, for the reason `summarises_on_the_report` gives. The stream is
    fixed rather than taken from `report.destination`: a run that wrote files
    already owns that stream with the diagnostics this one supersedes.
    """
    print(f"{RERUN_HINT}\n", file=sys.stderr)
    rendered = report.renderer.render(
        report.checked.diagnostics_list,
        report.options.output_format,
        fix_errors=report.outcome.fix_errors,
    )
    print(rendered, end="", file=sys.stderr)
    if summarises_on_the_report(report.options.output_format):
        print(fix_summary_line(report.outcome), file=sys.stderr)


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

    Every per-edit refusal is logged before the outcome's collapsed copy is
    reported. `summarise_fix_errors` reduces a rule that emitted one bad edit
    per paragraph to a single line, which is the right report and the wrong
    record: the count says how many were dropped and never which spans were
    involved. The detail goes to the log, where volume is tolerable, and the
    answer to "why is my file not fixed" stays available.
    """
    for plan in plans:
        _log_plan_counters(plan)
        _log_refusal_detail(plan)
    _LOGGER.info(fix_summary_line(outcome))


def _log_plan_counters(plan: PlannedFile) -> None:
    """Log one file's selection counters and its replacement byte delta.

    The counters are named fields rather than a formatted sentence so a log
    consumer can read them as values. `bytes_delta` is the signed change the
    replacement would make to the file; `patch_byte_count` on the planner's own
    record is a different unit -- the rendered unified patch -- and both are
    kept because they answer different questions.
    """
    unfixable = len(plan.selected.unfixable)
    manual = len(plan.selected.manual)
    withheld = len(plan.selected.withheld_unsafe)
    _LOGGER.info(
        "fix plan counters",
        extra={
            "path": plan.reported_path,
            "source_backed_spans": plan.source_backed_spans,
            "candidate_count": len(plan.selected.eligible)
            + unfixable
            + manual
            + withheld,
            "unfixable_count": unfixable,
            "manual_count": manual,
            "withheld_unsafe_count": withheld,
            "coalesced_count": plan.coalesced,
            "rejected_count": len(plan.fix_errors),
            "planned_edits": plan.planned_edits,
            "bytes_delta": _bytes_delta(plan),
        },
    )


def _log_refusal_detail(plan: PlannedFile) -> None:
    """Log each refusal for one file before any collapse hides its detail."""
    for fix_error in plan.fix_errors:
        _LOGGER.info(
            "fix refused",
            extra={
                "path": fix_error.path,
                "operation": "plan_fixes",
                "outcome": fix_error.identifier,
                "rule_codes": ", ".join(fix_error.rule_codes),
                "detail": fix_error.message,
            },
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
