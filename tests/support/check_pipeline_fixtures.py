"""Shared fixtures for the per-file check pipeline tests.

The pipeline tests are split across two modules: one drives `cli_pipeline`
directly, and one drives the same code through `cli.run_check` to pin the
injectable boundaries. Both need the same reporters, runners, and preview
builders, so those live here rather than being duplicated or imported across
test modules.
"""

import pathlib
import typing as typ

from stilyagi import cli_io, cli_pipeline, config, diagnostics, model
from stilyagi.cli_args import CheckOptions

if typ.TYPE_CHECKING:
    import pytest
    from stilyagi.engine.fix_pipeline import DiffPreview
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


def checked_file(
    reported_path: str,
    messages: list[str],
    preview: DiffPreview | None = None,
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
            preview=preview,
        ),
    )


def preview(patch: str, identifiers: list[str]) -> DiffPreview:
    """Build one diff preview carrying the supplied patch and refusals."""
    from stilyagi.engine.fix_pipeline import DiffPreview

    return DiffPreview(
        patch,
        tuple(
            diagnostics.FixError(
                path="notes.md",
                identifier=identifier,
                rule_codes=("PUN201",),
                message=f"{identifier}; file was not modified",
            )
            for identifier in identifiers
        ),
    )
