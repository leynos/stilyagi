"""Inspection of config keys whose components themselves contain dots.

A `per-file-ignores` glob such as `*.md` is one key component, not a nested
table. These tests pin the three observable consequences of that: text output
must quote the component rather than flattening it, table inspection must
report the leaf origin under the quoted spelling, and a key printed that way
must be selectable again unchanged.
"""

import json
import typing as typ

from stilyagi import cli

from tests.config_resolution_support import _make_markdown_target, _write_config

if typ.TYPE_CHECKING:
    import pathlib

    import pytest

_GLOB_CONFIG = '[lint.per-file-ignores]\n"*.md" = ["MD001"]'


def test_text_output_renders_a_dotted_config_key(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Render a config key that itself contains a dot without losing its shape.

    Flattening origins to a dotted string and splitting that string again
    reinterprets the name, which used to raise `KeyError` and exit non-zero.
    """
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, _GLOB_CONFIG)
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main(["config", "--target", str(target)])
    output = capsys.readouterr()

    assert exit_code == 0, "expected text output to accept a dotted config key"
    assert not output.err, "expected no diagnostic for a valid config"
    assert (
        f'lint.per-file-ignores."*.md" = ["MD001"]  # file from {config_file.resolve()}'
        in output.out
    ), "expected the dotted key to keep its quoted component and its origin"


def test_table_inspection_reports_a_dotted_config_key_origin(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Report descendant origins for a table whose keys contain dots."""
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, _GLOB_CONFIG)
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "lint.per-file-ignores",
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected table inspection to succeed"
    assert payload["value"] == {"*.md": ["MD001"]}, (
        "expected the glob key to remain one flat key"
    )
    expected_origin = {
        "kind": "file",
        "source_file": str(config_file.resolve()),
        "cli_overridden": False,
    }
    assert payload["origins"] == {'lint.per-file-ignores."*.md"': expected_origin}, (
        "expected the glob leaf origin under its quoted dotted spelling"
    )


def test_quoted_dotted_key_can_be_selected(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Select one dotted config key by quoting it in the requested key."""
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, _GLOB_CONFIG)
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        'lint.per-file-ignores."*.md"',
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 0, "expected the quoted key to be selectable"
    assert payload["key"] == 'lint.per-file-ignores."*.md"', (
        "expected the requested key to be echoed unchanged"
    )
    assert payload["value"] == ["MD001"], "expected the selected rule list"


def test_a_key_component_outside_the_basic_plane_round_trips(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Render an astral-plane component in a spelling TOML can read back.

    `json.dumps` escapes such a character as a surrogate pair by default, and
    TOML forbids surrogate code points in its Unicode escapes. Quoting that way
    made the command reject its own printed key, so this pins the round trip
    rather than only the rendering.
    """
    glob = "*.md-\U0001f600"
    config_file = tmp_path / "stilyagi.toml"
    _write_config(config_file, f'[lint.per-file-ignores]\n"{glob}" = ["MD001"]')
    target = _make_markdown_target(tmp_path)

    rendered = cli.main(["config", "--target", str(target)])
    text = capsys.readouterr()
    selected = cli.main([
        "config",
        f'lint.per-file-ignores."{glob}"',
        "--target",
        str(target),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()

    assert rendered == 0, "expected text output to accept an astral-plane key"
    assert selected == 0, "expected the printed key component to be selectable"
    assert not text.err, "expected no diagnostic for a valid config"
    assert not output.err, "expected no diagnostic selecting the printed key"
    assert f'lint.per-file-ignores."{glob}"' in text.out, (
        "expected the component to be quoted verbatim, not surrogate-escaped"
    )
    assert json.loads(output.out)["value"] == ["MD001"], (
        "expected the selected rule list to survive the round trip"
    )
