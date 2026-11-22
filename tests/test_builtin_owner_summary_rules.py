"""Owner-only summary behaviour and the documentation rules' policy boundary.

``DOC003`` compares a summary against the extractor's authoritative owner name.
The policy tests pin the per-rule opt-in that the default ``DOC`` selection
prefix cannot express, and the surface tests prove Markdown and ordinary
comments never receive these codes. ``tests/test_builtin_docstring_rules.py``
holds the separation and punctuation matrix.
"""

import pytest
from stilyagi import config, diagnostics, model
from stilyagi.config.rules import DocRuleConfig

from tests.support.docstring_rule_fixtures import ALL_ENABLED, doc_setup
from tests.support.rule_fixtures import LintSetup, marked_span

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")


def _python(
    source: str | bytes,
    setup: LintSetup | None = None,
) -> list[diagnostics.Diagnostic]:
    """Run the documentation rules over a Python source."""
    return (setup or doc_setup()).run(source, model.Syntax.PYTHON_DOCSTRING)


def _rust(
    source: str | bytes,
    setup: LintSetup | None = None,
) -> list[diagnostics.Diagnostic]:
    """Run the documentation rules over a Rust source."""
    return (setup or doc_setup("doc.rs")).run(source, model.Syntax.RUST_DOC_COMMENT)


def _codes(result: list[diagnostics.Diagnostic]) -> tuple[str, ...]:
    """Return the diagnostic codes in order."""
    return tuple(diagnostic.code for diagnostic in result)


class TestOwnerOnlySummary:
    """``DOC003`` reports a summary that only restates the owner's name."""

    def test_a_class_named_summary_warns(self) -> None:
        """A class documenting itself by name is redundant."""
        source = 'class Widget:\n    """Widget."""\n'
        result = _python(source)

        assert _codes(result) == ("DOC003",), (
            f"expected one DOC003 finding, got {_codes(result)}"
        )
        assert marked_span(source.encode(), result) == b"W", (
            "expected the anchor to be the name's first character"
        )

    def test_only_the_matching_owner_warns(self) -> None:
        """Two classes with the same text differ by their authoritative name."""
        source = 'class Widget:\n    """Widget."""\n\nclass Other:\n    """Widget."""\n'
        result = _python(source)

        assert _codes(result) == ("DOC003",), (
            f"expected only the Widget docstring to report, got {_codes(result)}"
        )
        assert result[0].line == 2, (
            f"expected the finding on line 2, got {result[0].line}"
        )

    @pytest.mark.parametrize(
        "summary",
        [
            pytest.param("read.", id="period"),
            pytest.param("read().", id="call-period"),
        ],
    )
    def test_function_owner_forms_warn(self, summary: str) -> None:
        """A function summary may name itself with ``()`` and one period."""
        source = f'def read():\n    """{summary}"""\n'

        assert _codes(_python(source)) == ("DOC003",), (
            f"expected {summary!r} to be reported for a function owner"
        )

    @pytest.mark.parametrize(
        "summary",
        [
            pytest.param("read", id="bare"),
            pytest.param("read()", id="call"),
        ],
    )
    def test_unpunctuated_function_forms_report_both_rules(self, summary: str) -> None:
        """DOC002 and DOC003 are independent findings on one summary."""
        source = f'def read():\n    """{summary}"""\n'

        assert _codes(_python(source)) == ("DOC002", "DOC003"), (
            f"expected both findings for {summary!r}"
        )

    def test_a_class_owner_may_not_use_call_syntax(self) -> None:
        """``()`` is a function-owner form only."""
        source = 'class Widget:\n    """Widget()"""\n'

        assert "DOC003" not in _codes(_python(source)), (
            "expected call syntax not to match a class owner name"
        )

    def test_content_beyond_the_name_passes(self) -> None:
        """A summary that says something about the owner is not redundant."""
        source = 'class Widget:\n    """Widget stores records."""\n'

        assert _python(source) == [], "expected a descriptive summary to pass"

    def test_matching_is_case_sensitive(self) -> None:
        """A different spelling is content, not a repeat."""
        source = 'class Widget:\n    """widget."""\n'

        assert _python(source) == [], "expected case-sensitive matching"

    def test_an_underscored_owner_name_is_matched_whole(self) -> None:
        """Underscores are ordinary name characters, not token boundaries."""
        source = 'def read_rows():\n    """read_rows."""\n'

        assert _codes(_python(source)) == ("DOC003",), (
            "expected an underscored function name to match whole"
        )

    def test_a_module_owner_is_skipped(self) -> None:
        """A module has no name a summary could repeat."""
        assert _python('"""__doc__."""\n') == [], (
            "expected an unnamed module owner to be skipped"
        )

    def test_rust_named_struct_warns(self) -> None:
        """A named Rust item's doc comment is checked."""
        source = "/// Widget.\npub struct Widget;\n"
        result = _rust(source)

        assert _codes(result) == ("DOC003",), (
            f"expected one DOC003 finding, got {_codes(result)}"
        )
        assert marked_span(source.encode(), result) == b"W", (
            "expected the anchor to be the name's first character"
        )

    def test_rust_summary_with_content_on_the_same_paragraph_passes(self) -> None:
        """Without a blank line, the paragraph is the summary and says more."""
        source = "/// Widget\n/// stores records.\npub struct Widget;\n"

        assert _rust(source) == [], "expected a two-line paragraph to describe the item"

    def test_rust_repeat_followed_by_a_blank_line_warns(self) -> None:
        """A blank line ends the summary, leaving only the name."""
        source = "/// Widget.\n///\n/// Stores records.\npub struct Widget;\n"

        assert _codes(_rust(source)) == ("DOC003",), (
            "expected the first paragraph to be reported"
        )

    @pytest.mark.parametrize(
        "declaration",
        [
            pytest.param("pub enum Widget {}", id="enum"),
            pytest.param("pub union Widget { a: u8 }", id="union"),
            pytest.param("pub trait Widget {}", id="trait"),
            pytest.param("pub const Widget: u8 = 0;", id="const"),
            pytest.param("pub static Widget: u8 = 0;", id="static"),
            pytest.param("pub type Widget = u8;", id="type"),
            pytest.param("macro_rules! Widget { () => {}; }", id="macro"),
        ],
    )
    def test_rust_named_item_kinds_warn(self, declaration: str) -> None:
        """Every named Rust item kind in the target is checked."""
        source = f"/// Widget.\n{declaration}\n"

        assert _codes(_rust(source)) == ("DOC003",), (
            f"expected {declaration!r} to be checked"
        )

    def test_an_impl_owner_is_skipped(self) -> None:
        """An impl block documents no named item of its own."""
        source = "/// Widget.\nimpl Widget {}\n"

        assert _rust(source) == [], "expected an impl owner to be skipped"

    def test_doc002_and_doc003_report_independently(self) -> None:
        """One summary may earn both findings, in inventory order."""
        source = 'class Widget:\n    """Widget"""\n'
        result = _python(source)

        assert _codes(result) == ("DOC002", "DOC003"), (
            f"expected both independent findings, got {_codes(result)}"
        )
        assert marked_span(source.encode(), result) == b"t|W", (
            "expected DOC002 on the final character and DOC003 on the name"
        )


class TestOptIn:
    """``DOC`` selection is not opt-in; the per-rule flag is."""

    def test_default_prefix_without_config_reports_nothing(self) -> None:
        """Selection alone must not enable these rules."""
        setup = LintSetup(select=("DOC",), reported_path="doc.py")
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], (
            "expected absent per-rule opt-in to keep the rules inert"
        )

    def test_explicit_false_opt_in_reports_nothing(self) -> None:
        """An explicit ``enabled = false`` is still inert."""
        setup = LintSetup(
            select=("DOC",),
            rules={code: {"enabled": False} for code in ALL_ENABLED},
            reported_path="doc.py",
        )
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], (
            "expected explicit false opt-in to keep the rules inert"
        )

    def test_an_unselected_rule_does_not_run(self) -> None:
        """Opt-in does not override shared selection."""
        setup = LintSetup(select=(), rules=ALL_ENABLED, reported_path="doc.py")
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], "expected an unselected rule not to run"

    def test_ignore_removes_an_enabled_rule(self) -> None:
        """Shared ignore precedence still applies."""
        setup = LintSetup(
            select=("DOC",), ignore=("DOC",), rules=ALL_ENABLED, reported_path="doc.py"
        )
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], "expected lint.ignore to win"

    def test_a_per_file_ignore_removes_an_enabled_rule(self) -> None:
        """Shared per-file globs still apply."""
        setup = LintSetup(
            select=("DOC",),
            per_file_ignores={"*.py": ("DOC",)},
            rules=ALL_ENABLED,
            reported_path="doc.py",
        )
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], "expected the per-file glob to win"

    def test_disabling_the_builtin_pack_removes_every_rule(self) -> None:
        """The plugin gate precedes per-rule opt-in."""
        setup = LintSetup(
            select=("DOC",), plugins=(), rules=ALL_ENABLED, reported_path="doc.py"
        )
        source = 'class Widget:\n    """Widget"""\n'

        assert _python(source, setup) == [], "expected the plugin gate to win"

    def test_a_malformed_flag_is_rejected_even_when_unselected(self) -> None:
        """An option error cannot hide behind selection."""
        setup = LintSetup(
            select=(),
            rules={"DOC001": {"enabled": "yes"}},
            reported_path="doc.py",
        )

        with pytest.raises(config.InvalidConfigError, match=r"rule\.DOC001\.enabled"):
            _python('def read():\n    """Read."""\n', setup)

    def test_an_unknown_option_is_rejected(self) -> None:
        """A misspelled option cannot leave the rule silently inert."""
        setup = LintSetup(
            select=("DOC",),
            rules={"DOC002": {"enable": True}},
            reported_path="doc.py",
        )

        with pytest.raises(config.InvalidConfigError, match=r"rule\.DOC002\.enable"):
            _python('def read():\n    """Read."""\n', setup)

    def test_the_config_record_defaults_to_disabled(self) -> None:
        """The frozen record documents the opt-in default."""
        assert DocRuleConfig().enabled is False, (
            "expected the documentation rule config to default to disabled"
        )


class TestSurfaceExclusions:
    """Markdown and ordinary comments never receive these codes."""

    def test_markdown_regions_are_not_checked(self) -> None:
        """A Markdown heading or paragraph is outside every rule target."""
        setup = LintSetup(select=("DOC",), rules=ALL_ENABLED, reported_path="doc.md")
        source = "# Widget\n\nRead records\n"

        assert setup.run(source) == [], (
            "expected a Markdown document to receive no documentation rule"
        )

    def test_an_ordinary_python_comment_is_not_checked(self) -> None:
        """Only docstrings are extracted as documentation regions."""
        source = "# Read records\ndef read():\n    return 1\n"

        assert _python(source) == [], "expected a plain comment to be ignored"

    def test_a_non_docstring_python_string_is_not_checked(self) -> None:
        """A string that is not the first statement is not a docstring."""
        source = 'value = """Read records"""\n'

        assert _python(source) == [], "expected a non-docstring string to be ignored"

    def test_an_ordinary_rust_comment_is_not_checked(self) -> None:
        """Only ``///`` and ``//!`` documentation comments are regions."""
        source = "// Read records\npub fn read() {}\n"

        assert _rust(source) == [], "expected a plain Rust comment to be ignored"


class TestDeterminism:
    """Repeated runs produce identical ordered findings."""

    def test_repeated_runs_agree(self) -> None:
        """The same source yields the same ordered diagnostics."""
        source = (
            'class Widget:\n    """Widget"""\n\n'
            'def read():\n    """Read records.\n    More detail.\n    """\n'
        )

        first = _python(source)
        second = _python(source)

        assert first == second, "expected repeated runs to agree exactly"

    def test_each_rule_can_be_enabled_independently(self) -> None:
        """Enabling one code does not activate its siblings."""
        setup = LintSetup(
            select=("DOC",),
            rules={"DOC002": {"enabled": True}},
            reported_path="doc.py",
        )
        source = 'class Widget:\n    """Widget"""\n'

        result = _python(source, setup)

        assert _codes(result) == ("DOC002",), (
            f"expected only the enabled rule to report, got {_codes(result)}"
        )
