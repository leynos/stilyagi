"""Unit tests for deterministic mixed-source discovery."""

import logging
import pathlib
import typing as typ

from stilyagi import config, discovery, model
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import pytest
    from syrupy.assertion import SnapshotAssertion


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write a tiny Markdown file with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")


def test_explicit_markdown_file_is_reported_verbatim(tmp_path: pathlib.Path) -> None:
    """Keep an explicitly named Markdown file and syntax in reported form."""
    target = tmp_path / "notes.md"
    _write_markdown(target, "Notes")

    files = discovery.discover_files([target], config.StilyagiConfig())

    assert_with_context(
        files
        == [
            discovery.DiscoveredFile(
                reported_path=target.as_posix(),
                resolved_path=target.resolve(),
                syntax=model.Syntax.MARKDOWN,
            ),
        ],
        "expected files == [discovery.DiscoveredFile(reported...",
    )


def test_explicit_unregistered_file_is_logged_and_skipped(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip a direct unregistered target without pretending it was linted."""
    target = tmp_path / "notes.txt"
    target.write_text("plain text\n", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="stilyagi.discovery"):
        files = discovery.discover_files([target], config.StilyagiConfig())

    assert files == [], "expected files == []"
    assert_with_context(
        any(
            "ignoring target without a registered extractor" in record.message
            for record in caplog.records
        ),
        "expected any(('ignoring target without a registered extractor' in reco...",
    )


def test_directory_recursion_skips_noise_and_symlinked_directories(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Recursion should stay deterministic and avoid directory symlink loops."""
    root = tmp_path / "docs"
    _write_markdown(root / "alpha.md", "Alpha")
    _write_markdown(root / "nested" / "beta.markdown", "Beta")
    _write_markdown(root / "build" / "ignored.md", "Ignored")
    _write_markdown(root / "nested" / ".venv" / "ignored.md", "Ignored")
    for ignored_name in (
        ".eggs",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".stilyagi_cache",
        ".tox",
        ".uv-cache",
        ".uv-tools",
        ".venv-release-smoke",
        "__pycache__",
        "site-packages",
    ):
        _write_markdown(root / ignored_name / "ignored.md", "Ignored")
    (root / "nested" / "loop").symlink_to(root, target_is_directory=True)

    files = discovery.discover_files([root], config.StilyagiConfig())

    normalised_files = [
        {
            "reported_path": pathlib
            .Path(file.reported_path)
            .relative_to(tmp_path)
            .as_posix(),
            "resolved_path": file.resolved_path.relative_to(tmp_path).as_posix(),
        }
        for file in files
    ]
    assert_with_context(
        normalised_files == snapshot(extension_class=JSONSnapshotExtension),
        "expected deterministic discovery paths without ignor...",
    )
    assert_with_context(
        all(isinstance(file, discovery.DiscoveredFile) for file in files),
        "expected all((isinstance(file, discovery.DiscoveredF...",
    )


def test_mixed_sources_carry_their_registered_syntaxes(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """Discover registered final suffixes with their matching extractor syntax."""
    root = tmp_path / "repository"
    _write_markdown(root / "docs" / "guide.md", "Guide")
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text('"""Module docs."""\n', encoding="utf-8")
    (root / "src" / "lib.rs").write_text("//! Crate docs.\n", encoding="utf-8")
    (root / "src" / "not-source.py.txt").write_text("ignored\n", encoding="utf-8")

    files = discovery.discover_files([root], config.StilyagiConfig())

    assert_with_context(
        [file.syntax for file in files]
        == [
            model.Syntax.MARKDOWN,
            model.Syntax.PYTHON_DOCSTRING,
            model.Syntax.RUST_DOC_COMMENT,
        ],
        "expected the registered final suffixes to select Markdown, Python, and Rust",
    )
    normalised_files = [
        {
            "reported_path": pathlib
            .Path(file.reported_path)
            .relative_to(tmp_path)
            .as_posix(),
            "resolved_path": file.resolved_path.relative_to(tmp_path).as_posix(),
            "syntax": file.syntax,
        }
        for file in files
    ]
    assert_with_context(
        normalised_files == snapshot(extension_class=JSONSnapshotExtension),
        "expected the mixed-source path and syntax contract snapshot",
    )
