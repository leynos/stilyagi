"""Operational-error tests for configuration inspection."""

import typing as typ

import pytest
from stilyagi import cli

from tests.config_resolution_support import _make_markdown_target, _write_config

if typ.TYPE_CHECKING:
    import pathlib


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param(["unknown.key"], "unknown configuration key", id="unknown"),
        pytest.param(
            ["--target", "missing.md"], "target does not exist", id="missing-target"
        ),
    ],
)
def test_config_inspection_errors_do_not_write_stdout(
    arguments: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
) -> None:
    """Return a useful error and no partial output for invalid requests."""
    if arguments == ["unknown.key"]:
        target = _make_markdown_target(tmp_path)
        arguments = [*arguments, "--target", str(target)]
    else:
        arguments = ["--target", str(tmp_path / "missing.md")]

    exit_code = cli.main(["config", *arguments, "--output-format", "json"])
    output = capsys.readouterr()

    assert exit_code == 2, "expected configuration inspection errors to exit 2"
    assert not output.out, "expected errors to leave standard output empty"
    assert message in output.err, "expected a useful config inspection error"


def test_extend_cycle_is_reported_without_partial_json(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Reject cyclic inheritance before producing a JSON response."""
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    _write_config(first, f'extend = "{second}"')
    _write_config(second, f'extend = "{first}"')
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main([
        "config",
        "--target",
        str(target),
        "--isolated",
        "--config",
        str(first),
        "--output-format",
        "json",
    ])
    output = capsys.readouterr()

    assert exit_code == 2, "expected inheritance cycles to exit 2"
    assert not output.out, "expected the failed inspection to emit no JSON"
    assert "cycle detected" in output.err, "expected the inheritance cycle detail"


def test_invalid_toml_is_reported_without_partial_json(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    """Reject malformed discovered config before writing the result."""
    _write_config(tmp_path / "stilyagi.toml", "[lint\n")
    target = _make_markdown_target(tmp_path)

    exit_code = cli.main(["config", "--target", str(target), "--output-format", "json"])
    output = capsys.readouterr()

    assert exit_code == 2, "expected invalid TOML to exit 2"
    assert not output.out, "expected the failed inspection to emit no JSON"
    assert "toml" in output.err, "expected the invalid TOML detail"
