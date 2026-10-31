"""Per-file execution for the `stilyagi check` command.

This is the one path a discovered input travels: read it byte-faithfully,
extract it through the syntax it was discovered under, resolve the
configuration in force for its path, run the rules, and -- when the run asked
for one -- plan its fix. Every stage is wrapped in an operational metric span,
so a run's cost can be attributed to the phase that spent it.

Keeping that in one function is what makes the run's accounting honest: a
second implementation would repeat the metric recording, span boundaries, and
failure classification, and the two copies would disagree the first time one
changed. The run-level sweep imports this module rather than reimplementing it.

The read lives here rather than entirely in `cli_io`. `cli_io` owns the byte
*boundary*: how a stream is read without newline translation, and how an
artefact is written back without re-encoding. This module owns what happens to
a *path*: the syntax dispatch that decides how a document is decoded, the
failure that counts as an unreadable file, and the span that measures it.
Those three are one decision, and a caller able to reach the raw read without
them could produce a check whose metrics denied what it did.

The read returns the input's bytes alongside its text because a fix plan
splices byte offsets. Planning against a second read of the same path would
mean splicing offsets derived from one sequence into another, so the decoded
text every later stage sees and the bytes every edit is applied to come from
the same call.
"""

import dataclasses as dc
import logging
import os
import pathlib
import typing as typ

from stilyagi import check_metrics, config, diagnostics, engine, model
from stilyagi.check_inputs import (
    CheckInput,
    FileCheckResult,
)
from stilyagi.cli_config import resolve_target_config
from stilyagi.cli_io import SourcedInput, SourceReadError, read_source
from stilyagi.engine.checker import map_ir_errors
from stilyagi.engine.fix_pipeline import (
    FixRequest,
    PlannedFile,
    plan_file_fixes,
    preview_safe_fixes,
)
from stilyagi.fixes import FixLevel
from stilyagi.rules.registry import RuleRunRequest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli_args import CheckOptions
    from stilyagi.rules import registry as rules_registry

__all__ = [
    "CheckReporter",
    "CheckRun",
    "check_one_file",
]

_LOGGER = logging.getLogger(__name__)


#: How an expected failure is surfaced. The command boundary supplies the
#: implementation, so this module never chooses a stream or a log level.
#: ``path`` is ``None`` when the failure has no single file to blame, as when
#: discovery or configuration fails before any file is known.
type CheckReporter = cabc.Callable[[pathlib.Path | None, Exception], None]


@dc.dataclass(frozen=True, slots=True)
class CheckRun:
    """The collaborators one check invocation holds fixed across every file.

    Bundling them keeps each per-file step's signature to the values that
    actually vary between files: the input, and whatever has been resolved
    about it so far.

    The reporter is a field rather than a module-level call so a caller can
    substitute where expected failures go without substituting how they are
    detected -- the two are separate decisions, and a test that only wants to
    capture the failures should not have to reimplement the read.
    """

    options: CheckOptions
    resolver: config.ConfigResolver
    rule_runner: rules_registry.RuleRunner
    report: CheckReporter


def _rule_request(
    *,
    sourced_input: SourcedInput,
    document: model.Document,
    resolved_config: config.StilyagiConfig,
    run: CheckRun,
) -> RuleRunRequest:
    """Build the per-document rule request from the values already in hand.

    The check pipeline already holds the original bytes, the reported path and
    the resolved configuration here, so rules can be handed byte-exact source
    without a second read and without reaching for the filesystem themselves.

    Parameters
    ----------
    sourced_input:
        The read result carrying both the original bytes and decoded text.
    document:
        The extracted document with its canonical IR envelope.
    resolved_config:
        The effective configuration for this target.
    run:
        The collaborators and options fixed for this invocation.

    Returns
    -------
    RuleRunRequest
        The frozen request a rule runner receives.
    """
    config_file = run.resolver.config_file_for_path(
        sourced_input.resolved_path,
        explicit_config=run.options.explicit_config or None,
        isolated=run.options.isolated,
    )
    return RuleRunRequest(
        config=resolved_config,
        config_path=str(config_file) if config_file is not None else None,
        source_bytes=sourced_input.source_bytes,
        reported_path=sourced_input.reported_path,
        document=document,
        config_relative_path=_config_relative_path(
            sourced_input.resolved_path, config_file
        ),
    )


def _config_relative_path(
    target: pathlib.Path,
    config_file: pathlib.Path | None,
) -> str:
    """Return the POSIX target path per-file ignore globs are matched against.

    Globs are config-relative, anchored at the governing config file's parent,
    or at the invocation working directory when no config file governs the
    target. ``os.path.relpath`` is used rather than ``Path.relative_to`` so a
    target outside the config tree still yields a stable relative spelling
    instead of failing the check.

    Parameters
    ----------
    target:
        The resolved path of the file being checked.
    config_file:
        The governing config file, or ``None`` when configuration is inline
        only or absent.

    Returns
    -------
    str
        The target path as POSIX text, relative to the glob anchor.
    """
    anchor = (
        config_file.expanduser().resolve().parent
        if config_file is not None
        else pathlib.Path.cwd()
    )
    relative = os.path.relpath(target.expanduser().resolve(), anchor)
    return pathlib.PurePath(relative).as_posix()


def _wants_a_plan(run: CheckRun) -> bool:
    """Return whether this invocation asked for a fix preview or a mutation."""
    return bool(run.options.diff or run.options.fix)


def _requested_level(run: CheckRun) -> FixLevel:
    """Return the applicability ceiling this invocation's flags request (D-15).

    A preview plans at `FixLevel.SAFE` unless the run also asked for a
    mutation: `--unsafe-fixes` alone is documented as inert, and a preview of
    an edit nobody agreed to apply would be a patch that cannot be used.

    Returns
    -------
    FixLevel
        ``UNSAFE`` only when the run both mutates and opted in to unsafe edits.
    """
    if run.options.fix and run.options.unsafe_fixes:
        return FixLevel.UNSAFE
    return FixLevel.SAFE


@dc.dataclass(frozen=True, slots=True)
class _PlannedFileRequest:
    """Everything one file's fix plan needs to be described.

    Grouped because these values read as one clump at every call site; spread
    across an argument list, each argument's role had to be recovered from
    position.
    """

    sourced_input: SourcedInput
    document: model.Document
    diagnostics_list: list[diagnostics.Diagnostic]
    resolved_config: config.StilyagiConfig
    run: CheckRun


def _plan_fix(request: _PlannedFileRequest) -> PlannedFile:
    """Plan one file's edits at the level this run asked for.

    Returns
    -------
    PlannedFile
        The file's replacement bytes, or the refusal channel explaining why it
        has none.
    """
    sourced_input = request.sourced_input
    run = request.run
    fix_request = FixRequest(
        source_bytes=sourced_input.source_bytes,
        source_text=sourced_input.source_text,
        reported_path=sourced_input.reported_path,
        resolved_path=sourced_input.resolved_path,
        syntax=sourced_input.syntax,
        document=request.document,
        diagnostics=tuple(request.diagnostics_list),
        lint_config=request.resolved_config.lint,
        level=_requested_level(run),
        from_stdin=sourced_input.from_stdin,
    )
    if run.options.fix:
        return plan_file_fixes(fix_request)
    return preview_safe_fixes(fix_request)


def _read_source(check_input: CheckInput, run: CheckRun) -> SourcedInput | None:
    """Return one input with its bytes and text, or ``None`` after reporting.

    Every read and decoding failure is caught here, so the check loop has one
    shape of failure to handle rather than a family of exception types. The
    function is deliberately the only place a read failure is converted into a
    reported outcome, which is what keeps the operational metrics and the exit
    status telling the same story about the same file.

    The failure is reported against the input's *reported* path, not the
    resolved one the read attempted. That is the command-line-relative identity
    the run summary and every diagnostic already use, so a user reading the
    warning can match it to the file they asked about rather than to an
    absolute path they never typed. The typed `SourceReadError` is handed on
    intact, so a consumer that needs the path the read actually reached still
    has it.

    Parameters
    ----------
    check_input:
        The resolved input to read.
    run:
        The collaborators for this invocation, whose reporter receives any
        failure.

    Returns
    -------
    SourcedInput | None
        The read input, or ``None`` when it could not be read and the failure
        has already been reported.
    """
    try:
        return read_source(check_input)
    except SourceReadError as exc:
        run.report(pathlib.Path(check_input.reported_path), exc)
        return None


def _report_phase_failure(
    sourced_input: SourcedInput,
    run: CheckRun,
    error: Exception,
    phase: str,
) -> FileCheckResult:
    """Record one failed check phase and return that file's failed outcome."""
    check_metrics.record_operational_failure(phase)
    run.report(pathlib.Path(sourced_input.reported_path), error)
    return FileCheckResult(diagnostics=[], had_error=True, was_unreadable=False)


def check_one_file(check_input: CheckInput, run: CheckRun) -> FileCheckResult:
    """Check one discovered file or standard-input payload.

    Parameters
    ----------
    check_input:
        The resolved input to check, carrying either its bytes or its text.
    run:
        The collaborators fixed for this invocation, which decide whether a
        fix is planned and where expected failures are reported.

    Returns
    -------
    FileCheckResult
        The file's diagnostics, its operational outcome, and its planned fix
        when the run asked for one.
    """
    check_metrics._record_file(check_input.syntax)
    with check_metrics._measure_phase("read"):
        sourced_input = _read_source(check_input, run)
    if sourced_input is None:
        check_metrics.record_unreadable_file()
        check_metrics.record_operational_failure("read")
        return FileCheckResult(diagnostics=[], had_error=True, was_unreadable=True)

    _LOGGER.debug("extracting %s", sourced_input.reported_path)
    try:
        with check_metrics._measure_phase("extract"):
            document = engine.extract_document(
                sourced_input.source_text, check_input.syntax
            )
    except engine.BridgeExtractionError as exc:
        return _report_phase_failure(sourced_input, run, exc, "extract")
    except Exception:
        check_metrics.record_operational_failure("extract")
        _LOGGER.exception(
            "unexpected extraction failure for %s",
            sourced_input.reported_path,
        )
        raise

    _LOGGER.debug("resolving config for %s", sourced_input.reported_path)
    try:
        with check_metrics._measure_phase("config"):
            resolved_config = resolve_target_config(
                sourced_input.resolved_path, run.options, run.resolver
            )
    except (
        config.InvalidCacheDirError,
        config.InvalidConfigError,
    ) as exc:
        return _report_phase_failure(sourced_input, run, exc, "config")

    diagnostics_list = _collect_diagnostics(
        sourced_input, document, resolved_config, run
    )
    return FileCheckResult(
        diagnostics=diagnostics_list,
        had_error=False,
        was_unreadable=False,
        planned=_plan_if_wanted(
            _PlannedFileRequest(
                sourced_input=sourced_input,
                document=document,
                diagnostics_list=diagnostics_list,
                resolved_config=resolved_config,
                run=run,
            )
        ),
    )


def _collect_diagnostics(
    sourced_input: SourcedInput,
    document: model.Document,
    resolved_config: config.StilyagiConfig,
    run: CheckRun,
) -> list[diagnostics.Diagnostic]:
    """Return the file's IR-error and rule diagnostics for the rules phase."""
    try:
        with check_metrics._measure_phase("rules"):
            return [
                *map_ir_errors(document, sourced_input.reported_path),
                *run.rule_runner(
                    _rule_request(
                        sourced_input=sourced_input,
                        document=document,
                        resolved_config=resolved_config,
                        run=run,
                    )
                ),
            ]
    except Exception:
        check_metrics.record_operational_failure("rules")
        raise


def _plan_if_wanted(request: _PlannedFileRequest) -> PlannedFile | None:
    """Plan this file's fix, unless the run asked for no plan.

    Planning is skipped unless a fix was asked for, so an ordinary check never
    pays for it and never reports a plan it did not make.

    Returns
    -------
    PlannedFile | None
        The file's plan, or ``None`` when this run asked for no plan.
    """
    if not _wants_a_plan(request.run):
        return None
    return _plan_fix(request)
