"""Per-file check workflow: read, extract, resolve, run rules, preview fixes.

This module owns the cohesive work one discovered file undergoes. It depends on
`config`, `engine`, `rules`, and `diagnostics`, and it is imported by `cli`
rather than importing it, so the dependency direction runs inward and the
command module keeps only discovery, rendering, stream selection, and exit
status.

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
from stilyagi.cli_io import CheckInput, SourceReadError, read_source
from stilyagi.engine.checker import map_ir_errors
from stilyagi.engine.fix_pipeline import DiffPreview, DiffRequest, preview_safe_fixes

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.cli_args import CheckOptions
    from stilyagi.cli_io import SourcedInput
    from stilyagi.rules import registry as rules_registry

__all__ = [
    "CheckReporter",
    "CheckRun",
    "CheckedFile",
    "CheckedFiles",
    "FileCheck",
    "aggregate_checked_files",
    "check_one_file",
    "collect_checked_files",
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
    """

    diagnostics_list: list[diagnostics.Diagnostic]
    failed: bool
    preview: DiffPreview | None = None


@dc.dataclass(frozen=True, slots=True)
class CheckedFile:
    """One file's result together with the path it was reported under."""

    reported_path: str
    result: FileCheck


@dc.dataclass(frozen=True, slots=True)
class CheckedFiles:
    """Diagnostics, previews, and failure state collected across checked files.

    File order, diagnostic order, fix-error order, and patch order all follow
    the order the files were checked in, so the rendered output is a pure
    function of the discovery order.
    """

    diagnostics_list: list[diagnostics.Diagnostic]
    fix_errors: list[diagnostics.FixError]
    patches: list[str]
    error: bool


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
        safe-fix preview is planned and where expected failures are reported.

    Returns
    -------
    FileCheck
        The file's diagnostics, whether it failed, and its diff preview when
        one was requested and planned.
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

    diagnostics_list = [
        *map_ir_errors(document, sourced_input.reported_path),
        *run.rule_runner(document, resolved_config),
    ]
    # Planning is skipped entirely unless --diff is set, so the ordinary check
    # path never pays for it.
    preview = (
        _plan_preview(sourced_input, document, diagnostics_list, resolved_config)
        if run.options.diff
        else None
    )
    return FileCheck(diagnostics_list, failed=False, preview=preview)


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


def _plan_preview(
    sourced_input: SourcedInput,
    document: model.Document,
    diagnostics_list: list[diagnostics.Diagnostic],
    resolved_config: config.StilyagiConfig,
) -> DiffPreview:
    """Plan a safe-fix preview for one file the run asked to preview.

    The preview is derived from the same bytes the document was extracted
    from, which is what keeps the patch applicable to the file on disk.

    Returns
    -------
    DiffPreview
        The planned patch, with any refused edits on the separate error
        channel.
    """
    return preview_safe_fixes(
        DiffRequest(
            sourced_input.source_bytes,
            sourced_input.source_text,
            sourced_input.reported_path,
            document,
            tuple(diagnostics_list),
            resolved_config.lint,
        )
    )


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
    alike: each file contributes its diagnostics in order, then its fix errors
    and its patch in the same relative order. Any file that failed makes the
    whole run an operational error.

    Returns
    -------
    CheckedFiles
        The flattened run, ready for rendering.

    Examples
    --------
    >>> aggregate_checked_files([]).error
    False
    >>> aggregate_checked_files([CheckedFile("a.md", FileCheck([], failed=True))]).error
    True
    """
    diagnostics_list: list[diagnostics.Diagnostic] = []
    fix_errors: list[diagnostics.FixError] = []
    patches: list[str] = []
    error = False
    for checked_file in checked_files:
        result = checked_file.result
        diagnostics_list.extend(result.diagnostics_list)
        error = result.failed or error
        if result.preview is not None:
            fix_errors.extend(result.preview.fix_errors)
            patches.append(result.preview.patch)
    return CheckedFiles(
        diagnostics_list=diagnostics_list,
        fix_errors=fix_errors,
        patches=patches,
        error=error,
    )
