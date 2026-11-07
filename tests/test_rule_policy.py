"""Truth tables for rule selection, per-file ignores, and suppression.

The policy layer is where a finding is admitted or dropped, so these tests
state its contract directly: precedence between prefixes, glob anchoring, and
the directive state machine. Rule behaviour is exercised elsewhere; here a
single repeated word stands in for "some finding" so a failure points at
policy rather than at a rule.
"""

import pytest
from stilyagi.model.source import SourceSpan
from stilyagi.rules.suppression import expand_prefixes

from tests.support.rule_fixtures import LintSetup, codes_of, spans_of

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

REPEAT = "the the.\n"
TERM_ENABLED: dict[str, dict[str, object]] = {"TERM001": {"terms": ["obviously"]}}
BANNED = "obviously\n"


class TestPrefixExpansion:
    """Prefixes expand against the concrete inventory."""

    def test_all_matches_every_code(self) -> None:
        """``ALL`` is a prefix like any other, but matches everything."""
        assert expand_prefixes(("ALL",), ("MD001", "STY001")) == (
            "MD001",
            "STY001",
        ), "expected ALL to expand to the whole inventory"

    def test_unmatched_prefix_is_a_no_op(self) -> None:
        """An unknown prefix selects nothing rather than raising."""
        assert not expand_prefixes(("NOPE",), ("MD001",)), (
            "expected an unknown prefix to match nothing"
        )

    def test_order_follows_the_inventory(self) -> None:
        """Expansion returns inventory order, not configuration order."""
        assert expand_prefixes(("STY", "MD"), ("MD001", "STY001")) == (
            "MD001",
            "STY001",
        ), "expected expansion to follow inventory order"


class TestSelectionPrecedence:
    """Selection, ignore, and per-file ignores are applied in order."""

    def test_selected_rule_reports(self) -> None:
        """The positive control for the exclusions below."""
        assert codes_of(LintSetup().run(REPEAT)) == ("STY001",), (
            "expected a selected rule to report its finding"
        )

    def test_ignore_wins_over_a_narrower_select(self) -> None:
        """Ignore wins regardless of which prefix is longer."""
        setup = LintSetup(select=("STY001",), ignore=("STY",))

        assert setup.run(REPEAT) == [], (
            "expected a broader ignore to beat a narrower select"
        )

    def test_per_file_glob_excludes_a_matching_path(self) -> None:
        """A glob exclusion applies to the config-relative target path."""
        setup = LintSetup(
            per_file_ignores={"docs/*.md": ("STY",)},
            reported_path="docs/guides/intro.md",
        )

        assert setup.run(REPEAT) == [], (
            "expected a glob exclusion to hide a matching path"
        )

    def test_per_file_glob_does_not_match_another_tree(self) -> None:
        """The exclusion is anchored, not a bare suffix match."""
        setup = LintSetup(
            per_file_ignores={"docs/*.md": ("STY",)},
            reported_path="src/intro.md",
        )

        assert codes_of(setup.run(REPEAT)) == ("STY001",), (
            "expected the anchored glob not to match a sibling tree"
        )

    def test_empty_plugin_list_disables_the_builtin_pack(self) -> None:
        """Selecting rules cannot re-enable a disabled pack."""
        assert LintSetup(plugins=()).run(REPEAT) == [], (
            "expected an empty plugin list to disable the builtin pack"
        )

    def test_ignored_rule_still_validates_its_options(self) -> None:
        """An option error cannot hide behind selection."""
        from stilyagi.config.schema import InvalidConfigError

        setup = LintSetup(select=(), rules={"TERM001": {"terms": ["two words"]}})

        with pytest.raises(InvalidConfigError):
            setup.run(REPEAT)


class TestSuppressionDirectives:
    """Range, file, and inline directives follow the documented state machine."""

    def test_repeated_disable_is_idempotent(self) -> None:
        """A second ``disable`` does not need a second ``enable``."""
        source = (
            "<!-- stilyagi: disable STY -->\n"
            "<!-- stilyagi: disable STY -->\n"
            "the the.\n"
            "<!-- stilyagi: enable STY -->\n"
        )

        assert LintSetup().run(source) == [], (
            "expected a repeated disable to need no second enable"
        )

    def test_an_unmatched_enable_is_a_no_op(self) -> None:
        """An ``enable`` with no open range changes nothing."""
        source = "<!-- stilyagi: enable STY -->\nthe the.\n"

        assert spans_of(LintSetup().run(source)) == ((34, 37),), (
            "expected an unmatched enable to change nothing"
        )

    def test_one_enable_reopens_the_range_for_the_finding_that_follows(self) -> None:
        """A single ``enable`` drops the earlier finding and keeps the later."""
        source = (
            "<!-- stilyagi: disable STY -->\n"
            "the the.\n"
            "<!-- stilyagi: enable STY -->\n"
            "the the.\n"
        )

        assert spans_of(LintSetup().run(source)) == ((74, 77),), (
            "expected the earlier finding suppressed and the later one reported"
        )

    def test_an_unclosed_disable_lasts_to_end_of_file(self) -> None:
        """No ``enable`` means suppression runs to EOF."""
        source = "<!-- stilyagi: disable STY -->\nthe the.\n\nthe the.\n"

        assert LintSetup().run(source) == [], (
            "expected an unclosed disable to last to end of file"
        )

    def test_a_narrower_enable_reopens_one_code(self) -> None:
        """``enable STY001`` re-enables the code inside a disabled ``STY`` range."""
        source = (
            "<!-- stilyagi: disable STY -->\n"
            "<!-- stilyagi: enable STY001 -->\n"
            "the the.\n"
            "<!-- stilyagi: enable STY -->\n"
        )

        assert codes_of(LintSetup().run(source)) == ("STY001",), (
            "expected a narrower enable to reopen only that code"
        )

    def test_file_directive_with_no_codes_covers_all_builtins(self) -> None:
        """An empty code list on ``ignore-file`` means every builtin."""
        source = "<!-- stilyagi: ignore-file -->\nthe the.\nobviously\n"
        setup = LintSetup(rules=TERM_ENABLED)

        assert setup.run(source) == [], (
            "expected an empty ignore-file to cover every builtin"
        )

    def test_ignore_next_consumes_the_next_nonempty_unit(self) -> None:
        """Blank regions are skipped when binding an inline directive."""
        source = "<!-- stilyagi: ignore-next STY001 -->\n\nthe the.\n\nthe the.\n"

        assert spans_of(LintSetup().run(source)) == ((53, 56),), (
            "expected ignore-next to bind the next nonempty unit"
        )

    def test_ignore_next_binds_even_when_the_rule_is_ignored(self) -> None:
        """The consumed unit does not depend on selection."""
        source = "<!-- stilyagi: ignore-next STY001 -->\nthe the.\n\nthe the.\n"
        setup = LintSetup(select=("MD", "TERM"))

        assert setup.run(source) == [], (
            "expected ignore-next to bind even when unselected"
        )

    def test_unselected_ignore_next_binds_only_the_first_unit(self) -> None:
        """Selection is a diagnostics filter, not a suppression input.

        ``STY001`` is outside ``lint.select`` here, so it produces no finding
        and the empty result of a run cannot show what the directive bound.
        The resolved plan can: the directive must still consume the first
        paragraph and leave the second alone.
        """
        source = "<!-- stilyagi: ignore-next STY001 -->\nthe the.\n\nthe the.\n"
        setup = LintSetup(select=("MD", "TERM"))
        policy = setup.policy(source)
        first = source.index(REPEAT)
        second = source.index(REPEAT, first + len(REPEAT))

        assert not policy.is_enabled("STY001"), "the rule must be unselected"
        assert policy.suppressions.suppresses("STY001", SourceSpan(first, first + 3)), (
            "the directive must consume the first paragraph"
        )
        assert not policy.suppressions.suppresses(
            "STY001", SourceSpan(second, second + 3)
        ), "the directive must not reach the second paragraph"

    def test_ignore_next_consumes_a_finding_free_paragraph(self) -> None:
        """A paragraph with nothing to report still consumes the directive."""
        source = (
            "<!-- stilyagi: ignore-next STY001 -->\n\nA quiet paragraph.\n\nthe the.\n"
        )

        assert _reported_words(source) == [b"the"], (
            "expected the quiet paragraph to consume the directive"
        )

    def test_ignore_next_suppresses_the_unit_when_it_reports(self) -> None:
        """The positive control for the finding-free consumer above."""
        source = "<!-- stilyagi: ignore-next STY001 -->\n\nthe the.\n"

        assert _reported_words(source) == [], (
            "expected the reporting paragraph to be suppressed"
        )

    def test_ignore_next_binds_the_first_list_paragraph(self) -> None:
        """A thin list container is skipped; its first paragraph is the unit."""
        source = "<!-- stilyagi: ignore-next STY001 -->\n\n- one\n- the the\n"

        assert _reported_words(source) == [b"the"], (
            "expected the directive to bind the first list paragraph"
        )

    def test_ignore_next_skips_an_empty_list_item(self) -> None:
        """An empty item is not a unit, so the next item consumes nothing."""
        source = "<!-- stilyagi: ignore-next STY001 -->\n\n- \n- the the\n"

        assert _reported_words(source) == [], (
            "expected the empty item to be skipped, not consumed"
        )

    def test_ignore_next_consumes_a_table_cell_and_leaves_a_later_finding(self) -> None:
        """A table cell is a prose unit, so it can consume the directive.

        The header cells are empty, so the first nonempty unit is the first
        body cell. Only the second cell's finding may survive.
        """
        source = (
            "<!-- stilyagi: ignore-next STY001 -->\n\n"
            "|  |  |\n"
            "| --- | --- |\n"
            "| the the | the the |\n"
        )

        assert _reported_words(source) == [b"the"], (
            "expected the first cell to consume the directive and the second to report"
        )

    def test_ignore_next_suppresses_a_reporting_table_cell(self) -> None:
        """The positive control for the table-cell consumer above."""
        source = (
            "<!-- stilyagi: ignore-next STY001 -->\n\n"
            "|  |  |\n"
            "| --- | --- |\n"
            "| the the | quiet |\n"
        )

        assert _reported_words(source) == [], (
            "expected the reporting table cell to be suppressed"
        )

    def test_ignore_next_binds_a_blockquote_paragraph_not_its_child(self) -> None:
        """A nested paragraph stays distinct from the quote it sits inside."""
        source = "<!-- stilyagi: ignore-next STY001 -->\n\n> outer\n>\n> - the the\n"

        assert _reported_words(source) == [b"the"], (
            "expected the quote's own paragraph to consume the directive"
        )

    def test_a_nested_blockquote_paragraph_is_its_own_unit(self) -> None:
        """A directive inside a quote binds only the paragraph that follows it."""
        source = "> outer\n>\n> <!-- stilyagi: ignore-next STY001 -->\n>\n> the the.\n"

        assert _reported_words(source) == [], (
            "expected the nested paragraph to be its own suppression unit"
        )

    @pytest.mark.parametrize("position", ["before", "between", "after"])
    def test_file_ignore_applies_wherever_it_appears(self, position: str) -> None:
        """A file directive covers the document regardless of its position."""
        assert LintSetup().run(_file_ignore_source(position)) == [], (
            f"expected a file directive placed {position} to cover the document"
        )


def _reported_words(source: str) -> list[bytes]:
    """Return the source bytes each finding addresses, in document order."""
    data = source.encode("utf-8")
    return [
        data[diagnostic.span.byte_start : diagnostic.span.byte_end]
        for diagnostic in LintSetup().run(source)
        if diagnostic.span is not None
    ]


_FILE_DIRECTIVE = "<!-- stilyagi: ignore-file STY001 -->\n"
_FINDING_PARAGRAPH = "the the.\n"


def _file_ignore_source(position: str) -> str:
    """Return a two-finding document with the file directive in one position."""
    if position == "before":
        return _FILE_DIRECTIVE + _FINDING_PARAGRAPH + "\n" + _FINDING_PARAGRAPH
    if position == "between":
        return _FINDING_PARAGRAPH + "\n" + _FILE_DIRECTIVE + _FINDING_PARAGRAPH
    return _FINDING_PARAGRAPH + "\n" + _FINDING_PARAGRAPH + "\n" + _FILE_DIRECTIVE
