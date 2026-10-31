"""Behavioural tests for the starter-pack builtin rules.

Each rule has a documented span contract, so these tests assert the exact byte
offsets the plan records rather than only the diagnostic count. The negative
controls matter as much as the positives: a rule that reports inside inline
code, across markup, or on a corrupted source span would still "find" the
word, and only an exclusion test can tell the difference.
"""

import pytest
from stilyagi import model
from stilyagi.fixes import Applicability

from tests.support.rule_fixtures import LintSetup, spans_of

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

TERM_ENABLED: dict[str, dict[str, object]] = {
    "TERM001": {"terms": ["obviously", "clearly"]},
}


class TestHeadingDepth:
    """``MD001`` reports structural heading jumps only."""

    def test_reports_a_skipped_level_at_the_heading_node_span(self) -> None:
        """The finding covers the whole heading node, marker included."""
        result = LintSetup().run("# Start\n### Detail\n")

        assert [diagnostic.code for diagnostic in result] == ["MD001"], (
            "expected a skipped level to report MD001"
        )
        assert spans_of(result) == ((8, 18),), (
            "expected the finding to cover the whole second heading"
        )
        diagnostic = result[0]
        assert diagnostic.severity.value == "error", (
            "expected a structural jump to be an error"
        )
        assert diagnostic.fix is not None, (
            "expected the structural finding to carry a fix"
        )
        assert diagnostic.fix.applicability is Applicability.MANUAL, (
            "expected the heading fix to be manual"
        )
        assert diagnostic.fix.edits == (), "expected the manual fix to make no edits"

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("### Deep\n## Two\n# One\n", id="descending"),
            pytest.param("# One\n## Two\n### Three\n", id="consecutive"),
            pytest.param("### Only\n", id="first-heading-any-depth"),
        ],
    )
    def test_does_not_report_legal_sequences(self, source: str) -> None:
        """Only an increase greater than one is a jump."""
        assert LintSetup().run(source) == [], (
            "expected legal heading sequences to report nothing"
        )

    def test_reports_an_empty_heading_as_a_structural_span(self) -> None:
        """A heading with no text still has an uneditable node span."""
        result = LintSetup().run("# Start\n###\n")

        assert spans_of(result) == ((8, 11),), (
            "expected the empty heading to cover its whole node"
        )
        assert result[0].fix is not None, "expected the empty heading to carry a fix"
        assert result[0].fix.edits == (), (
            "expected the empty heading fix to make no edits"
        )

    def test_state_advances_through_a_suppressed_heading(self) -> None:
        """A suppressed jump still becomes the depth the next heading compares to."""
        source = (
            "## Two\n"
            "<!-- stilyagi: disable MD001 -->\n"
            "#### Four\n"
            "<!-- stilyagi: enable MD001 -->\n"
            "##### Five\n"
        )

        assert LintSetup().run(source) == [], (
            "expected the resumed depth not to trigger a jump"
        )


class TestRepeatedWord:
    """``STY001`` matches maximal adjacent runs inside one segment."""

    def test_reports_the_second_token_of_a_pair(self) -> None:
        """The diagnostic points at the repetition, not the first word."""
        result = LintSetup().run("the the.\n")

        assert [diagnostic.code for diagnostic in result] == ["STY001"], (
            "expected a repeated word to report STY001"
        )
        assert spans_of(result) == ((4, 7),), (
            "expected the reported span to cover the second token"
        )
        assert result[0].severity.value == "warning", (
            "expected a repeated word to be a warning"
        )

    def test_unsafe_edit_removes_the_whole_run_suffix(self) -> None:
        """A three-word run leaves one word, not two."""
        result = LintSetup().run("the the the.\n")

        assert spans_of(result) == ((4, 7),), (
            "expected the three-word run to report only its second token"
        )
        fix = result[0].fix
        assert fix is not None, "expected the repetition finding to carry a fix"
        assert fix.applicability is Applicability.UNSAFE, (
            "expected the repeated-word fix to be unsafe"
        )
        assert [(edit.byte_start, edit.byte_end) for edit in fix.edits] == [(3, 11)], (
            "expected the unsafe edit to remove the whole run suffix"
        )

    def test_distinct_runs_produce_disjoint_edits(self) -> None:
        """Each maximal run is one finding with its own edit."""
        result = LintSetup().run("a a b b.\n")

        assert spans_of(result) == ((2, 3), (6, 7)), (
            "expected each maximal run to report its own span"
        )
        edits = [
            (edit.byte_start, edit.byte_end)
            for diagnostic in result
            for edit in (diagnostic.fix.edits if diagnostic.fix else ())
        ]
        assert edits == [(1, 3), (5, 7)], (
            "expected each run's edit to remove only its suffix"
        )

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("The the.\n", id="exact-spelling"),
            pytest.param("the\nthe.\n", id="line-break"),
            pytest.param("*the* the.\n", id="markup-boundary"),
            pytest.param("**the** the.\n", id="strong-boundary"),
            pytest.param("`the the`.\n", id="inline-code"),
            pytest.param("the,the.\n", id="comma-separated"),
        ],
    )
    def test_does_not_join_across_a_boundary(self, source: str) -> None:
        """Matching never crosses spelling, markup, line, or code boundaries."""
        assert LintSetup().run(source) == [], (
            "expected no finding to cross a spelling, markup, or code boundary"
        )

    def test_uses_byte_offsets_for_multibyte_text(self) -> None:
        """Character indices are never mistaken for byte offsets."""
        result = LintSetup().run("é é.\n")

        assert spans_of(result) == ((3, 5),), (
            "expected multibyte text to report byte offsets"
        )

    def test_survives_crlf_line_endings(self) -> None:
        """CRLF bytes do not shift the reported span."""
        result = LintSetup().run(b"the the.\r\n")

        assert spans_of(result) == ((4, 7),), (
            "expected CRLF line endings not to shift the span"
        )


class TestBannedTerm:
    """``TERM001`` is opt-in and matches whole tokens only."""

    def test_reports_nothing_until_terms_are_configured(self) -> None:
        """Selecting the rule without terms is a no-op."""
        assert LintSetup().run("This is obviously wrong.\n") == [], (
            "expected an unconfigured term rule to report nothing"
        )

    def test_reports_a_configured_term_case_insensitively(self) -> None:
        """The default comparison folds case."""
        result = LintSetup(rules=TERM_ENABLED).run("This is Obviously wrong.\n")

        assert [diagnostic.code for diagnostic in result] == ["TERM001"], (
            "expected a folded term match to report TERM001"
        )
        assert spans_of(result) == ((8, 17),), (
            "expected the folded match to cover the whole token"
        )
        assert result[0].severity.value == "error", (
            "expected a banned term to be an error"
        )
        assert result[0].fix is None, "expected a banned term to need no fix"

    def test_exact_case_option_rejects_other_casing(self) -> None:
        """``case_sensitive`` requires the configured spelling."""
        rules: dict[str, dict[str, object]] = {
            "TERM001": {"terms": ["obviously"], "case_sensitive": True}
        }
        result = LintSetup(rules=rules).run("Obviously obviously.\n")

        assert spans_of(result) == ((10, 19),), (
            "expected case_sensitive to match only the configured spelling"
        )

    def test_matches_whole_tokens_only(self) -> None:
        """A configured term never matches inside a longer word."""
        result = LintSetup(rules=TERM_ENABLED).run("unobviously obviously.\n")

        assert spans_of(result) == ((12, 21),), (
            "expected a term not to match inside a longer word"
        )

    def test_ignores_inline_code(self) -> None:
        """Prose matching excludes inline-code segments."""
        result = LintSetup(rules=TERM_ENABLED).run("`obviously` obviously.\n")

        assert spans_of(result) == ((12, 21),), (
            "expected inline code not to be matched as prose"
        )

    @pytest.mark.parametrize(
        "terms",
        [
            pytest.param(["two words"], id="multi-word"),
            pytest.param(["-hyphen"], id="non-alphabetic"),
            pytest.param([""], id="empty"),
        ],
    )
    def test_rejects_invalid_terms_as_configuration_errors(
        self, terms: list[str]
    ) -> None:
        """Malformed options surface through the established config error."""
        from stilyagi.config.schema import InvalidConfigError

        with pytest.raises(InvalidConfigError, match="TERM001"):
            LintSetup(rules={"TERM001": {"terms": terms}}).run("text\n")


class TestRuleOrdering:
    """Diagnostics follow inventory order, whatever a rule found first."""

    def test_reports_md_then_sty_then_term(self) -> None:
        """Structural, then style, then terminology."""
        source = "# Start\n### Detail the the obviously\n"
        result = LintSetup(rules=TERM_ENABLED).run(source)

        assert [diagnostic.code for diagnostic in result] == [
            "MD001",
            "STY001",
            "TERM001",
        ], "expected diagnostics in structural, style, then term order"


class TestSourceVerification:
    """A segment's advertised span must address its own text."""

    @staticmethod
    def _document(text: str, byte_start: int, byte_end: int) -> model.Document:
        """Build a handwritten region whose segment claims a byte span."""
        return model.Document(
            syntax=model.Syntax.MARKDOWN,
            ir={
                "nodes": [],
                "regions": [
                    {
                        "id": "r0",
                        "kind": "paragraph",
                        "syntax": "markdown",
                        "scope": ["markdown", "paragraph"],
                        "attrs": {},
                        "segments": [
                            {
                                "text": text,
                                "node": "n1",
                                "source": {
                                    "byte_start": byte_start,
                                    "byte_end": byte_end,
                                },
                            }
                        ],
                    }
                ],
            },
        )

    def test_a_matching_span_still_reports(self) -> None:
        """The positive control for the verification below."""
        document = self._document("the the", 0, 7)

        result = LintSetup().run_document(document, b"the the")

        assert spans_of(result) == ((4, 7),), (
            "expected a matching span to report at its byte offset"
        )

    @pytest.mark.parametrize(
        ("text", "byte_start", "byte_end", "source"),
        [
            pytest.param("the the", 0, 7, b"XXXXXXX", id="wrong-text"),
            pytest.param("the the", 0, 700, b"the the", id="past-end-of-file"),
            pytest.param("é é", 0, 1, "é é".encode(), id="split-code-point"),
        ],
    )
    def test_a_mismatched_span_produces_no_finding(
        self,
        text: str,
        byte_start: int,
        byte_end: int,
        source: bytes,
    ) -> None:
        """A stale or malformed span is demoted, never trusted."""
        document = self._document(text, byte_start, byte_end)

        assert LintSetup().run_document(document, source) == [], (
            "expected a mismatched span to produce no finding"
        )
