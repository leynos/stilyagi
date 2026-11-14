"""In-process faults raised while `dump-ir` extracts one document.

The operand and discovery rejections live in `test_dump_ir_in_process.py`;
these cases start after discovery has handed the command an input and stop at
the per-document extraction boundary, where each failure must become a command
error rather than a partial JSON array.
"""

import json
import typing as typ

from stilyagi import cli_dump_ir, config, model
from stilyagi.check_inputs import CheckInput
from stilyagi.cli_args import DumpIrOptions

from tests.support.dump_ir_harness import run_dump_ir

if typ.TYPE_CHECKING:
    import pathlib

    import pytest


def test_dump_ir_reports_an_unreadable_source(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report a source whose bytes cannot be decoded as Markdown."""
    (tmp_path / "notes.md").write_bytes(b"# Invalid \xff\n")

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "undecodable source bytes are an operational error"
    assert not output, "an unreadable source must emit no JSON"
    assert "cannot read notes.md" in error, "the error must name the unreadable source"


def test_dump_ir_reports_a_missing_canonical_ir(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an extractor that returns no canonical IR for its input."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")
    monkeypatch.setattr(
        cli_dump_ir.CacheExtractionService,
        "extract",
        lambda _self, _request: typ.cast(
            "object", _ExtractionResult(canonical_json=None)
        ),
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "a missing canonical result is an operational error"
    assert not output, "a missing canonical result must emit no JSON"
    assert "returned no canonical IR" in error, (
        "the error must describe the missing extractor result"
    )


def test_dump_ir_reports_an_extraction_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an extractor that rejects its own input."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    def refuse_extraction(_self: object, _request: object) -> typ.NoReturn:
        """Fail the bridge extraction for the discovered input."""
        message = "bridge refused the document"
        raise ValueError(message)

    monkeypatch.setattr(
        cli_dump_ir.CacheExtractionService, "extract", refuse_extraction
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "an extraction failure is an operational error"
    assert not output, "an extraction failure must emit no JSON"
    assert "cannot extract notes.md" in error, (
        "the error must name the input and the extraction failure"
    )


def test_dump_ir_reports_a_config_error(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an invalid project configuration before any extraction."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")

    def refuse_config(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Reject every configuration resolution for the invocation."""
        message = "cannot read stilyagi.toml"
        raise config.ConfigError(message)

    monkeypatch.setattr(
        cli_dump_ir.config.ConfigResolver,
        "resolve_config_for_path",
        refuse_config,
    )

    exit_code, output, error = run_dump_ir(tmp_path, monkeypatch, "notes.md")

    assert exit_code == 2, "an invalid configuration is an operational error"
    assert not output, "a configuration failure must emit no JSON"
    assert "cannot read stilyagi.toml" in error, (
        "the error must carry the configuration failure detail"
    )
    assert "cannot extract" not in error, (
        "a broken config is not an extraction failure: ConfigError subclasses"
        " ValueError, so it must be reported before the extraction guard"
    )


class _ExtractionResult:
    """Stand in for one cache extraction result with a chosen IR payload."""

    def __init__(self, canonical_json: str | None) -> None:
        """Hold the canonical JSON the extractor would have produced."""
        self.canonical_json = canonical_json


def test_dump_ir_extracts_an_explicit_markdown_check_input(
    tmp_path: pathlib.Path,
) -> None:
    """Extract one Markdown input whose exact identity was chosen by the caller."""
    (tmp_path / "notes.md").write_text("# Heading\n", encoding="utf-8")
    context = cli_dump_ir._ExtractionContext(
        DumpIrOptions(targets=("notes.md",)),
        config.ConfigResolver(),
        cli_dump_ir.CacheExtractionService(
            cli_dump_ir.CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version=cli_dump_ir.PACKAGE_VERSION,
                no_cache=True,
            )
        ),
    )
    try:
        canonical = cli_dump_ir._extract_document(
            CheckInput(
                reported_path="notes.md",
                resolved_path=tmp_path / "notes.md",
                syntax=model.Syntax.MARKDOWN,
            ),
            context,
        )
    finally:
        context.cache.close()

    assert json.loads(canonical)["document"]["path"] == "notes.md", (
        "one explicit input must extract to its own canonical document"
    )
