"""Finite behaviour matrix for the summary separation and punctuation rules.

Each test states the source it cares about and asserts the exact byte span the
finding addresses, not merely that a code appeared. The negative controls carry
as much weight as the positives: a rule that ignored its syntax target, its
owner kind, or a Markdown exclusion would still produce a finding, and only a
witness that must stay silent can tell the difference.

``DOC003`` and the policy boundary live in
``tests/test_builtin_owner_summary_rules.py``; the two modules share their
setup through ``tests.support.docstring_rule_fixtures``.
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


def _codes(result: list[diagnostics.Diagnostic]) -> tuple[str, ...]:
    """Return the diagnostic codes in order."""
    return tuple(diagnostic.code for diagnostic in result)


def _assert_anchor(
    source: str | bytes,
    result: list[diagnostics.Diagnostic],
    codes: tuple[str, ...],
    anchor: bytes,
) -> None:
    """Assert the reported codes and the bytes the first finding addresses."""
    encoded = source.encode() if isinstance(source, str) else source

    assert_with_context(
        _codes(result) == codes,
        f"expected {codes}, got {_codes(result)}",
    )
    assert_with_context(
        marked_span(encoded, result[:1]) == anchor,
        f"expected the anchor {anchor!r}, got {marked_span(encoded, result[:1])!r}",
    )


class TestSummarySeparation:
    """``DOC001`` reports a Python summary touching its explanation."""

    @pytest.mark.parametrize(
        "declaration",
        [
            pytest.param('"""Module summary.\nMore detail."""\n', id="module"),
            pytest.param(
                'class Widget:\n    """Stores records.\n    More detail."""\n',
                id="class",
            ),
            pytest.param(
                'def read():\n    """Read records.\n    More detail."""\n',
                id="function",
            ),
        ],
    )
    def test_reports_every_supported_owner_kind(self, declaration: str) -> None:
        """Module, class, and function docstrings are all checked."""
        result = _python(declaration)

        assert_with_context(
            _codes(result) == ("DOC001",),
            f"expected one DOC001 finding, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(declaration.encode(), result) == b"M",
            "expected the finding to anchor the second line's first character",
        )

    def test_a_blank_separator_passes(self) -> None:
        """A summary followed by a blank line needs no finding."""
        source = 'def read():\n    """Read records.\n\n    More detail.\n    """\n'

        assert _python(source) == [], "expected a blank separator to pass"

    def test_a_single_content_line_passes(self) -> None:
        """A one-line docstring has nothing to separate."""
        assert_with_context(
            _python('def read():\n    """Read records."""\n') == [],
            "expected a single content line to pass",
        )

    def test_blank_only_content_is_skipped(self) -> None:
        """Missing documentation is outside this slice."""
        assert_with_context(
            _python('def read():\n    """   """\n') == [],
            "expected blank-only content to be skipped",
        )

    def test_a_literal_escape_does_not_split_a_line(self) -> None:
        r"""A two-character ``\n`` escape is text, not a physical line break."""
        source = 'def read():\n    """Read records.\\nMore detail."""\n'

        assert_with_context(
            _python(source) == [],
            "expected a literal escape not to create a second content line",
        )

    def test_crlf_is_a_single_line_terminator(self) -> None:
        """The CR of a CR-LF pair belongs to the terminator."""
        source = b'def read():\r\n    """Read records.\r\n    More detail."""\r\n'
        result = _python(source)

        assert_with_context(
            _codes(result) == ("DOC001",),
            f"expected a CR-LF docstring to report DOC001, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(source, result) == b"M",
            "expected the anchor to be the second line's first character",
        )

    def test_a_unicode_first_character_spans_its_whole_bytes(self) -> None:
        """A multibyte anchor character is reported as one complete character."""
        source = 'def read():\n    """Read records.\n    élan continues.\n    """\n'
        result = _python(source)

        assert_with_context(
            _codes(result) == ("DOC001",),
            f"expected one DOC001 finding, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(source.encode(), result) == "é".encode(),
            "expected the anchor to cover the whole multibyte character",
        )
        assert result[0].span is not None, "expected the finding to carry a span"
        assert_with_context(
            result[0].span.byte_end - result[0].span.byte_start == 2,
            "expected a two-byte UTF-8 anchor",
        )


class TestSummaryPunctuation:
    """``DOC002`` reports a plain summary with no terminal punctuation."""

    def test_python_summary_line_is_checked(self) -> None:
        """The Python candidate is the first nonblank line."""
        source = 'def read():\n    """Read records"""\n'
        result = _python(source)

        _assert_anchor(source, result, ("DOC002",), b"s")

    @pytest.mark.parametrize("terminal", [".", "!", "?"])
    def test_accepts_each_terminal_character(self, terminal: str) -> None:
        """All three accepted terminators pass."""
        source = f'def read():\n    """Read records{terminal}"""\n'

        assert _python(source) == [], f"expected {terminal!r} to be accepted"

    def test_a_python_multi_line_summary_is_the_first_line_only(self) -> None:
        """A first line without punctuation reports, though later lines have it."""
        source = 'def read():\n    """Read records\n    More detail."""\n'
        result = _python(source)

        assert_with_context(
            _codes(result) == ("DOC001", "DOC002"),
            f"expected separation and punctuation findings, got {_codes(result)}",
        )
        punctuation = [item for item in result if item.code == "DOC002"]
        assert_with_context(
            marked_span(source.encode(), punctuation) == b"s",
            "expected the DOC002 anchor to be the final 's' of the first line",
        )

    @pytest.mark.parametrize(
        ("summary", "expected"),
        [
            pytest.param("Read records. ", (), id="terminal-before-space"),
            pytest.param("Read records ", ("DOC002",), id="trailing-space"),
        ],
    )
    def test_trailing_whitespace_is_trimmed_before_the_terminal_check(
        self,
        summary: str,
        expected: tuple[str, ...],
    ) -> None:
        """Only the trimmed summary's final character decides the finding."""
        source = f'def read():\n    """{summary}"""\n'

        assert_with_context(
            _codes(_python(source)) == expected,
            f"expected {expected} for {summary!r}, got {_codes(_python(source))}",
        )

    def test_leading_blank_lines_are_skipped(self) -> None:
        """The first content line is the summary even after a blank line."""
        source = 'def read():\n    """\n    Read records.\n    More detail.\n    """\n'
        result = _python(source)

        _assert_anchor(source, result, ("DOC001",), b"M")

    def test_rust_line_comment_anchor_is_source_backed(self) -> None:
        """A Rust summary anchors on the final source byte of the paragraph."""
        source = "/// Read records\npub fn read() {}\n"
        result = _rust(source)

        _assert_anchor(source, result, ("DOC002",), b"s")
        assert result[0].line == 1, "expected the finding on the comment's line"
        assert result[0].column == 16, f"expected column 16, got {result[0].column}"

    def test_rust_wrapped_paragraph_uses_its_final_character(self) -> None:
        """Consecutive comment lines form one paragraph."""
        source = "/// Read records\n/// and continue.\npub fn read() {}\n"

        assert _rust(source) == [], "expected a wrapped paragraph ending in '.' to pass"

    def test_rust_wrapped_paragraph_anchors_its_final_character(self) -> None:
        """The anchor maps through the second line's own source segment."""
        source = "/// Read records\n/// and continue\npub fn read() {}\n"
        result = _rust(source)

        _assert_anchor(source, result, ("DOC002",), b"e")
        assert_with_context(
            result[0].line == 2,
            f"expected the finding on the second comment line, got {result[0].line}",
        )

    def test_rust_summary_immediately_followed_by_a_heading_is_skipped(self) -> None:
        """A structural line makes the candidate unsupported, not reported."""
        source = "/// Summary without punctuation\n/// # Heading\npub fn read() {}\n"

        assert_with_context(
            _rust(source) == [],
            "expected a summary followed by a heading to be skipped",
        )

    @pytest.mark.parametrize(
        "line",
        [
            pytest.param("# Heading", id="heading"),
            pytest.param("> quoted", id="block-quote"),
            pytest.param("- item", id="dash-list"),
            pytest.param("+ item", id="plus-list"),
            pytest.param("* item", id="star-list"),
            pytest.param("1. step", id="ordered-dot"),
            pytest.param("2) step", id="ordered-paren"),
            pytest.param("```", id="backtick-fence"),
            pytest.param("~~~", id="tilde-fence"),
            pytest.param(">>> read()", id="doctest-prompt"),
            pytest.param("---", id="dash-break"),
            pytest.param("___", id="underscore-break"),
            pytest.param("***", id="star-break"),
            pytest.param("===", id="equals-break"),
        ],
    )
    def test_structural_line_starts_are_skipped(self, line: str) -> None:
        """A recognized Markdown structure marker suppresses the check."""
        source = f"/// Read records\n///   {line}\npub fn read() {{}}\n"

        assert _rust(source) == [], f"expected {line!r} to be skipped"

    @pytest.mark.parametrize(
        "summary",
        [
            pytest.param("Read `records`", id="backtick"),
            pytest.param("Read \\records", id="backslash"),
            pytest.param("Read [records]", id="brackets"),
            pytest.param("Read <records>", id="angle-brackets"),
            pytest.param("Read *records*", id="emphasis"),
            pytest.param("Read _records_", id="underscore-emphasis"),
            pytest.param('Read "records"', id="double-quote"),
        ],
    )
    def test_markup_candidates_are_skipped(self, summary: str) -> None:
        """A candidate this slice cannot judge is skipped, not reported."""
        source = f'def read():\n    """{summary}"""\n'

        assert _python(source) == [], f"expected {summary!r} to be skipped"

    def test_a_decorated_block_comment_is_skipped(self) -> None:
        """Decorative asterisks are not stripped or reparsed."""
        source = "/**\n * Read records\n */\npub fn read() {}\n"

        assert _rust(source) == [], "expected a decorative block comment to be skipped"

    def test_a_plain_block_comment_is_checked(self) -> None:
        """A block comment without decorative prefixes is ordinary prose."""
        source = "/** Read records */\npub struct S;\n"
        result = _rust(source)

        assert_with_context(
            _codes(result) == ("DOC002",),
            f"expected a plain block comment to be checked, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(source.encode(), result) == b"s",
            "expected the anchor to be the final 's' of 'records'",
        )

    def test_an_empty_summary_is_skipped(self) -> None:
        """A blank-only region produces no punctuation finding."""
        assert_with_context(
            _rust("//!\n\npub fn read() {}\n") == [],
            "expected an empty documentation comment to be skipped",
        )

    def test_a_unicode_terminal_character_spans_its_bytes(self) -> None:
        """The final character of a Unicode summary is one complete character."""
        source = "/// Résumé\npub fn read() {}\n"
        result = _rust(source)

        assert_with_context(
            _codes(result) == ("DOC002",),
            f"expected one DOC002 finding, got {_codes(result)}",
        )
        assert_with_context(
            marked_span(source.encode(), result) == "é".encode(),
            "expected the anchor to cover the final multibyte character",
        )

    def test_no_unicode_normalization_is_applied(self) -> None:
        """Composed and decomposed spellings keep their own byte widths."""
        composed = "/// Caff\u00e8\npub fn read() {}\n"
        decomposed = "/// Caffe\u0300\npub fn read() {}\n"

        composed_result = _rust(composed)
        decomposed_result = _rust(decomposed)

        assert_with_context(
            _codes(composed_result) == ("DOC002",),
            "expected the composed summary to be reported",
        )
        assert_with_context(
            _codes(decomposed_result) == ("DOC002",),
            "expected the decomposed summary to be reported",
        )
        assert_with_context(
            marked_span(composed.encode(), composed_result) == b"\xc3\xa8",
            "expected the composed anchor to be one two-byte character",
        )
        assert_with_context(
            marked_span(decomposed.encode(), decomposed_result) == b"\xcc\x80",
            "expected the decomposed anchor to be the combining mark alone",
        )
