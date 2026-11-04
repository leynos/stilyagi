"""Tests for the command-line to configuration translation.

The record returned by `resolve_target_config` is the one place a target's
effective configuration and its provenance are decided together, so these
tests pin both halves of that pair rather than the resolver underneath it.
"""

import pathlib

from stilyagi import cli_args, cli_config, config


def _markdown_target(directory: pathlib.Path) -> pathlib.Path:
    """Create a Markdown target inside *directory* and return its path."""
    target = directory / "doc.md"
    target.write_text("# Title\n", encoding="utf-8")
    return target


def test_resolve_target_config_pairs_the_config_with_its_file(
    tmp_path: pathlib.Path,
) -> None:
    """A discovered config file should be reported alongside its config."""
    config_file = tmp_path / "stilyagi.toml"
    config_file.write_text("cache-dir = '.from-file'\n", encoding="utf-8")
    target = _markdown_target(tmp_path)

    resolved = cli_config.resolve_target_config(
        target,
        cli_args.CheckOptions(targets=(str(target),)),
        config.ConfigResolver(),
    )

    assert resolved.config_file == config_file, (
        f"expected the governing config file, got {resolved.config_file}"
    )
    assert resolved.config.cache_dir == pathlib.Path(".from-file"), (
        "expected the configuration the record reports to be the one the file "
        f"supplied, got {resolved.config.cache_dir}"
    )


def test_resolve_target_config_reports_no_file_for_inline_only_input(
    tmp_path: pathlib.Path,
) -> None:
    """Inline-only configuration should be paired with an absent file."""
    target = _markdown_target(tmp_path)

    resolved = cli_config.resolve_target_config(
        target,
        cli_args.CheckOptions(
            targets=(str(target),),
            explicit_config=('cache-dir = ".inline"',),
        ),
        config.ConfigResolver(),
    )

    assert resolved.config_file is None, (
        f"expected no governing file, got {resolved.config_file}"
    )
    assert resolved.config.cache_dir == pathlib.Path(".inline"), (
        f"expected the inline override to apply, got {resolved.config.cache_dir}"
    )
