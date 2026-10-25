"""Public CLI tests for effective configuration inspection."""

import json
import typing as typ

from stilyagi import cli
from stilyagi.cli_config import resolve_target_config
from stilyagi.config import ConfigResolver
from syrupy.extensions.json import JSONSnapshotExtension

from tests.config_resolution_support import _make_markdown_target, _write_config

if typ.TYPE_CHECKING:
    import pathlib

    import pytest
    from syrupy.assertion import SnapshotAssertion


def test_config_parser_accepts_inspection_options() -> None:
    """Parse the config command without routing it through `check`."""
    parsed = cli.build_parser().parse_args([
        "config",
        "lint.select",
        "--target",
        "notes.md",
        "--config",
        'lint.ignore = ["STY001"]',
        "--isolated",
        "--select",
        "DOC",
        "--output-format",
        "json",
    ])

    assert parsed.command == "config", "expected the config subcommand"
    assert parsed.key == "lint.select", "expected the positional key"
    assert parsed.target == "notes.md", "expected the inspection target"


def test_config_json_shows_all_defaults_without_creating_cache(
    capsys: pytest.CaptureFixture[str],
    snapshot: SnapshotAssertion,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose default values and origins without filesystem side effects."""
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["config", "--output-format", "json"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected config inspection to succeed"
    assert not output.err, "expected no diagnostic on a successful inspection"
    assert payload["values"]["cache-dir"] == ".stilyagi_cache", (
        "expected the default cache directory"
    )
    assert payload["values"]["lint"]["select"] == [
        "MD",
        "DOC",
        "PUN",
        "STY",
        "PYDOC",
    ], "expected the default enabled rule selection"
    assert payload["origins"]["cache-dir"] == {
        "kind": "default",
        "source_file": None,
        "cli_overridden": False,
    }, "expected the default cache directory provenance"
    assert not (tmp_path / ".stilyagi_cache").exists(), (
        "expected inspection not to create a cache"
    )
    assert payload == snapshot(extension_class=JSONSnapshotExtension), (
        "expected the JSON config snapshot"
    )


def test_config_text_output_is_stable(
    capsys: pytest.CaptureFixture[str], snapshot: SnapshotAssertion
) -> None:
    """Keep the human-readable view deterministic and snapshot its contract."""
    exit_code = cli.main(["config"])
    output = capsys.readouterr()

    assert exit_code == 0, "expected config inspection to succeed"
    assert not output.err, "expected no diagnostic on a successful inspection"
    assert output.out == snapshot(extension_class=JSONSnapshotExtension), (
        "expected stable text output"
    )


def test_json_inspection_serializes_toml_dates_and_non_finite_floats(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Render supported TOML values as standards-compliant JSON values."""
    config_file = tmp_path / "stilyagi.toml"
    _write_config(
        config_file,
        "[rule.STY001]\nrelease-date = 2026-10-24\nscore = nan",
    )
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "rule",
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected TOML values to remain inspectable"
    assert not output.err, "expected no diagnostic on a successful inspection"
    assert payload["value"]["STY001"] == {
        "release-date": "2026-10-24",
        "score": "nan",
    }, "expected TOML date and non-finite float values as JSON strings"


def test_inline_override_reports_inherited_file_origin(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Report the file origin displaced by an inline dotted-key override."""
    base = tmp_path / "base.toml"
    _write_config(base, '[lint]\nselect = ["MD001", "MD002"]')
    project = tmp_path / "project"
    project.mkdir()
    _write_config(project / "stilyagi.toml", f'extend = "{base}"')
    target = _make_markdown_target(project)

    exit_code = cli.main([
        "config",
        "lint.select",
        "--target",
        str(target),
        "--config",
        'lint.select = ["STY001"]',
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected key inspection to succeed"
    assert not output.err, "expected no diagnostic on a successful inspection"
    assert payload["key"] == "lint.select", "expected the requested dotted key"
    assert payload["value"] == ["STY001"], "expected the inline override value"
    origin = payload["origins"]["lint.select"]
    assert origin["kind"] == "inline", "expected inline source provenance"
    assert origin["source_file"] == str(base.resolve()), (
        "expected the displaced inherited file source"
    )
    assert origin["cli_overridden"], "expected inline overrides to be marked"


def test_flag_override_uses_the_check_selection_translation(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Apply the same rule-selection translation used by `check`."""
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, '[lint]\nselect = ["MD001"]')

    exit_code = cli.main([
        "config",
        "lint.select",
        "--target",
        str(_make_markdown_target(tmp_path)),
        "--select",
        "STY001",
        "--extend-select",
        "DOC001",
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected flag inspection to succeed"
    assert payload["value"] == ["STY001", "DOC001"], (
        "expected selection flags to replace then extend the configured rules"
    )
    assert payload["origins"]["lint.select"] == {
        "kind": "flag",
        "source_file": str(config_file.resolve()),
        "cli_overridden": True,
    }, "expected flag provenance for the selected rules"


def test_config_values_match_check_resolution_for_the_same_inputs(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Keep inspection values aligned with the existing check resolver."""
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, '[lint]\nselect = ["MD001"]')
    target = _make_markdown_target(tmp_path)
    check_options = cli.CheckOptions(
        targets=(str(target),),
        explicit_config=('lint.ignore = ["DOC001"]',),
        select=("STY001",),
        extend_select=("DOC002",),
    )
    check_config = resolve_target_config(target, check_options, ConfigResolver())

    exit_code = cli.main([
        "config",
        "--target",
        str(target),
        "--config",
        'lint.ignore = ["DOC001"]',
        "--select",
        "STY001",
        "--extend-select",
        "DOC002",
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected config inspection to succeed"
    assert tuple(payload["values"]["lint"]["select"]) == check_config.lint.select, (
        "expected config inspection and check to agree on selected rules"
    )
    assert tuple(payload["values"]["lint"]["ignore"]) == check_config.lint.ignore, (
        "expected config inspection and check to agree on ignored rules"
    )


def test_table_inspection_includes_descendant_origins(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Return every leaf origin when the requested key names a table."""
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, '[lint]\npreview = true\nselect = ["STY001"]')
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "lint",
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected table inspection to succeed"
    assert payload["value"]["preview"] is True, "expected the configured preview flag"
    assert payload["value"]["select"] == ["STY001"], "expected the configured selection"
    assert set(payload["origins"]) == {
        "lint.fixable",
        "lint.ignore",
        "lint.per-file-ignores",
        "lint.preview",
        "lint.select",
        "lint.unfixable",
    }, "expected every lint leaf to carry source provenance"
    assert payload["origins"]["lint.preview"]["source_file"] == str(
        config_file.resolve()
    ), "expected preview provenance to identify the config file"
    assert payload["origins"]["lint.select"]["source_file"] == str(
        config_file.resolve()
    ), "expected selection provenance to identify the config file"
    assert payload["origins"]["lint.fixable"]["kind"] == "default", (
        "expected unspecified lint values to retain default provenance"
    )


def test_same_directory_config_precedence_is_preserved(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Use the existing supported-file order during inspection."""
    _write_config(tmp_path / ".stilyagi.toml", 'cache-dir = ".hidden"')
    _write_config(tmp_path / "stilyagi.toml", 'cache-dir = ".plain"')
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "cache-dir",
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected key inspection to succeed"
    assert payload["value"] == ".hidden", "expected the first supported config file"
    assert payload["origins"]["cache-dir"]["source_file"] == str(
        (tmp_path / ".stilyagi.toml").resolve()
    ), "expected provenance to identify the winning supported config file"


def test_nearest_config_origin_is_reported(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Use the nearest config without implicitly merging its ancestor."""
    _write_config(tmp_path / "stilyagi.toml", 'cache-dir = ".ancestor"')
    nested = tmp_path / "docs"
    nested.mkdir()
    child_config = nested / "stilyagi.toml"
    _write_config(child_config, 'cache-dir = ".nearest"')
    target = _make_markdown_target(nested)

    exit_code = cli.main([
        "config",
        "cache-dir",
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected key inspection to succeed"
    assert payload["value"] == ".nearest", "expected the nearest config value"
    assert payload["origins"]["cache-dir"] == {
        "kind": "file",
        "source_file": str(child_config.resolve()),
        "cli_overridden": False,
    }, "expected the nearest config file to supply the value"


def test_ordered_extend_sources_are_visible(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Report the last parent that wins in an ordered `extend` chain."""
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    child = tmp_path / "child.toml"
    _write_config(first, 'cache-dir = ".first"')
    _write_config(second, 'cache-dir = ".second"')
    _write_config(child, f'extend = ["{first}", "{second}"]')
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "cache-dir",
        "--target",
        str(target),
        "--isolated",
        "--config",
        str(child),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected key inspection to succeed"
    assert payload["value"] == ".second", "expected the last extended config to win"
    assert payload["origins"]["cache-dir"]["source_file"] == str(second.resolve()), (
        "expected provenance to point to the last winning parent"
    )


def test_isolated_mode_ignores_discovered_config(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Skip nearest-config discovery while retaining explicit inline values."""
    _write_config(tmp_path / "stilyagi.toml", 'cache-dir = ".discovered"')
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "cache-dir",
        "--target",
        str(target),
        "--isolated",
        "--config",
        'cache-dir = ".inline"',
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected isolated inspection to succeed"
    assert payload["value"] == ".inline", "expected isolated mode to use inline config"
    assert payload["origins"]["cache-dir"] == {
        "kind": "inline",
        "source_file": None,
        "cli_overridden": True,
    }, "expected the inline config to be the only source"
