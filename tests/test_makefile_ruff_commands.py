"""Hermetic contracts for Ruff command construction in Makefile targets."""

import os
import pathlib
import shutil
import typing as typ

import pytest
from cmd_mox import Invocation
from cmd_mox.command_runner import CommandRunner

pytest_plugins = ("cmd_mox.pytest_plugin",)

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
SENTINEL_RUFF_VERSION = "sentinel"


@pytest.mark.parametrize(
    ("target", "expected_ruff_invocations"),
    [
        pytest.param("fmt", 2, id="fmt"),
        pytest.param("check-fmt", 1, id="check-fmt"),
        pytest.param("lint", 1, id="lint"),
        pytest.param("spelling-helper-test", 2, id="spelling-helper-test"),
    ],
)
def test_makefile_targets_build_ruff_commands_from_the_version_pin(
    cmd_mox: CmdMox,
    tmp_path: pathlib.Path,
    target: str,
    expected_ruff_invocations: int,
) -> None:
    """Override the Ruff pin and verify every Ruff-using target honours it."""
    for command in ("uv", "cargo", "rustfmt", "whitaker", "mdformat-all"):
        cmd_mox.spy(command).returns()

    shim_dir = cmd_mox.environment.shim_dir
    assert shim_dir is not None, "expected cmd-mox command shims"
    make = shutil.which("make")
    assert make is not None, "expected make executable"

    response = CommandRunner(cmd_mox.environment).run(
        Invocation(
            command=make,
            args=[
                "--directory",
                str(REPOSITORY_ROOT),
                "--no-print-directory",
                f"UV={shim_dir / 'uv'}",
                f"CARGO={shim_dir / 'cargo'}",
                f"WHITAKER={shim_dir / 'whitaker'}",
                f"MDFORMAT_ALL={shim_dir / 'mdformat-all'}",
                f"RUFF_VERSION={SENTINEL_RUFF_VERSION}",
                target,
            ],
            stdin="",
            env={},
        ),
        dict(os.environ, HOME=str(tmp_path / "home")),
    )
    assert response.exit_code == 0, response.stderr

    ruff_invocations = tuple(
        invocation
        for invocation in cmd_mox.journal
        if invocation.command == "uv"
        and invocation.args[:2] == ["tool", "run"]
        and invocation.args[2].startswith("ruff@")
    )
    assert len(ruff_invocations) == expected_ruff_invocations, (
        f"expected {expected_ruff_invocations} Ruff invocations for {target}"
    )
    assert all(
        invocation.args[2] == f"ruff@{SENTINEL_RUFF_VERSION}"
        for invocation in ruff_invocations
    ), "expected every recorded Ruff invocation to use the sentinel version"
