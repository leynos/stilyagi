"""Run-level sweep over the files a check invocation discovered.

`check_execution` owns the cohesive work one file undergoes; this module owns
what happens to the *collection*. Collecting a result per input, flattening
those results into one render-ready bundle, and -- for a mutating run --
re-linting what was written and overlaying that onto the planning pass are all
operations whose unit is the run, not the file.

The split is along a seam the per-file module's own docstring draws: it claims
only per-file ownership, and every function here sweeps the whole set. Keeping
the two apart lets the per-file workflow be read without the aggregation loops,
and lets the aggregation be tested with no document at all.

The dependency runs inward and stays acyclic: this module imports
`check_execution`, and nothing in `check_execution` imports this back.
"""

import dataclasses as dc
import typing as typ

from stilyagi.check_execution import CheckRun, check_one_file
from stilyagi.check_inputs import CheckInput, FileCheckResult
from stilyagi.engine.fix_pipeline import patch_for

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics
    from stilyagi.fix_execution import AppliedFix

__all__ = [
    "CheckedFile",
    "CheckedFiles",
    "aggregate_checked_files",
    "collect_checked_files",
    "reconcile_written_files",
    "relint_written_files",
]


@dc.dataclass(frozen=True, slots=True)
class CheckedFile:
    """One file's result together with the path it was reported under."""

    reported_path: str
    result: FileCheckResult


@dc.dataclass(frozen=True, slots=True)
class CheckedFiles:
    """Diagnostics, patches, and failure state collected across checked files.

    File order, diagnostic order, fix-error order, and patch order all follow
    the order the files were checked in, so the rendered output is a pure
    function of the discovery order.
    """

    diagnostics_list: list[diagnostics.Diagnostic]
    fix_errors: list[diagnostics.FixError]
    patches: list[str]
    error: bool


def collect_checked_files(
    discovered_files: cabc.Iterable[CheckInput],
    run: CheckRun,
) -> list[CheckedFile]:
    """Check every discovered file, keeping the order they were discovered in.

    Returns
    -------
    list[CheckedFile]
        One result per input, in the order the inputs were supplied.
    """
    return [
        CheckedFile(
            reported_path=discovered_file.reported_path,
            result=check_one_file(discovered_file, run),
        )
        for discovered_file in discovered_files
    ]


def aggregate_checked_files(
    checked_files: cabc.Sequence[CheckedFile],
) -> CheckedFiles:
    """Flatten per-file results into one render-ready bundle.

    One pass over the results preserves file order for diagnostics and patches
    alike: each file contributes its diagnostics in order, then its refusals
    and its patch in the same relative order. Any file that failed makes the
    whole run an operational error.

    Returns
    -------
    CheckedFiles
        The flattened run, ready for rendering.

    Examples
    --------
    >>> from stilyagi.check_inputs import FileCheckResult
    >>> aggregate_checked_files([]).error
    False
    >>> failing = CheckedFile(
    ...     "a.md", FileCheckResult([], had_error=True, was_unreadable=True)
    ... )
    >>> aggregate_checked_files([failing]).error
    True
    """
    diagnostics_list: list[diagnostics.Diagnostic] = []
    fix_errors: list[diagnostics.FixError] = []
    patches: list[str] = []
    error = False
    for checked_file in checked_files:
        result = checked_file.result
        diagnostics_list.extend(result.diagnostics)
        error = result.had_error or error
        if result.planned is not None:
            fix_errors.extend(result.planned.fix_errors)
            patches.append(patch_for(result.planned))
    return CheckedFiles(
        diagnostics_list=diagnostics_list,
        fix_errors=fix_errors,
        patches=patches,
        error=error,
    )


def relint_written_files(
    applied: cabc.Sequence[AppliedFix],
    run: CheckRun,
    planned: cabc.Sequence[CheckedFile] = (),
) -> list[CheckedFile]:
    """Re-lint only the files a fix run actually mutated (D-13).

    This is deliberately not a fixpoint loop. RFC 0003 §12's "0 when all found
    violations were fixed" is not computable in one pass without *assuming*
    that applying a fix removes its diagnostic -- an assumption nothing tests
    and which a partial fix falsifies. If the re-lint surfaces further fixable
    diagnostics they are reported, not applied, and the caller says so.

    Re-reading the written file is also the honest check: it verifies what is
    on disk now, not what the plan expected to put there.

    Parameters
    ----------
    applied:
        The files that were written, each carrying the reported path to
        re-attribute diagnostics to and the resolved path to read.
    run:
        The collaborators for this invocation, reused so the re-lint resolves
        the same configuration and rule selection as the planning pass.
    planned:
        The planning pass's own results. The executor records what it wrote,
        not the syntax it was read under, so the re-lint recovers that from the
        plan keyed on the same resolved path rather than re-deriving it from
        the suffix. A path that resolution had already redirected cannot have
        its syntax guessed from its spelling.

    Returns
    -------
    list[CheckedFile]
        One re-check per written file, in planning order. The container is
        reused so a failed re-read is reported exactly as the planning pass
        would have reported it, rather than being flattened into diagnostics
        that cannot express it.
    """
    syntaxes = {
        checked.result.planned.resolved_path: checked.result.planned.syntax
        for checked in planned
        if checked.result.planned is not None
    }
    rerun = dc.replace(
        run,
        options=dc.replace(run.options, diff=False, fix=False),
        force_fresh=True,
    )
    return collect_checked_files(
        (
            CheckInput(
                reported_path=fixed.reported_path,
                resolved_path=fixed.resolved_path,
                syntax=syntaxes[fixed.resolved_path],
            )
            for fixed in applied
        ),
        rerun,
    )


def reconcile_written_files(
    checked_files: cabc.Sequence[CheckedFile],
    relinted: cabc.Sequence[CheckedFile],
    applied: cabc.Sequence[AppliedFix],
) -> list[CheckedFile]:
    """Overlay the re-lint onto the planning pass, one result per checked file.

    A mutating run must exit on the diagnostics that are still standing when it
    finishes, and those come from two different reads. A written file describes
    itself on disk now, so its re-lint is authoritative. A file that was *not*
    written still holds the bytes the planning pass read, so its planning
    diagnostics are the accurate description and the re-lint has nothing to say
    about it -- `relint_written_files` never read it.

    Taking the re-lint alone therefore drops the second group entirely, and a
    run that fixed one file while leaving a sibling's unfixable diagnostic
    standing would exit `0`. Overlaying restores the whole picture while
    keeping file order, diagnostic order, and the failure flag of each read
    exactly where the planning pass put them: this is the same sequence,
    `CheckedFile`-for-`CheckedFile`, not a second discovery.

    Parameters
    ----------
    checked_files:
        The planning pass's results, in discovery order.
    relinted:
        One re-check per written file, in the order of ``applied``.
    applied:
        The files this run actually wrote, in planning order.

    Returns
    -------
    list[CheckedFile]
        One result per input in ``checked_files``, each written file's result
        replaced by its re-lint.

    Examples
    --------
    >>> reconcile_written_files([], [], [])
    []
    """
    # Keyed by resolved path, the identity discovery deduplicates on, so the
    # overlay cannot land on the wrong file when two targets name one file.
    rewritten = {
        fixed.resolved_path: relinted_file
        for fixed, relinted_file in zip(applied, relinted, strict=True)
    }
    reconciled: list[CheckedFile] = []
    for checked_file in checked_files:
        planned = checked_file.result.planned
        replacement = None if planned is None else rewritten.get(planned.resolved_path)
        reconciled.append(checked_file if replacement is None else replacement)
    return reconciled
