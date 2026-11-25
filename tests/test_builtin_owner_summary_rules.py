"""Owner-only summary behaviour and the documentation rules' policy boundary.

``DOC003`` compares a summary against the extractor's authoritative owner name.
The policy tests pin the per-rule opt-in that the default ``DOC`` selection
prefix cannot express, and the surface tests prove Markdown and ordinary
comments never receive these codes. ``tests/test_builtin_docstring_rules.py``
holds the separation and punctuation matrix.
"""

import pytest
from stilyagi import diagnostics, model

from tests.support.assertions import assert_with_context
from tests.support.docstring_rule_fixtures import doc_setup
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


def _run(
    source: str | bytes,
    syntax: model.Syntax,
) -> list[diagnostics.Diagnostic]:
    """Run the documentation rules over one source in its own syntax."""
    reported_path = "doc.py" if syntax is model.Syntax.PYTHON_DOCSTRING else "doc.rs"
    return doc_setup(reported_path).run(source, syntax)


def _codes(result: list[diagnostics.Diagnostic]) -> tuple[str, ...]:
    """Return the diagnostic codes in order."""
    return tuple(diagnostic.code for diagnostic in result)


class TestOwnerOnlySummary:
    """``DOC003`` reports a summary that only restates the owner's name."""

    @pytest.mark.parametrize(
        ("source", "syntax"),
        [
            pytest.param(
                'class Widget:\n    """Widget."""\n',
                model.Syntax.PYTHON_DOCSTRING,
                id="python",
            ),
            pytest.param(
                "/// Widget.\npub struct Widget;\n",
                model.Syntax.RUST_DOC_COMMENT,
                id="rust",
            ),
        ],
    )
    def test_a_named_owner_summary_warns(
        self,
        source: str,
        syntax: model.Syntax,
    ) -> None:
        """A class or struct documenting itself by name is redundant."""
        result = _run(source, syntax)

        assert_with_context(
            _codes(result) == ("DOC003",),
            f"expected one DOC003 finding, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(source.encode(), result) == b"W",
            "expected the anchor to be the name's first character",
        )

    def test_only_the_matching_owner_warns(self) -> None:
        """Two classes with the same text differ by their authoritative name."""
        source = 'class Widget:\n    """Widget."""\n\nclass Other:\n    """Widget."""\n'
        result = _python(source)

        assert_with_context(
            _codes(result) == ("DOC003",),
            f"expected only the Widget docstring to report, got {_codes(result)}",
        )
        assert_with_context(
            result[0].line == 2, f"expected the finding on line 2, got {result[0].line}"
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

        assert_with_context(
            _codes(_python(source)) == ("DOC003",),
            f"expected {summary!r} to be reported for a function owner",
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

        assert_with_context(
            _codes(_python(source)) == ("DOC002", "DOC003"),
            f"expected both findings for {summary!r}",
        )

    def test_a_class_owner_may_not_use_call_syntax(self) -> None:
        """``()`` is a function-owner form only."""
        source = 'class Widget:\n    """Widget()"""\n'

        assert_with_context(
            "DOC003" not in _codes(_python(source)),
            "expected call syntax not to match a class owner name",
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

        assert_with_context(
            _codes(_python(source)) == ("DOC003",),
            "expected an underscored function name to match whole",
        )

    def test_a_module_owner_is_skipped(self) -> None:
        """A module has no name a summary could repeat."""
        assert_with_context(
            _python('"""__doc__."""\n') == [],
            "expected an unnamed module owner to be skipped",
        )

    def test_rust_summary_with_content_on_the_same_paragraph_passes(self) -> None:
        """Without a blank line, the paragraph is the summary and says more."""
        source = "/// Widget\n/// stores records.\npub struct Widget;\n"

        assert _rust(source) == [], "expected a two-line paragraph to describe the item"

    def test_rust_repeat_followed_by_a_blank_line_warns(self) -> None:
        """A blank line ends the summary, leaving only the name."""
        source = "/// Widget.\n///\n/// Stores records.\npub struct Widget;\n"

        assert_with_context(
            _codes(_rust(source)) == ("DOC003",),
            "expected the first paragraph to be reported",
        )

    @pytest.mark.parametrize(
        "declaration",
        [
            pytest.param("pub enum Widget {}", id="enum"),
            pytest.param("pub union Widget { a: u8 }", id="union"),
            pytest.param("pub trait Widget {}", id="trait"),
            pytest.param("pub fn Widget() {}", id="function"),
            pytest.param("pub const Widget: u8 = 0;", id="const"),
            pytest.param("pub static Widget: u8 = 0;", id="static"),
            pytest.param("pub type Widget = u8;", id="type"),
            pytest.param("macro_rules! Widget { () => {}; }", id="macro"),
        ],
    )
    def test_rust_named_item_kinds_warn(self, declaration: str) -> None:
        """Every named Rust item kind in the target is checked."""
        source = f"/// Widget.\n{declaration}\n"

        assert_with_context(
            _codes(_rust(source)) == ("DOC003",),
            f"expected {declaration!r} to be checked",
        )

    def test_a_rust_function_accepts_the_call_form(self) -> None:
        """A Rust function owner may name itself with ``()``."""
        source = "/// Widget().\npub fn Widget() {}\n"

        assert_with_context(
            _codes(_rust(source)) == ("DOC003",),
            "expected a Rust function's call form to match",
        )

    def test_an_impl_owner_is_skipped(self) -> None:
        """An impl block documents no named item of its own."""
        source = "/// Widget.\nimpl Widget {}\n"

        assert _rust(source) == [], "expected an impl owner to be skipped"

    def test_doc002_and_doc003_report_independently(self) -> None:
        """One summary may earn both findings, in inventory order."""
        source = 'class Widget:\n    """Widget"""\n'
        result = _python(source)

        assert_with_context(
            _codes(result) == ("DOC002", "DOC003"),
            f"expected both independent findings, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(source.encode(), result) == b"t|W",
            "expected DOC002 on the final character and DOC003 on the name",
        )
