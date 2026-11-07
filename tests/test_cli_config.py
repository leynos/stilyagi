"""Tests for the command-line to configuration translation.

The record returned by `resolve_target_config` is the one place a target's
effective configuration and its provenance are decided together, so these
tests pin both halves of that pair rather than the resolver underneath it.

Explicit `--config` provenance gets its own cases here. It is the one route
where the governing file is not the one nearest the target, so a fallback to
discovery, the working directory, or the first explicit file would still pass
every nearest-config test while quietly applying the wrong per-file ignores.
"""

import io
import pathlib
import typing as typ

from stilyagi import cli, cli_args, cli_config, config
from stilyagi.rules import registry as rules_registry

if typ.TYPE_CHECKING:
    import pytest
    from stilyagi import diagnostics


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


def test_the_last_explicit_config_file_governs(tmp_path: pathlib.Path) -> None:
    """Explicit files layer in order, so the final one decides the target."""
    target = _markdown_target(tmp_path)
    first = tmp_path / "first.toml"
    first.write_text('[lint]\nselect = ["MD"]\n', encoding="utf-8")
    second = tmp_path / "second.toml"
    second.write_text('[lint]\nselect = ["STY"]\n', encoding="utf-8")

    resolved = cli_config.resolve_target_config(
        target,
        cli_args.CheckOptions(
            targets=(str(target),),
            explicit_config=(str(first), str(second)),
        ),
        config.ConfigResolver(),
    )

    assert resolved.config_file == second, (
        f"expected the last explicit file to govern, got {resolved.config_file}"
    )
    assert resolved.config.lint.select == ("STY",), (
        f"expected the last file's selection, got {resolved.config.lint.select}"
    )


def test_an_explicit_config_anchors_per_file_ignores_from_elsewhere(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-file globs follow the explicit config, not the working directory.

    The config sits in `project/`, the run starts in `tmp_path`, and both
    documents live under `project/docs/`. Only the file the glob names may lose
    its finding, so a provenance fallback that anchored on the working
    directory would leave both findings live and fail the control assertion.
    The run is isolated, so the explicit config is the only one that could
    supply the ignore.
    """
    project = tmp_path / "project"
    docs = project / "docs"
    docs.mkdir(parents=True)
    config_file = project / "stilyagi.toml"
    config_file.write_text(
        '[lint]\nselect = ["STY"]\nper-file-ignores = { "docs/doc.md" = ["STY001"] }\n',
        encoding="utf-8",
    )
    for name in ("doc.md", "control.md"):
        (docs / name).write_text("# Title\n\nword word\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    produced: dict[str, list[str]] = {}

    def record(request: rules_registry.RuleRunRequest) -> list[diagnostics.Diagnostic]:
        """Run the real runner, remembering what each document produced."""
        found = rules_registry.run_rules(request)
        produced[pathlib.Path(request.reported_path).name] = [
            diagnostic.code for diagnostic in found
        ]
        return found

    cli.run_check(
        cli.CheckOptions(
            targets=("project/docs/doc.md", "project/docs/control.md"),
            explicit_config=(str(config_file),),
            isolated=True,
        ),
        collaborators=cli.CheckCollaborators(rule_runner=record, output=io.StringIO()),
    )

    assert "STY001" not in produced["doc.md"], (
        "the explicit config's per-file ignore must apply to the document it names"
    )
    assert "STY001" in produced["control.md"], (
        "the control document must still report its repeated word"
    )
