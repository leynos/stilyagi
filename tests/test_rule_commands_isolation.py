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
import typing as typ

import pytest
from stilyagi import cli

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


def test_check_trips_the_config_sentinel(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sentinels are effective: a config-reading command trips them."""
    monkeypatch.chdir(tmp_path)
    _malformed_project(tmp_path)
    _install_sentinels(monkeypatch)

    with pytest.raises(AssertionError, match="rule discovery must not call"):
        cli.main(["check", "."])


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
