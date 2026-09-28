"""Shared fixtures for the per-file check pipeline tests.

The pipeline tests are split across two modules: one drives `cli_pipeline`
directly, and one drives the same code through `cli.run_check` to pin the
injectable boundaries. Both need the same reporters, runners, and plan
builders, so those live here rather than being duplicated or imported across
test modules.
"""

import pathlib
import typing as typ

from stilyagi import cli_io, cli_pipeline, config, diagnostics, model
from stilyagi.cli_args import CheckOptions
from stilyagi.engine.fix_pipeline import PlannedFile
from stilyagi.engine.fix_planning.selection import CandidatePartition
from stilyagi.fixes import Applicability, Fix, TextEdit

if typ.TYPE_CHECKING:
    import pytest
    from stilyagi.rules import registry as rules_registry


def input_for(path: pathlib.Path) -> cli_io.CheckInput:
    """Return the check input that reads one real file."""
    return cli_io.CheckInput(reported_path=path.name, resolved_path=path)


def recording_reporter() -> tuple[
    list[tuple[pathlib.Path | None, Exception]], cli_pipeline.CheckReporter
]:
    """Return a reporter that records every call instead of printing."""
    failures: list[tuple[pathlib.Path | None, Exception]] = []

    def report(path: pathlib.Path | None, error: Exception) -> None:
        """Record one reported failure."""
        failures.append((path, error))

    return failures, report


def run_for(
    rule_runner: rules_registry.RuleRunner,
    report: cli_pipeline.CheckReporter,
) -> cli_pipeline.CheckRun:
    """Return the collaborators for one per-file check."""
    return cli_pipeline.CheckRun(
        options=CheckOptions(targets=("docs",)),
        resolver=config.ConfigResolver(),
        rule_runner=rule_runner,
        report=report,
    )


def silent_runner(
    _document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Return no diagnostics, so a test controls the only finding."""
    return []


def one_diagnostic_runner(
    _document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Return one diagnostic, so a readable file has something to collect."""
    return [diagnostics.Diagnostic(path="notes.md", code="PUN201", message="x")]


class VanishedFileError(FileNotFoundError):
    """A target that disappeared between discovery and its read."""

    def __init__(self) -> None:
        """Build the failure with its message inside the class."""
        super().__init__("target disappeared during read")


def patch_read_bytes_failure(
    monkeypatch: pytest.MonkeyPatch, target: pathlib.Path
) -> None:
    """Make reads of one target file fail after discovery has succeeded."""
    original_read_bytes = pathlib.Path.read_bytes

    def read_bytes(path: pathlib.Path, *args: object, **kwargs: object) -> bytes:
        """Raise for the target file only, leaving other reads intact."""
        if path == target:
            raise VanishedFileError
        return original_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_bytes", read_bytes)


def rewrite_paragraph(
    document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer one safe replacement against a source-backed paragraph span.

    The target document must contain "Paragraph"; the edit rewrites it to
    "Section". Callers use this where the *written* file matters, since the
    replacement is what a re-lint then reads back.
    """
    from tests.support.fix_fixtures import find_source_span

    span = find_source_span(document, "Paragraph")
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Use the preferred paragraph term.",
            severity=diagnostics.Severity.WARNING,
            fix=Fix(
                "Rewrite paragraph",
                Applicability.SAFE,
                (TextEdit.replace(span, "Section"),),
            ),
        )
    ]


def rewrite_heading_marker(
    _document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer a deliberately unsafe synthetic-span edit against a heading.

    The span targets the `##` marker itself, which the intermediate
    representation does not back. The planner therefore refuses the edit and the
    file is never written, which is what makes this useful for pinning the
    refusal and unwritten-file paths.
    """
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Do not change the heading marker automatically.",
            severity=diagnostics.Severity.WARNING,
            fix=Fix(
                "Remove heading marker",
                Applicability.SAFE,
                (TextEdit(0, 1, ""),),
            ),
        )
    ]


def checked_file(
    reported_path: str,
    messages: list[str],
    planned: PlannedFile | None = None,
) -> cli_pipeline.CheckedFile:
    """Build one checked file carrying diagnostics in the given order."""
    return cli_pipeline.CheckedFile(
        reported_path,
        cli_pipeline.FileCheck(
            [
                diagnostics.Diagnostic(
                    path=reported_path, code="PUN201", message=message
                )
                for message in messages
            ],
            failed=False,
            planned=planned,
        ),
    )


def planned_file(
    reported_path: str,
    fixed_text: str,
    *,
    source_text: str = "# Notes\n",
    identifiers: list[str] | None = None,
) -> PlannedFile:
    """Build one file's plan from replacement text and its refusal identifiers.

    All but two of a `PlannedFile`'s fields are carried through from planning
    untouched by anything the aggregation pass does, so they are given neutral
    zeros here; the ones that matter are the bytes a patch is rendered from and
    the refusals the run reports.

    Returns
    -------
    PlannedFile
        The plan carrying the supplied replacement bytes and refusals.
    """
    source_bytes = source_text.encode("utf-8")
    fixed_bytes = fixed_text.encode("utf-8")
    return PlannedFile(
        reported_path=reported_path,
        resolved_path=pathlib.Path(reported_path),
        source_bytes=source_bytes,
        source_text=source_text,
        fixed_bytes=fixed_bytes if fixed_bytes != source_bytes else None,
        fix_errors=tuple(
            diagnostics.FixError(
                path=reported_path,
                identifier=identifier,
                rule_codes=("PUN201",),
                message=f"{identifier}; file was not modified",
            )
            for identifier in identifiers or []
        ),
        selected=CandidatePartition((), (), (), ()),
        source_backed_spans=0,
        coalesced=0,
        planned_edits=0,
        from_stdin=False,
    )
