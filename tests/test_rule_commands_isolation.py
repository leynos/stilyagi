"""Prove rule discovery never reads config, documents, plugins, or caches.

The catalogue answers from static declarations. This module installs sentinels
on every runtime boundary a rule *execution* would need -- configuration
loading, discovery, extraction, rule running, plugin entry points, and cache
access -- and then runs the discovery commands in-process. A boundary that is
touched fails the test immediately, so the isolation claim is observed rather
than assumed.

One test deliberately runs `check` against the same sentinels. It proves the
guard is live: a command that legitimately reads configuration trips the
sentinel, so a future `rules` regression that starts reading config cannot
pass because the sentinel was silently ineffective.
"""

import importlib.metadata
import json
import subprocess  # ruff: ignore[suspicious-subprocess-import] - a trusted local interpreter runs the import probe.
import sys
import typing as typ

import pytest
from stilyagi import cli

from tests.support.subprocess_env import python_module_environment

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib

_SENTINEL_METHODS: typ.Final[tuple[tuple[str, str], ...]] = (
    ("stilyagi.config.ConfigResolver", "resolve_config_for_path"),
    ("stilyagi.config.ConfigResolver", "_resolve_config_for_path"),
    ("stilyagi.config.ConfigResolver", "_inspect_config_for_path"),
)

_SENTINEL_FUNCTIONS: typ.Final[tuple[str, ...]] = (
    "stilyagi.config.load_config_file",
    "stilyagi.config.resolve_config_for_path",
    "stilyagi.discovery.discover_files",
    "stilyagi.discovery.discover_files_with_summary",
    "stilyagi.engine.extract_document",
    "stilyagi.engine.extract_document_result",
    "stilyagi.rules.registry.run_rules",
    "stilyagi.rules.builtin.pack.run_selected",
    "stilyagi.cli_extraction_cache.open_extraction_cache",
    # Aliases imported into the command modules are the actual call sites for
    # the check path, so patching only their defining modules would leave a
    # sentinel the command never consults. `cli` binds
    # `open_extraction_cache` at import, which is why its own alias is listed
    # separately from the defining module above.
    "stilyagi.cli.open_extraction_cache",
    "stilyagi.cli.cache_policy_for",
    "stilyagi.cli.discover_targets",
    "stilyagi.cli.collect_checked_files",
    "stilyagi.cli_apply.apply_fixes",
)


def _forbidden(name: str) -> cabc.Callable[..., typ.NoReturn]:
    """Return a sentinel that fails the test when ``name`` is invoked."""

    def explode(*_args: object, **_kwargs: object) -> typ.NoReturn:
        """Report the forbidden boundary crossing."""
        message = f"rule discovery must not call {name}"
        raise AssertionError(message)

    return explode


def _install_sentinels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every runtime boundary with a failing sentinel."""
    for module_name, attribute in _SENTINEL_METHODS:
        monkeypatch.setattr(f"{module_name}.{attribute}", _forbidden(attribute))
    for target in _SENTINEL_FUNCTIONS:
        monkeypatch.setattr(target, _forbidden(target))
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        _forbidden("importlib.metadata.entry_points"),
    )


def _malformed_project(root: pathlib.Path) -> None:
    """Write a source file and a configuration no parser can read."""
    (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (root / "stilyagi.toml").write_text("[lint\n", encoding="utf-8")


def _valid_project(root: pathlib.Path) -> None:
    """Write a source file and a valid minimal configuration."""
    (root / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (root / "stilyagi.toml").write_text("[lint]\n", encoding="utf-8")


def test_rules_command_succeeds_without_any_runtime_boundary(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The list command ignores a malformed config and reads no document."""
    monkeypatch.chdir(tmp_path)
    _malformed_project(tmp_path)
    _install_sentinels(monkeypatch)

    assert cli.main(["rules", "--output-format", "json"]) == 0, (
        "expected static discovery to succeed despite malformed config"
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert [rule["code"] for rule in payload["rules"]] == [
        "MD001",
        "STY001",
        "TERM001",
    ], "expected the complete inventory"
    assert not captured.err, "expected an isolated command to write no errors"


def test_rule_detail_succeeds_without_any_runtime_boundary(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The detail command reads no configuration and extracts no document."""
    monkeypatch.chdir(tmp_path)
    _malformed_project(tmp_path)
    _install_sentinels(monkeypatch)

    assert cli.main(["rule", "TERM001"]) == 0, (
        "expected static detail to succeed despite malformed config"
    )
    captured = capsys.readouterr()
    assert "TERM001 banned-term" in captured.out, "expected the requested rule"
    assert not captured.err, "expected an isolated command to write no errors"


@pytest.mark.parametrize(
    "target",
    [
        pytest.param("stilyagi.cli.discover_targets", id="discovery-alias"),
        pytest.param("stilyagi.cli.collect_checked_files", id="check-loop-alias"),
    ],
)
def test_check_trips_a_command_boundary_alias(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    """A command-boundary alias is a real call site, not a decorative patch.

    The cache alias cannot be exercised here: `check` builds the extraction
    cache only after discovery succeeds, so a malformed project would return
    two before reaching it. The cache boundary is covered by the all-sentinels
    control below, which fails on the first alias reached.
    """
    monkeypatch.chdir(tmp_path)
    _valid_project(tmp_path)
    monkeypatch.setattr(target, _forbidden(target))

    with pytest.raises(AssertionError, match="rule discovery must not call"):
        cli.main(["check", "."])


def test_importing_the_command_line_ignores_malformed_config(
    tmp_path: pathlib.Path,
) -> None:
    """Importing the CLI has no configuration side effect.

    Every `stilyagi.*` import first runs the package `__init__`, which imports
    `engine` and `model`; that pre-existing package boundary is not rule
    execution. What this probe checks is that the import does not *read* the
    malformed configuration beside it.
    """
    _malformed_project(tmp_path)

    completed = subprocess.run(
        [sys.executable, "-c", "import stilyagi.cli"],
        cwd=tmp_path,
        env=python_module_environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr


def test_discovery_commands_leave_the_directory_unchanged(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both commands leave every file and directory exactly as they found it."""
    monkeypatch.chdir(tmp_path)
    _malformed_project(tmp_path)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert cli.main(["rules"]) == 0, "expected the list command to succeed"
    assert cli.main(["rule", "MD001", "--output-format", "json"]) == 0, (
        "expected the detail command to succeed"
    )
    capsys.readouterr()

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before, "expected rule discovery to write no file"
