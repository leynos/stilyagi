"""Unit tests for deterministic Markdown discovery."""

import logging
import pathlib
import typing as typ

from stilyagi import config, discovery
from syrupy.extensions.json import JSONSnapshotExtension

if typ.TYPE_CHECKING:
    import pytest
    from syrupy.assertion import SnapshotAssertion


def _write_markdown(path: pathlib.Path, title: str) -> None:
    """Write a tiny Markdown file with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n", encoding="utf-8")


def test_explicit_markdown_file_is_reported_verbatim(tmp_path: pathlib.Path) -> None:
    """Keep an explicitly named Markdown file in the reported path form."""
    target = tmp_path / "notes.md"
    _write_markdown(target, "Notes")

    files = discovery.discover_markdown_files([target], config.StilyagiConfig())

    assert files == [
        discovery.DiscoveredFile(
            reported_path=target.as_posix(),
            resolved_path=target.resolve(),
        ),
    ], "expected files == [discovery.DiscoveredFile(reported..."


def test_explicit_non_markdown_file_is_logged_and_skipped(
    tmp_path: pathlib.Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip a direct non-Markdown target without pretending it was linted."""
    target = tmp_path / "notes.txt"
    target.write_text("plain text\n", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="stilyagi.discovery"):
        files = discovery.discover_markdown_files([target], config.StilyagiConfig())

    assert files == [], "expected files == []"
    assert any(
        "ignoring non-Markdown target" in record.message for record in caplog.records
    ), "expected any(('ignoring non-Markdown target' in reco..."


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
    (root / "nested" / "loop").symlink_to(root, target_is_directory=True)

    files = discovery.discover_markdown_files([root], config.StilyagiConfig())

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
    assert normalised_files == snapshot(extension_class=JSONSnapshotExtension), (
        "expected deterministic discovery paths without ignor..."
    )
    assert all(isinstance(file, discovery.DiscoveredFile) for file in files), (
        "expected all((isinstance(file, discovery.DiscoveredF..."
    )
