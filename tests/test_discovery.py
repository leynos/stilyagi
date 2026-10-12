"""Unit tests for deterministic mixed-source discovery."""

import logging
import pathlib
import typing as typ

import pytest
from stilyagi import cli, config, discovery, model
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.assertions import assert_with_context

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import os

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


def test_explicit_unregistered_file_returns_a_notice_and_is_skipped(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Return skip context without logging from the discovery query."""
    target = tmp_path / "notes.txt"
    target.write_text("plain text\n", encoding="utf-8")

    with caplog.at_level(logging.INFO, logger="stilyagi.discovery"):
        result = discovery.discover_files_with_summary(
            [target],
            config.StilyagiConfig(respect_gitignore=False),
        )
    assert not caplog.records, "expected discovery query not to emit log records"
    monkeypatch.chdir(tmp_path)
    exit_code = cli.main(["check", target.name])

    assert_with_context(
        result.skipped_files == 1,
        "expected result.skipped_files == 1 for the unregistered direct target",
    )
    assert result.skipped_by_reason == (
        discovery.SkippedCandidateCount("unregistered_candidate", 1),
    ), "the skip count retains its fixed, bounded reason"
    assert not result.files, "expected result.files to be empty"
    assert len(result.notices) == 1, "expected one structured discovery notice"
    assert exit_code == 0, "expected exit_code == 0"


def test_explicit_ignored_directory_is_not_walked_and_checks_zero_files(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An ignored directory target is skipped before traversal begins."""
    target = tmp_path / "node_modules"
    _write_markdown(target / "dependency.md", "Dependency")
    original_walk = pathlib.Path.walk
    walked_paths: list[pathlib.Path] = []

    def record_walk(
        path: pathlib.Path,
        *,
        follow_symlinks: bool = False,
        on_error: cabc.Callable[[OSError], None] | None = None,
    ) -> cabc.Iterator[tuple[pathlib.Path, list[str], list[str]]]:
        """Record requested walks while preserving pathlib's traversal."""
        walked_paths.append(path)
        yield from original_walk(
            path,
            follow_symlinks=follow_symlinks,
            on_error=on_error,
        )

    monkeypatch.setattr(pathlib.Path, "walk", record_walk)
    result = discovery.discover_files_with_summary([target], config.StilyagiConfig())
    monkeypatch.chdir(tmp_path)
    exit_code = cli.main(["check", target.name])
    captured = capsys.readouterr()

    assert not result.files, "expected result.files to be empty"
    assert not walked_paths, "expected no directory walks for an ignored target"
    assert exit_code == 0, "expected exit_code == 0"
    assert captured.out == (
        "checked 0 files (0 skipped, 0 unreadable); 0 errors, 0 warnings\n"
    ), "expected the zero-file run summary"


def test_directory_walk_failure_is_retained_with_partial_results(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preserve discovered files and traversal errors in the query result."""
    target = tmp_path / "docs"
    _write_markdown(target / "notes.md", "Notes")

    def walk_with_failure(
        path: pathlib.Path,
        *,
        follow_symlinks: bool = False,
        on_error: cabc.Callable[[OSError], None] | None = None,
    ) -> cabc.Iterator[tuple[pathlib.Path, list[str], list[str]]]:
        """Yield a partial directory result and report its later failure."""
        assert not follow_symlinks, "expected symlink traversal to remain disabled"
        yield path, [], ["notes.md"]
        assert on_error is not None, "expected a pathlib walk error callback"
        on_error(PermissionError(13, "permission denied", path.as_posix()))

    monkeypatch.setattr(pathlib.Path, "walk", walk_with_failure)
    result = discovery.discover_files_with_summary([target], config.StilyagiConfig())

    assert len(result.files) == 1, "expected the file found before the error"
    assert len(result.failures) == 1, "expected one retained traversal failure"
    assert isinstance(result.failures[0].error, PermissionError), (
        "expected the original traversal error"
    )
    with pytest.raises(PermissionError, match="permission denied"):
        discovery.discover_files([target], config.StilyagiConfig())


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
        ".git",
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
        "dist",
        "node_modules",
        "site-packages",
        "target",
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


def test_a_missing_target_is_retained_as_a_notice_and_contributes_nothing(
    tmp_path: pathlib.Path,
) -> None:
    """A target that is neither a file nor a directory is reported, not linted."""
    target = tmp_path / "absent.md"

    result = discovery.discover_files_with_summary(
        [target], config.StilyagiConfig(respect_gitignore=False)
    )

    assert not result.files, "a missing target contributes no files"
    assert result.notices == (
        discovery.DiscoveryNotice("missing_or_unsupported_target", target),
    ), "the missing target is retained for command-layer reporting"


def test_target_stat_failure_is_retained_as_a_discovery_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not turn an inaccessible explicit target into a missing-path notice."""
    target = tmp_path / "restricted.md"
    _write_markdown(target, "Restricted")
    original_lstat = pathlib.Path.lstat

    def fail_target_lstat(path: pathlib.Path) -> os.stat_result:
        """Raise a permission error only for the explicit target."""
        if path == target:
            raise PermissionError(13, "permission denied", target.as_posix())
        return original_lstat(path)

    monkeypatch.setattr(pathlib.Path, "lstat", fail_target_lstat)

    result = discovery.discover_files_with_summary(
        [target], config.StilyagiConfig(respect_gitignore=False)
    )

    assert not result.files, "an inaccessible target cannot be checked"
    assert result.skipped_files == 0, (
        "an operational failure is not a skipped candidate"
    )
    assert len(result.failures) == 1, "the stat error is retained as a failure"
    assert result.failures[0].path == target, "the failure retains the target path"
    assert isinstance(result.failures[0].error, PermissionError), (
        "the original permission error is retained"
    )


def test_target_expansion_failure_is_retained_as_a_discovery_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A home-directory lookup error remains visible to command reporting."""
    target = pathlib.Path("~/notes.md")
    original_expanduser = pathlib.Path.expanduser

    def fail_target_expansion(path: pathlib.Path) -> pathlib.Path:
        """Simulate an unavailable home directory for the requested target."""
        if path == target:
            raise RuntimeError
        return original_expanduser(path)

    monkeypatch.setattr(pathlib.Path, "expanduser", fail_target_expansion)

    result = discovery.discover_files_with_summary(
        [target], config.StilyagiConfig(respect_gitignore=False)
    )

    assert not result.files, "a target with no resolved home cannot be checked"
    assert len(result.failures) == 1, "the expansion error is retained"
    assert result.failures[0].path == target, "the raw target remains identifiable"
    assert isinstance(result.failures[0].error, RuntimeError), (
        "the original expansion error is retained"
    )


def test_candidate_resolution_failure_keeps_partial_discoveries(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path resolution error is retained without discarding other files."""
    root = tmp_path / "source"
    _write_markdown(root / "notes.md", "Notes")
    broken = root / "loop.py"
    broken.write_text('"""Loop."""\n', encoding="utf-8")
    original_resolve = pathlib.Path.resolve

    def fail_candidate_resolution(
        path: pathlib.Path,
        *,
        strict: bool = False,
    ) -> pathlib.Path:
        """Simulate a symlink-loop error for one candidate only."""
        if path == broken:
            raise RuntimeError
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(pathlib.Path, "resolve", fail_candidate_resolution)

    result = discovery.discover_files_with_summary(
        [root], config.StilyagiConfig(respect_gitignore=False)
    )

    assert [file.reported_path for file in result.files] == [
        (root / "notes.md").as_posix(),
    ], "a failed candidate does not discard successfully resolved files"
    assert len(result.failures) == 1, "the resolution error is retained"
    assert result.failures[0].path == broken, "the failure identifies the candidate"
    assert isinstance(result.failures[0].error, RuntimeError), (
        "the original resolution error is retained"
    )


def test_a_symlinked_directory_target_is_retained_as_a_notice_and_skipped(
    tmp_path: pathlib.Path,
) -> None:
    """A symlinked directory named on the command line is not followed."""
    real = tmp_path / "real"
    _write_markdown(real / "notes.md", "Notes")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    result = discovery.discover_files_with_summary(
        [link], config.StilyagiConfig(respect_gitignore=False)
    )

    assert not result.files, "a symlinked directory target is not followed"
    assert result.skipped_files == 1, "the skipped target contributes to the summary"
    assert result.notices == (
        discovery.DiscoveryNotice("symlinked_directory_target", link),
    ), "the skipped symlink is retained for command-layer reporting"
    assert result.skipped_by_reason == (
        discovery.SkippedCandidateCount("symlinked_directory_target", 1),
    ), "the symlink skip uses its fixed, bounded reason"


def test_skip_reason_counts_deduplicate_overlapping_targets(
    tmp_path: pathlib.Path,
) -> None:
    """Group skip metrics by reason while de-duplicating the total paths."""
    root = tmp_path / "source"
    unsupported = root / "data.json"
    unsupported.parent.mkdir()
    unsupported.write_text("{}\n", encoding="utf-8")
    link = root / "linked-source"
    link.symlink_to(root, target_is_directory=True)

    result = discovery.discover_files_with_summary(
        [root, unsupported, link], config.StilyagiConfig(respect_gitignore=False)
    )

    assert result.skipped_files == 2, "overlapping targets skip two distinct paths"
    assert result.skipped_by_reason == (
        discovery.SkippedCandidateCount("symlinked_directory_target", 1),
        discovery.SkippedCandidateCount("unregistered_candidate", 1),
    ), "fixed reason counts are deterministic"


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
