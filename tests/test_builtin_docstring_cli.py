"""Fresh-process command tests for the documentation rules.

The BDD scenarios call ``cli.main`` in the test process. These tests spawn
``python -m stilyagi`` instead, so the assertions are made against what a shell
observes: the process's own working directory, the configuration it discovers,
the bytes it writes, and its exit status.

Only the stable diagnostic records are snapshotted, with the temporary
directory removed from every path. Codes, severity, ordering, spans, and exit
status are asserted separately so a snapshot failure identifies a real contract
change rather than an incidental reformat.
"""

import json
import typing as typ

import pytest
from syrupy.extensions.json import JSONSnapshotExtension

from tests.support.subprocess_env import run_python_module

if typ.TYPE_CHECKING:
    import pathlib

    from syrupy.assertion import SnapshotAssertion

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

_CONFIG = (
    '[lint]\nselect = ["DOC"]\n\n'
    "[rule.DOC001]\nenabled = true\n\n"
    "[rule.DOC002]\nenabled = true\n\n"
    "[rule.DOC003]\nenabled = true\n"
)

_PYTHON = (
    'class Widget:\n    """Widget."""\n\n'
    'def read_rows():\n    """Read records.\n    More detail.\n    """\n'
)
_RUST = "/// Stores records\npub fn read() {}\n"
_MARKDOWN = "# Widget\n\nRead records\n"


def _tree(tmp_path: pathlib.Path, *, config: str | None = _CONFIG) -> pathlib.Path:
    """Write the mixed tree and return its root."""
    if config is not None:
        (tmp_path / "stilyagi.toml").write_text(config, encoding="utf-8")
    (tmp_path / "pkg.py").write_text(_PYTHON, encoding="utf-8")
    (tmp_path / "lib.rs").write_text(_RUST, encoding="utf-8")
    (tmp_path / "notes.md").write_text(_MARKDOWN, encoding="utf-8")
    return tmp_path


def _check(root: pathlib.Path) -> dict[str, object]:
    """Run the checker over ``root`` and return its decoded JSON payload."""
    result = run_python_module(
        root,
        "check",
        ".",
        "--output-format",
        "json",
        "--no-cache",
        timeout=120,
    )
    assert result.returncode == 0, (
        f"expected a warning-only run to exit 0, got {result.returncode}: "
        f"{result.stderr.decode(errors='replace')}"
    )
    return typ.cast("dict[str, object]", json.loads(result.stdout))


def _records(payload: dict[str, object]) -> list[dict[str, object]]:
    """Return the payload's diagnostics with the tree path removed."""
    return [
        typ.cast("dict[str, object]", diagnostic)
        for diagnostic in typ.cast("list[object]", payload["diagnostics"])
    ]


def test_mixed_tree_reports_every_documentation_rule(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """One run reports the three codes over Python, Rust, and Markdown."""
    payload = _check(_tree(tmp_path))

    assert snapshot(extension_class=JSONSnapshotExtension) == _records(payload), (
        "the stable diagnostic records changed"
    )


def test_codes_are_reported_in_source_order(tmp_path: pathlib.Path) -> None:
    """Findings follow file order, then source position within a file."""
    records = _records(_check(_tree(tmp_path)))
    paths = [record["path"] for record in records]

    assert paths == ["lib.rs", "pkg.py", "pkg.py"], (
        f"expected lib.rs before pkg.py, got {paths}"
    )
    located = [
        (typ.cast("dict[str, int]", record["location"])["line"], record["code"])
        for record in records
        if record["path"] == "pkg.py"
    ]
    assert located == [(2, "DOC003"), (6, "DOC001")], (
        f"expected the class finding before the function finding, got {located}"
    )


def test_every_finding_is_a_warning_without_a_fix(
    tmp_path: pathlib.Path,
) -> None:
    """These rules are diagnostic-only, so the run exits 0."""
    records = _records(_check(_tree(tmp_path)))

    assert {record["severity"] for record in records} == {"warning"}, (
        f"expected warning severity throughout, got {records}"
    )
    assert all(record["fix"] is None for record in records), (
        "expected no documentation rule to offer a fix"
    )


def test_markdown_receives_no_documentation_rule(tmp_path: pathlib.Path) -> None:
    """The Markdown document is checked but earns none of these codes."""
    records = _records(_check(_tree(tmp_path)))

    assert [record for record in records if record["path"] == "notes.md"] == [], (
        "expected no documentation finding in Markdown"
    )


def test_disabled_rules_report_nothing(tmp_path: pathlib.Path) -> None:
    """The default ``DOC`` prefix alone must not enable the rules."""
    payload = _check(_tree(tmp_path, config=_CONFIG.replace("true", "false")))

    assert payload["diagnostics"] == [], "expected false opt-in to be inert"
    assert typ.cast("dict[str, int]", payload["summary"])["checked_files"] == 3, (
        "expected all three documents to still be extracted and checked"
    )


def test_absent_configuration_reports_nothing(tmp_path: pathlib.Path) -> None:
    """A tree with no configuration file cannot opt the rules in."""
    payload = _check(_tree(tmp_path, config=None))

    assert payload["diagnostics"] == [], (
        "expected no findings without a configuration file"
    )


def test_repeated_runs_produce_identical_payloads(tmp_path: pathlib.Path) -> None:
    """Determinism holds across processes, not just within one."""
    root = _tree(tmp_path)

    first = _check(root)
    second = _check(root)

    assert first == second, "expected two fresh processes to agree exactly"


def test_malformed_opt_in_exits_two(tmp_path: pathlib.Path) -> None:
    """A malformed option is a configuration failure, not a silent skip."""
    root = _tree(
        tmp_path,
        config='[lint]\nselect = ["DOC"]\n\n[rule.DOC001]\nenabled = "yes"\n',
    )

    result = run_python_module(
        root, "check", ".", "--output-format", "json", "--no-cache", timeout=120
    )

    assert result.returncode == 2, (
        f"expected exit 2 for a bad option, got {result.returncode}"
    )
    assert b"rule.DOC001.enabled" in result.stderr, (
        f"expected the error to name the option, got {result.stderr!r}"
    )
