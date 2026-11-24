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

from tests.support.assertions import assert_with_context
from tests.support.subprocess_env import run_python_module

if typ.TYPE_CHECKING:
    import pathlib
    import subprocess

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

    assert_with_context(
        snapshot(extension_class=JSONSnapshotExtension) == _records(payload),
        "the stable diagnostic records changed",
    )


def test_codes_are_reported_in_source_order(tmp_path: pathlib.Path) -> None:
    """Findings follow file order, then source position within a file."""
    records = _records(_check(_tree(tmp_path)))
    paths = [record["path"] for record in records]

    assert_with_context(
        paths == ["lib.rs", "pkg.py", "pkg.py"],
        f"expected lib.rs before pkg.py, got {paths}",
    )
    located = [
        (typ.cast("dict[str, int]", record["location"])["line"], record["code"])
        for record in records
        if record["path"] == "pkg.py"
    ]
    assert_with_context(
        located == [(2, "DOC003"), (6, "DOC001")],
        f"expected the class finding before the function finding, got {located}",
    )


def test_every_finding_is_a_warning_without_a_fix(
    tmp_path: pathlib.Path,
) -> None:
    """These rules are diagnostic-only, so the run exits 0."""
    records = _records(_check(_tree(tmp_path)))

    assert_with_context(
        {record["severity"] for record in records} == {"warning"},
        f"expected warning severity throughout, got {records}",
    )
    assert_with_context(
        all(record["fix"] is None for record in records),
        "expected no documentation rule to offer a fix",
    )


def test_markdown_receives_no_documentation_rule(tmp_path: pathlib.Path) -> None:
    """The Markdown document is checked but earns none of these codes."""
    records = _records(_check(_tree(tmp_path)))

    assert_with_context(
        [record for record in records if record["path"] == "notes.md"] == [],
        "expected no documentation finding in Markdown",
    )


def test_disabled_rules_report_nothing(tmp_path: pathlib.Path) -> None:
    """The default ``DOC`` prefix alone must not enable the rules."""
    payload = _check(_tree(tmp_path, config=_CONFIG.replace("true", "false")))

    assert payload["diagnostics"] == [], "expected false opt-in to be inert"
    assert_with_context(
        typ.cast("dict[str, int]", payload["summary"])["checked_files"] == 3,
        "expected all three documents to still be extracted and checked",
    )


def test_absent_configuration_reports_nothing(tmp_path: pathlib.Path) -> None:
    """A tree with no configuration file cannot opt the rules in."""
    payload = _check(_tree(tmp_path, config=None))

    assert_with_context(
        payload["diagnostics"] == [],
        "expected no findings without a configuration file",
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

    assert_with_context(
        result.returncode == 2,
        f"expected exit 2 for a bad option, got {result.returncode}",
    )
    assert_with_context(
        b"rule.DOC001.enabled" in result.stderr,
        f"expected the error to name the option, got {result.stderr!r}",
    )


def _run(
    root: pathlib.Path,
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    """Run ``python -m stilyagi`` in ``root`` with the given arguments."""
    return run_python_module(root, "check", ".", "--no-cache", *arguments, timeout=120)


_MALFORMED_PYTHON = (
    '"""Module docstring before malformed Python source."""\n'
    "\n"
    "\n"
    "def broken_function(\n"
    '    """A docstring in a function whose signature never closes."""\n'
    '    return "unreachable"\n'
)


def _mixed_error_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a tree holding one error-severity and two documentation findings."""
    root = _tree(
        tmp_path,
        config='[lint]\nselect = ["DOC", "MD"]\n\n'
        "[rule.DOC001]\nenabled = true\n\n"
        "[rule.DOC002]\nenabled = true\n\n"
        "[rule.DOC003]\nenabled = true\n",
    )
    (root / "notes.md").write_text("# Start\n\n### Jump\n", encoding="utf-8")
    return root


def test_the_text_renderer_reports_documentation_rules(
    tmp_path: pathlib.Path,
    snapshot: SnapshotAssertion,
) -> None:
    """The human renderer names each documentation code at its own location."""
    result = _run(_tree(tmp_path))
    lines = [
        line
        for line in result.stdout.decode().splitlines()
        if "DOC00" in line or line.startswith("checked ")
    ]

    assert result.returncode == 0, (
        f"expected a warning-only run to exit 0, got {result.returncode}"
    )
    assert_with_context(
        snapshot == lines,
        "the text renderer's documentation lines changed",
    )


def test_error_findings_exit_one_alongside_documentation_warnings(
    tmp_path: pathlib.Path,
) -> None:
    """An error-severity finding fails the run; documentation warnings do not."""
    result = _run(_mixed_error_tree(tmp_path), "--output-format", "json")
    payload = typ.cast("dict[str, object]", json.loads(result.stdout))

    assert result.returncode == 1, (
        f"expected exit 1 for an error finding, got {result.returncode}"
    )
    severities = {
        typ.cast("dict[str, object]", record)["severity"]
        for record in typ.cast("list[object]", payload["diagnostics"])
    }
    assert severities == {"error", "warning"}, (
        f"expected both severities in one run, got {severities}"
    )


def test_extractor_diagnostics_survive_either_opt_in(
    tmp_path: pathlib.Path,
) -> None:
    """Extractor diagnostics persist unchanged while documentation findings vary."""
    observed: dict[str, list[dict[str, object]]] = {}
    for label, enabled in (("enabled", "true"), ("disabled", "false")):
        root = tmp_path / label
        root.mkdir()
        (root / "stilyagi.toml").write_text(
            f'[lint]\nselect = ["DOC"]\n\n[rule.DOC001]\nenabled = {enabled}\n'
            f"\n[rule.DOC002]\nenabled = {enabled}\n"
            f"\n[rule.DOC003]\nenabled = {enabled}\n",
            encoding="utf-8",
        )
        (root / "broken.py").write_text(_MALFORMED_PYTHON, encoding="utf-8")
        # A mixed tree, so the enabled run also carries documentation findings
        # beside the extractor diagnostics on the malformed Python file.
        (root / "pkg.py").write_text(_PYTHON, encoding="utf-8")
        (root / "lib.rs").write_text(_RUST, encoding="utf-8")
        (root / "notes.md").write_text(_MARKDOWN, encoding="utf-8")
        result = _run(root, "--output-format", "json")
        payload = typ.cast("dict[str, object]", json.loads(result.stdout))
        observed[label] = [
            typ.cast("dict[str, object]", record)
            for record in typ.cast("list[object]", payload["diagnostics"])
        ]

    extractor = {
        label: [
            record for record in records if not str(record["code"]).startswith("DOC")
        ]
        for label, records in observed.items()
    }
    documentation = [
        record
        for record in observed["enabled"]
        if str(record["code"]).startswith("DOC")
    ]

    assert_with_context(
        extractor["enabled"],
        "expected the malformed source to be diagnosed",
    )
    assert_with_context(
        {record["code"] for record in extractor["enabled"]}
        == {"python-parse-recovery"},
        f"expected only extractor codes, got {extractor['enabled']}",
    )
    assert_with_context(
        extractor["enabled"] == extractor["disabled"],
        "expected extractor diagnostics to be independent of the rule opt-in",
    )
    assert_with_context(
        documentation,
        "expected documentation findings in the enabled mixed tree",
    )
    assert_with_context(
        not [
            record
            for record in observed["disabled"]
            if str(record["code"]).startswith("DOC")
        ],
        "expected no documentation findings while the rules are disabled",
    )
    assert_with_context(
        result.returncode == 0,
        f"expected recovery warnings to exit 0, got {result.returncode}",
    )
