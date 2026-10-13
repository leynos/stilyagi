"""Turn a completed check run into its report and its exit status.

Rendering a run's diagnostics and deciding what the run *means* are one
decision, not two. The exit status is a statement about the findings that were
rendered, so a module that produced the report without the status -- or the
status without the report -- would leave the caller to re-derive half of a
conclusion from the other half's inputs. Both live here.

`compute_exit_code` stays public because RFC 0003 §12 defines the mapping from
diagnostics to process status, and `cli.py` re-exports it so the documented
`cli.compute_exit_code` entry point keeps working. The mapping itself is
imported by the command rather than restated there: one implementation, one
place to change when the policy moves.

The delivery half is separated inside the module for the same reason. Building
the report, choosing the stream it belongs on, and emitting the diff artefact
are three different failures, and only the last one touches the byte boundary
that a patch has to cross intact (D-10).
"""

import logging
import sys
import time
import typing as typ

from stilyagi import check_metrics, diagnostics, engine
from stilyagi.cli_apply import elapsed_ms
from stilyagi.cli_io import write_artefact
from stilyagi.cli_run import CheckedFile, CheckedFiles, aggregate_checked_files

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.check_inputs import DiscoveryInputs
    from stilyagi.cli import CheckCollaborators
    from stilyagi.cli_args import CheckOptions

__all__ = [
    "compute_exit_code",
    "report_run",
]

_LOGGER = logging.getLogger(__name__)


def report_run(
    checked_files: cabc.Sequence[CheckedFile],
    discovery_inputs: DiscoveryInputs,
    options: CheckOptions,
    collaborators: CheckCollaborators,
) -> int:
    """Render one run's results to the right streams and return its exit code.

    The run summary is built from the same per-file results the diagnostics came
    from, so the counts and the findings cannot describe two different runs.

    Returns
    -------
    int
        Zero for a clean run, one for findings, or two for an operational error.
    """
    aggregate = aggregate_checked_files(checked_files)
    _LOGGER.debug(
        "rendering %d diagnostic(s) as %s",
        len(aggregate.diagnostics_list),
        options.output_format,
    )
    summary = engine.RunSummary.from_diagnostics(
        aggregate.diagnostics_list,
        checked_files=len(discovery_inputs.inputs),
        skipped_files=discovery_inputs.skipped_files,
        unreadable_files=_count_unreadable(checked_files),
    )
    check_metrics._record_diagnostic_counts(summary.errors, summary.warnings)
    rendered = collaborators.renderer.render(
        aggregate.diagnostics_list,
        options.output_format,
        fix_errors=aggregate.fix_errors,
        summary=summary,
    )
    _write_rendered(rendered, aggregate, options, collaborators)
    exit_code = compute_exit_code(
        aggregate.diagnostics_list,
        # A structured discovery failure makes the run an operational error even
        # when every input that was discovered checked cleanly.
        had_error=aggregate.error or bool(discovery_inputs.failures),
    )
    _LOGGER.debug("check complete: exit code %d", exit_code)
    return exit_code


def compute_exit_code(
    diagnostics_list: cabc.Sequence[diagnostics.Diagnostic],
    *,
    had_error: bool = False,
) -> int:
    """Return the documented exit code for one check run.

    Returns
    -------
    int
        Zero for success or warning-only diagnostics, one for error-severity
        diagnostics, or two for an operational error.

    Examples
    --------
    >>> compute_exit_code([])
    0
    >>> compute_exit_code([
    ...     diagnostics.Diagnostic(path="docs/example.md", code="STY001", message="x")
    ... ])
    1
    >>> compute_exit_code([
    ...     diagnostics.Diagnostic(
    ...         path="docs/example.md",
    ...         code="IR001",
    ...         message="x",
    ...         severity=diagnostics.Severity.WARNING,
    ...     )
    ... ])
    0
    >>> compute_exit_code([], had_error=True)
    2
    """
    if had_error:
        return 2
    if any(diagnostics.is_failing_severity(item.severity) for item in diagnostics_list):
        return 1
    return 0


def _write_rendered(
    rendered: str,
    aggregate: CheckedFiles,
    options: CheckOptions,
    collaborators: CheckCollaborators,
) -> None:
    """Send one run's rendered report and, under `--diff`, its patch.

    Under `--diff` the machine artefact owns standard output alone: diagnostics
    and the summary go to standard error so `stilyagi check --diff | git apply`
    stays usable.

    Writing the report is part of rendering it. A closed or broken output
    stream fails here rather than after the run is accounted for, so the phase
    is measured and a failure is recorded as the render phase's, which is what
    makes `operational_failures_total{render}` and the exit code agree about
    the same event.
    """
    diagnostics_output = sys.stderr if options.diff else collaborators.output
    try:
        with check_metrics._measure_phase("render"):
            print(rendered, end="", file=diagnostics_output)
            if options.diff:
                _emit_patch(aggregate, collaborators.output)
    except Exception:
        check_metrics.record_operational_failure("render")
        raise


def _count_unreadable(checked_files: cabc.Sequence[CheckedFile]) -> int:
    """Return how many checked inputs could not be read or decoded."""
    return sum(1 for checked in checked_files if checked.result.was_unreadable)


def _emit_patch(aggregate: CheckedFiles, output: typ.TextIO) -> None:
    """Assemble one run's diff patch, record its shape, and write it out.

    Delivery goes through the byte-preserving boundary rather than through a
    text stream, because the patch is a machine artefact a user pipes into
    `git apply` and a text stream would re-encode it (D-10).

    The record's two counters are kept together because the failed case has no
    other signal. A plan whose replacement restores the bytes already present,
    or one every edit was refused for, contributes an *empty* patch rather than
    no patch, so the run emits nothing while having planned something. The two
    counters differing is that state, and it is invisible in the output alone:
    an empty stdout looks the same whether nothing was planned or everything
    was refused.

    The patch size is measured here because this is the only place the quantity
    exists. The planner cannot report it -- `FixPlanRequest` carries no reported
    path, so it has no header to measure, and its own byte field counts the
    replacement document instead.
    """
    diff_started = time.perf_counter()
    patch = "".join(aggregate.patches).encode("utf-8")
    _LOGGER.info(
        "diff rendered",
        extra={
            "operation": "render_diff",
            "patch_byte_count": len(patch),
            "planned_files": len(aggregate.patches),
            "patched_files": len([entry for entry in aggregate.patches if entry]),
            "elapsed_ms": elapsed_ms(diff_started),
        },
    )
    write_artefact(output, patch)
