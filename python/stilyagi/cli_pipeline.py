"""Per-file check workflow: read, extract, resolve, run rules, plan a fix.

This module owns the cohesive work one discovered file undergoes. It depends on
`config`, `engine`, `rules`, and `diagnostics`, and it is imported by `cli` and
`cli_run` rather than importing either, so the dependency direction runs inward
and the command module keeps only discovery, rendering, stream selection, and
exit status.

The run-level counterpart lives in `cli_run`: collecting one result per
discovered input, flattening those results for rendering, and reconciling a
mutating run's re-lint are operations over the whole set, and they are kept
apart from the per-file work rather than sharing a module with it.

Every failure that is *expected* at this boundary -- an unreadable file, a
bridge extraction refusal, an unusable configuration -- becomes a `FileCheck`
whose `failed` flag is set, and the reason is handed to the injectable
reporter. Nothing here prints or exits; the command boundary decides what an
expected failure means for the process.
"""

import dataclasses as dc
import logging
import pathlib
import typing as typ

from stilyagi import config, diagnostics, engine, model
from stilyagi.cli_config import resolve_target_config
from stilyagi.cli_io import CheckInput, SourcedInput, SourceReadError, read_source
from stilyagi.engine.checker import map_ir_errors
from stilyagi.engine.fix_pipeline import (
    FixRequest,
    PlannedFile,
    plan_file_fixes,
    preview_safe_fixes,
)
from stilyagi.fixes import FixLevel

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli_args import CheckOptions
    from stilyagi.rules import registry as rules_registry

__all__ = [
    "CheckReporter",
    "CheckRun",
    "CheckedFile",
    "FileCheck",
    "check_one_file",
]

_LOGGER = logging.getLogger(__name__)


#: How an expected failure is surfaced. The command boundary supplies the
#: implementation, so this module never chooses a stream or a log level.
#: ``path`` is ``None`` when the failure has no single file to blame, as when
#: discovery or configuration fails before any file is known.
type CheckReporter = cabc.Callable[[pathlib.Path | None, Exception], None]


@dc.dataclass(frozen=True, slots=True)
class FileCheck:
    """Everything one checked file contributed to the run.

    Naming the three values the pipeline used to return as an anonymous tuple
    keeps the aggregation pass readable and shows, at the point of
    construction, which field carries the failure flag.

    `planned` is the unrendered plan: the replacement bytes for `--fix`, and
    the patch rendered from them for `--diff`. Carrying it here is what spares
    the mutating command a second read, extraction, configuration resolution,
    and rule run for every file it rewrites, and it is also why `--fix` and
    `--diff` cannot disagree about what a plan is.
    """

    diagnostics_list: list[diagnostics.Diagnostic]
    failed: bool
    planned: PlannedFile | None = None

    @property
    def fix_errors(self) -> tuple[diagnostics.FixError, ...]:
        """The refused edits for this file, empty when nothing was planned."""
        return () if self.planned is None else self.planned.fix_errors


@dc.dataclass(frozen=True, slots=True)
class CheckedFile:
    """One file's result together with the path it was reported under."""

    reported_path: str
    result: FileCheck


@dc.dataclass(frozen=True, slots=True)
class PreparedFile:
    """One file after extraction and config resolution, before rule running.

    This is exactly the input a fix plan needs, which is why it exists as a
    named value rather than as another five-argument call: the check path uses
    it once and discards it, while the fix path hands it the applicability
    level as well, and a second read of the same file would risk planning
    against bytes the first read never saw.
    """

    sourced_input: SourcedInput
    document: model.Document
    diagnostics_list: list[diagnostics.Diagnostic]
    resolved_config: config.StilyagiConfig

    def request(self, level: FixLevel) -> FixRequest:
        """Build the planner request for this file at one applicability level."""
        return FixRequest(
            source_bytes=self.sourced_input.source_bytes,
            source_text=self.sourced_input.source_text,
            reported_path=self.sourced_input.reported_path,
            resolved_path=self.sourced_input.resolved_path,
            document=self.document,
            diagnostics=tuple(self.diagnostics_list),
            lint_config=self.resolved_config.lint,
            level=level,
            from_stdin=self.sourced_input.from_stdin,
        )


@dc.dataclass(frozen=True, slots=True)
class CheckRun:
    """The collaborators one check invocation holds fixed across every file.

    Bundling them keeps each per-file step's signature to the values that
    actually vary between files: the input, and whatever has been resolved
    about it so far.
    """

    options: CheckOptions
    resolver: config.ConfigResolver
    rule_runner: rules_registry.RuleRunner
    report: CheckReporter


def check_one_file(check_input: CheckInput, run: CheckRun) -> FileCheck:
    """Check one discovered Markdown file or stdin payload.

    Parameters
    ----------
    check_input:
        The resolved input to check, carrying either its bytes or its text.
    run:
        The collaborators fixed for this invocation, which decide whether a
        fix is planned and where expected failures are reported.

    Returns
    -------
    FileCheck
        The file's diagnostics, whether it failed, and its planned fix when one
        was requested and planned.
    """
    try:
        sourced_input = read_source(check_input)
    except SourceReadError as exc:
        # The typed error is handed over intact, so a reporter can tell a read
        # failure from an extraction one by type rather than by message text.
        run.report(exc.path, exc)
        return FileCheck([], failed=True)

    document = _extract_document(sourced_input, run)
    if document is None:
        return FileCheck([], failed=True)

    _LOGGER.debug("resolving config for %s", sourced_input.reported_path)
    try:
        resolved_config = resolve_target_config(
            sourced_input.resolved_path, run.options, run.resolver
        )
    except (config.InvalidCacheDirError, config.InvalidConfigError) as exc:
        run.report(sourced_input.resolved_path, exc)
        return FileCheck([], failed=True)

    prepared = PreparedFile(
        sourced_input,
        document,
        [
            *map_ir_errors(document, sourced_input.reported_path),
            *run.rule_runner(document, resolved_config),
        ],
        resolved_config,
    )
    if not _wants_a_plan(run):
        # Planning is skipped entirely unless a fix was asked for, so the
        # ordinary check path never pays for it.
        return FileCheck(prepared.diagnostics_list, failed=False)
    return FileCheck(
        prepared.diagnostics_list,
        failed=False,
        planned=_plan_fix(prepared, run),
    )


def _wants_a_plan(run: CheckRun) -> bool:
    """Return whether this invocation asked for a fix preview or a mutation."""
    return run.options.diff or run.options.fix


def _plan_fix(prepared: PreparedFile, run: CheckRun) -> PlannedFile:
    """Plan one file's edits at the level this run asked for.

    A preview and a mutation share every planning step and differ only in the
    applicability ceiling, so `--diff` always plans at `FixLevel.SAFE` -- a
    preview of an edit nobody has agreed to apply would be a patch that cannot
    be used.

    Returns
    -------
    PlannedFile
        The file's replacement bytes, or the refusal channel explaining why it
        has none.
    """
    request = prepared.request(_requested_level(run))
    if run.options.fix:
        return plan_file_fixes(request)
    return preview_safe_fixes(request)


def _requested_level(run: CheckRun) -> FixLevel:
    """Return the applicability ceiling this invocation's flags request (D-15)."""
    if run.options.fix and run.options.unsafe_fixes:
        return FixLevel.UNSAFE
    return FixLevel.SAFE


def _extract_document(
    sourced_input: SourcedInput,
    run: CheckRun,
) -> model.Document | None:
    """Extract one sourced input, reporting expected failures and re-raising others.

    A bridge refusal is an expected outcome for a malformed document and is
    reported. Anything else is a defect in the adapter, so it is logged with
    its traceback and allowed to propagate rather than being converted into an
    exit status that would hide it.

    Returns
    -------
    model.Document | None
        The extracted document, or ``None`` when the bridge refused it and the
        refusal has already been reported.
    """
    _LOGGER.debug("extracting %s", sourced_input.reported_path)
    try:
        return engine.extract_document(sourced_input.source_text, model.Syntax.MARKDOWN)
    except engine.BridgeExtractionError as exc:
        run.report(sourced_input.resolved_path, exc)
        return None
    except Exception:
        _LOGGER.exception(
            "unexpected extraction failure for %s", sourced_input.reported_path
        )
        raise
