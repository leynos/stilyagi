"""BDD steps for the documentation rules through the real check command.

Nothing here injects a rule runner: the scenarios exercise the shipped builtin
pack end to end over a mixed tree of Markdown, Python, and Rust, so a scenario
fails if opt-in validation, the extractor, the target filtering, or the JSON
renderer stops agreeing. Assertions are made against the recorded diagnostics
and the process exit status, which is the boundary a user sees.
"""

import json
import pathlib
import typing as typ

import pytest
from pytest_bdd import given, parsers, then, when
from stilyagi import cli

from tests.support.assertions import assert_with_context

#: The opt-in tables every scenario starts from.
_ALL_ENABLED = (
    "[rule.DOC001]\nenabled = true\n\n"
    "[rule.DOC002]\nenabled = true\n\n"
    "[rule.DOC003]\nenabled = true\n"
)

#: Paths the mixed tree uses, so a scenario can add just the source it needs.
PYTHON_PATH = "pkg.py"
RUST_PATH = "lib.rs"
MARKDOWN_PATH = "notes.md"

_SEPARATION_PYTHON = (
    'def read_rows():\n    """Read records.\n    More detail.\n    """\n'
)
_PUNCTUATION_RUST = "/// Read records\npub fn read() {}\n"
_REDUNDANT_PYTHON = (
    'class Widget:\n    """Widget."""\n\nclass Other:\n    """Widget."""\n'
)


class DocScenarioState(typ.TypedDict, total=False):
    """The scenario's tree, configuration, and latest completed run."""

    root: pathlib.Path
    config: str
    exit_code: int
    stdout: str
    stderr: str
    first_codes: list[str]


def _write_config(root: pathlib.Path, rules: str) -> None:
    """Write the tree's configuration with the given rule tables."""
    (root / "stilyagi.toml").write_text(
        '[lint]\nselect = ["DOC"]\n\n' + rules,
        encoding="utf-8",
    )


def _scenario(tmp_path: pathlib.Path, rules: str) -> DocScenarioState:
    """Create an empty tree holding only a configuration."""
    _write_config(tmp_path, rules)
    return {"root": tmp_path, "config": rules}


def _append(state: DocScenarioState, name: str, text: str) -> None:
    """Add one file to the scenario tree."""
    (state["root"] / name).write_text(text, encoding="utf-8")


def _run(
    state: DocScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run one JSON check over the scenario tree and record the result."""
    monkeypatch.chdir(state["root"])
    state["exit_code"] = cli.main(["check", ".", "--output-format", "json"])
    captured = capsys.readouterr()
    state["stdout"] = captured.out
    state["stderr"] = captured.err


def _diagnostics(state: DocScenarioState) -> list[dict[str, object]]:
    """Parse the recorded JSON output into its diagnostic list."""
    payload = json.loads(state["stdout"])
    return typ.cast("list[dict[str, object]]", payload["diagnostics"])


def _codes(state: DocScenarioState) -> list[str]:
    """Return the reported codes in output order."""
    return [typ.cast("str", diagnostic["code"]) for diagnostic in _diagnostics(state)]


def _span_bytes(state: DocScenarioState, code: str) -> list[bytes]:
    """Return the source bytes each ``code`` finding addresses."""
    found: list[bytes] = []
    for diagnostic in _diagnostics(state):
        if diagnostic["code"] != code:
            continue
        span = typ.cast("dict[str, int]", diagnostic["span"])
        path = state["root"] / typ.cast("str", diagnostic["path"])
        source = path.read_bytes()
        found.append(source[span["byte_start"] : span["byte_end"]])
    return found


def _only_diagnostic(state: DocScenarioState, code: str) -> dict[str, object]:
    """Return the one diagnostic carrying ``code``, failing on any other count."""
    matching = [
        diagnostic for diagnostic in _diagnostics(state) if diagnostic["code"] == code
    ]
    assert_with_context(
        len(matching) == 1,
        f"expected exactly one {code} diagnostic, got {matching}",
    )
    return matching[0]


@given(
    "DOC001 is enabled for Python docstrings",
    target_fixture="doc_scenario_state",
)
def doc001_enabled(tmp_path: pathlib.Path) -> DocScenarioState:
    """Enable only the separation rule."""
    return _scenario(tmp_path, "[rule.DOC001]\nenabled = true\n")


@given(
    "DOC002 is enabled for Rust documentation comments",
    target_fixture="doc_scenario_state",
)
def doc002_enabled(tmp_path: pathlib.Path) -> DocScenarioState:
    """Enable only the punctuation rule."""
    return _scenario(tmp_path, "[rule.DOC002]\nenabled = true\n")


@given("DOC003 is enabled", target_fixture="doc_scenario_state")
def doc003_enabled(tmp_path: pathlib.Path) -> DocScenarioState:
    """Enable only the owner-summary rule."""
    return _scenario(tmp_path, "[rule.DOC003]\nenabled = true\n")


@given(
    "all three documentation rules are enabled",
    target_fixture="doc_scenario_state",
)
def all_rules_enabled(tmp_path: pathlib.Path) -> DocScenarioState:
    """Enable every documentation rule."""
    return _scenario(tmp_path, _ALL_ENABLED)


@given(parsers.parse('a function docstring contains "{first}" followed by "{second}"'))
def a_function_docstring_contains(
    doc_scenario_state: DocScenarioState,
    first: str,
    second: str,
) -> None:
    """Write a Python module whose one docstring touches its explanation."""
    source = f'def read_rows():\n    """{first}\n    {second}\n    """\n'
    _append(doc_scenario_state, PYTHON_PATH, source)


@given(parsers.parse('an item has the documentation comment "{comment}"'))
def an_item_has_the_comment(
    doc_scenario_state: DocScenarioState,
    comment: str,
) -> None:
    """Write a Rust item carrying the given documentation comment."""
    _append(doc_scenario_state, RUST_PATH, f"{comment}\npub fn read() {{}}\n")


@given(parsers.parse('class {name} has the docstring "{summary}"'))
def a_class_has_the_docstring(
    doc_scenario_state: DocScenarioState,
    name: str,
    summary: str,
) -> None:
    """Append one class with the given docstring to the Python module."""
    path = doc_scenario_state["root"] / PYTHON_PATH
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(
        f'{existing}\nclass {name}:\n    """{summary}"""\n',
        encoding="utf-8",
    )


@given("matching text occurs in Markdown and ordinary Python and Rust comments")
def matching_text_in_unsupported_surfaces(
    doc_scenario_state: DocScenarioState,
) -> None:
    """Write the same unpunctured text into every unsupported surface."""
    _append(doc_scenario_state, MARKDOWN_PATH, "# Widget\n\nRead records\n")
    _append(
        doc_scenario_state,
        PYTHON_PATH,
        "# Read records\ndef read():\n    return 1\n",
    )
    _append(
        doc_scenario_state,
        RUST_PATH,
        "// Read records\npub fn read() {}\n",
    )


@given("DOC002 is disabled")
def doc002_disabled(doc_scenario_state: DocScenarioState) -> None:
    """Turn the punctuation rule's opt-in off without touching its siblings."""
    rules = _ALL_ENABLED.replace(
        "[rule.DOC002]\nenabled = true",
        "[rule.DOC002]\nenabled = false",
    )
    _write_config(doc_scenario_state["root"], rules)


@given("the mixed-source tree has one offending summary for each rule")
def one_offending_summary_each(doc_scenario_state: DocScenarioState) -> None:
    """Write one summary that each enabled documentation rule reports."""
    _append(doc_scenario_state, PYTHON_PATH, _SEPARATION_PYTHON + _REDUNDANT_PYTHON)
    _append(doc_scenario_state, RUST_PATH, _PUNCTUATION_RUST)


@given(parsers.parse('a Rust module documentation comment reads "{comment}"'))
def a_rust_module_comment(
    doc_scenario_state: DocScenarioState,
    comment: str,
) -> None:
    """Write a module-level documentation comment."""
    _append(doc_scenario_state, RUST_PATH, f"//! {comment}\n\npub fn read() {{}}\n")


@given("a function docstring separates its summary with a blank line")
def a_separated_docstring(doc_scenario_state: DocScenarioState) -> None:
    """Write the conforming counterpart of the separation violation."""
    _append(
        doc_scenario_state,
        PYTHON_PATH,
        'def read_rows():\n    """Read records.\n\n    More detail.\n    """\n',
    )


@when("the mixed-source tree is checked")
def check_the_tree(
    doc_scenario_state: DocScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the checker once over the tree in JSON mode."""
    _run(doc_scenario_state, monkeypatch, capsys)


@when("the mixed-source tree is checked twice")
def check_the_tree_twice(
    doc_scenario_state: DocScenarioState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the checker twice, recording the first run's code order."""
    _run(doc_scenario_state, monkeypatch, capsys)
    doc_scenario_state["first_codes"] = _codes(doc_scenario_state)
    _run(doc_scenario_state, monkeypatch, capsys)


@then(parsers.parse('DOC001 points to the start of "{text}"'))
def doc001_points_at(
    doc_scenario_state: DocScenarioState,
    text: str,
) -> None:
    """Assert the anchor is the first character of the explanation line."""
    _only_diagnostic(doc_scenario_state, "DOC001")

    assert_with_context(
        _span_bytes(doc_scenario_state, "DOC001") == [text[0].encode()],
        "expected DOC001 to anchor the first character of the "
        f"{text!r} line, got {_span_bytes(doc_scenario_state, 'DOC001')}",
    )


@then(parsers.parse('DOC002 points to the final "{character}" in "{text}"'))
def doc002_points_at(
    doc_scenario_state: DocScenarioState,
    character: str,
    text: str,
) -> None:
    """Assert the anchor is the final visible character of the summary."""
    assert_with_context(
        text.endswith(character),
        f"scenario error: {text!r} does not end with {character!r}",
    )
    _only_diagnostic(doc_scenario_state, "DOC002")

    assert_with_context(
        _span_bytes(doc_scenario_state, "DOC002") == [character.encode()],
        "expected DOC002 to anchor the final character, got "
        f"{_span_bytes(doc_scenario_state, 'DOC002')}",
    )


@then("no automatic fix is offered for DOC002")
def no_fix_is_offered(doc_scenario_state: DocScenarioState) -> None:
    """Assert the diagnostic carries no fix."""
    diagnostic = _only_diagnostic(doc_scenario_state, "DOC002")

    assert_with_context(
        diagnostic["fix"] is None and diagnostic["fix_applicable"] is False,
        f"expected no fix on DOC002, got {diagnostic['fix']!r}",
    )


@then("only the Widget docstring receives DOC003")
def only_widget_receives_doc003(doc_scenario_state: DocScenarioState) -> None:
    """Assert the owner's own name decides which docstring is redundant."""
    diagnostic = _only_diagnostic(doc_scenario_state, "DOC003")
    location = typ.cast("dict[str, int]", diagnostic["location"])
    source = (doc_scenario_state["root"] / PYTHON_PATH).read_text(encoding="utf-8")
    line = source.splitlines()[location["line"] - 1]

    assert_with_context(
        "class Widget" in source.splitlines()[location["line"] - 2],
        f"expected DOC003 on the Widget class, got line {location['line']}: {line!r}",
    )


@then("none of those surfaces receives a documentation rule diagnostic")
def no_unsupported_surface_reports(doc_scenario_state: DocScenarioState) -> None:
    """Assert Markdown and ordinary comments stay outside the surface."""
    reported = _diagnostics(doc_scenario_state)

    assert_with_context(
        reported == [],
        f"expected no documentation diagnostics, got {reported}",
    )
    assert_with_context(
        doc_scenario_state["exit_code"] == 0,
        f"expected exit 0 for a warning-free run, got "
        f"{doc_scenario_state['exit_code']}",
    )


@then("DOC001 and DOC003 are reported but DOC002 is not")
def doc001_and_doc003_only(doc_scenario_state: DocScenarioState) -> None:
    """Assert a disabled rule's findings disappear without its siblings'."""
    codes = _codes(doc_scenario_state)

    assert_with_context(
        "DOC001" in codes and "DOC003" in codes,
        f"expected DOC001 and DOC003, got {codes}",
    )
    assert_with_context(
        "DOC002" not in codes,
        f"expected no DOC002 while it is disabled, got {codes}",
    )


@then("the module comment receives no DOC003")
def module_comment_has_no_doc003(doc_scenario_state: DocScenarioState) -> None:
    """Assert an unnamed module owner is skipped."""
    assert_with_context(
        "DOC003" not in _codes(doc_scenario_state),
        f"expected no DOC003 for a module owner, got {_codes(doc_scenario_state)}",
    )


@then("no DOC001 diagnostic is reported")
def no_doc001(doc_scenario_state: DocScenarioState) -> None:
    """Assert the conforming docstring passes."""
    assert_with_context(
        "DOC001" not in _codes(doc_scenario_state),
        f"expected a blank separator to pass, got {_codes(doc_scenario_state)}",
    )


@then("both runs report the same codes in the same order")
def both_runs_agree(doc_scenario_state: DocScenarioState) -> None:
    """Assert repeated runs are identical and carry all three meanings."""
    second = _codes(doc_scenario_state)

    assert_with_context(
        second == doc_scenario_state["first_codes"],
        f"expected identical runs, got {doc_scenario_state['first_codes']} "
        f"then {second}",
    )
    assert_with_context(
        {"DOC001", "DOC002", "DOC003"} <= set(second),
        f"expected every documentation rule to report, got {second}",
    )
