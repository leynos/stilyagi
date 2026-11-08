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


def test_an_unresolvable_home_directory_is_an_operational_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report a failed `~` expansion as status 2 rather than a traceback.

    `Path.expanduser` raises a bare `RuntimeError` when it cannot determine the
    home directory. Expanding through `path_resolution.expand_user` turns that
    one environmental failure into the `PathResolutionError` this command
    reports, so the user sees a sentence naming the target instead of a stack
    trace.
    """
    from stilyagi import cli_config_command
    from stilyagi.config import path_resolution

    def _unresolvable(path: pathlib.Path) -> pathlib.Path:
        message = f"no home for {path}"
        raise path_resolution.PathResolutionError(message)

    # The command imports the helper by name, so the substitution has to
    # replace that binding rather than the module attribute it came from.
    monkeypatch.setattr(cli_config_command, "expand_user", _unresolvable)

    exit_code = cli.main(["config", "--target", "~/notes.md"])
    output = capsys.readouterr()

    assert exit_code == 2, "expected an unexpandable target to exit 2"
    assert not output.out, "expected no output when the target cannot expand"
    assert "cannot expand target" in output.err, (
        "expected the failure to name the target expansion that failed"
    )


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
