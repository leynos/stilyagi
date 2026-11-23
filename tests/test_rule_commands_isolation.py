"""Prove rule discovery never reads config, documents, plugins, or caches.

The catalogue answers from static declarations. This module installs sentinels
on every runtime boundary a rule *execution* would need -- configuration
loading, discovery, extraction, rule running, plugin entry points, and cache
access -- and then runs the discovery commands in-process. A boundary that is
touched fails the test immediately, so the isolation claim is observed rather
than assumed.

Two fresh-process probes cover what an in-process sentinel cannot: a config
read whose error is swallowed still reaches the filesystem, so an audit hook
records every file operation under the project directory, and a plugin lookup
is recorded even when the caller catches the failure. Targeted controls run
`check` against the config-loading and cache boundaries to prove those sentinels
are live call sites rather than decorative patches.
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


_PROBE_PREAMBLE = """\
import importlib.metadata
import os
import sys

root = os.path.realpath(os.getcwd())
side_effects = []


def _watch(event, args):
    if event not in {"open", "os.mkdir", "os.rename", "os.remove", "os.rmdir"}:
        return
    first = args[0] if args else None
    if not isinstance(first, (str, bytes, os.PathLike)):
        return
    path = os.path.realpath(os.fsdecode(first))
    if path == root or path.startswith(root + os.sep):
        side_effects.append((event, path))


def _forbidden(name):
    def note(*args, **kwargs):
        side_effects.append(("call", name))
        raise AssertionError(name)

    return note


sys.addaudithook(_watch)
importlib.metadata.entry_points = _forbidden("entry_points")

import stilyagi.config.resolve
import stilyagi.discovery
import stilyagi.engine
import stilyagi.rules.builtin.pack
import stilyagi.rules.builtin.text
import stilyagi.rules.registry

stilyagi.config.resolve.load_config_table = _forbidden("load_config_table")
stilyagi.discovery.discover_files = _forbidden("discover_files")
stilyagi.engine.extract_document = _forbidden("extract_document")
stilyagi.rules.builtin.pack.run_selected = _forbidden("run_selected")
stilyagi.rules.builtin.text.tokenize_segments = _forbidden("tokenize_segments")
stilyagi.rules.registry.run_rules = _forbidden("run_rules")

import stilyagi.cli
"""

_PROBE_EPILOGUE = """
if side_effects:
    raise SystemExit(f"import side effects: {side_effects!r}")
"""


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


def _tree_snapshot(root: pathlib.Path) -> dict[pathlib.Path, bytes]:
    """Return every file under ``root`` keyed by its relative path."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _run_import_probe(
    root: pathlib.Path,
    extra: str = "",
) -> subprocess.CompletedProcess[bytes]:
    """Import the command line in a fresh interpreter and detect side effects."""
    script = f"{_PROBE_PREAMBLE}{extra}{_PROBE_EPILOGUE}"
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
        [sys.executable, "-c", script],
        cwd=root,
        env=python_module_environment(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=60,
    )


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
        pytest.param(
            "stilyagi.config.ConfigResolver.resolve_with_provenance",
            id="config-loading",
        ),
        pytest.param("stilyagi.cli.open_extraction_cache", id="cache-alias"),
    ],
)
def test_check_trips_a_command_boundary_alias(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    """Every check boundary is a real call site, not a decorative patch.

    A valid project lets discovery succeed, so `check` reaches the config
    resolver and the extraction cache. Patching each boundary in turn proves
    the sentinels on the discovery tests guard live call sites.
    """
    monkeypatch.chdir(tmp_path)
    _valid_project(tmp_path)
    monkeypatch.setattr(target, _forbidden(target))

    with pytest.raises(AssertionError, match="rule discovery must not call"):
        cli.main(["check", "."])


def test_importing_the_command_line_has_no_runtime_side_effects(
    tmp_path: pathlib.Path,
) -> None:
    """Importing the CLI performs no config, extraction, provider, or cache work.

    The probe watches every file operation under the project directory and
    forbids the provider and execution entry points before `stilyagi.cli` is
    imported. A config read whose error is caught still reaches the
    filesystem, and a plugin lookup whose error is caught still records the
    call, so neither can hide behind an exception handler.
    """
    _malformed_project(tmp_path)
    before = _tree_snapshot(tmp_path)

    completed = _run_import_probe(tmp_path)

    assert completed.returncode == 0, completed.stderr.decode()
    assert not completed.stdout, "expected the import probe to print nothing"
    assert not completed.stderr, "expected the import to report no side effect"
    assert _tree_snapshot(tmp_path) == before, (
        "expected the import to leave the project untouched"
    )


def test_import_probe_reports_a_swallowed_config_read(
    tmp_path: pathlib.Path,
) -> None:
    """A read whose error is caught is still recorded, so the probe is live."""
    _malformed_project(tmp_path)
    extra = (
        "\ntry:\n"
        "    with open('stilyagi.toml', encoding='utf-8') as stream:\n"
        "        stream.read()\n"
        "except OSError:\n"
        "    pass\n"
    )

    completed = _run_import_probe(tmp_path, extra)

    assert completed.returncode != 0, "expected the probe to reject the side effect"
    assert b"import side effects" in completed.stderr, (
        "expected the probe's failure report"
    )
    assert b"stilyagi.toml" in completed.stderr, (
        "expected the report to name the config file"
    )


def test_discovery_commands_leave_the_directory_unchanged(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both commands leave every file and directory exactly as they found it."""
    monkeypatch.chdir(tmp_path)
    _malformed_project(tmp_path)
    before = _tree_snapshot(tmp_path)

    assert cli.main(["rules"]) == 0, "expected the list command to succeed"
    assert cli.main(["rule", "MD001", "--output-format", "json"]) == 0, (
        "expected the detail command to succeed"
    )
    capsys.readouterr()

    assert _tree_snapshot(tmp_path) == before, (
        "expected rule discovery to write no file"
    )
