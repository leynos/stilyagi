"""Anchor and coverage edge cases for the documentation-summary rules.

Real extraction never produces these shapes, but the rules must stay silent
rather than relocate a finding when one appears: an anchor inside a synthetic
separator, a region outside the documented kinds, or an unnamed owner. Each
case drives a public hook with a handwritten projected region, so the guard
that omits the finding is exercised through the code a rule actually runs.
"""

import typing as typ

import pytest
from stilyagi import diagnostics, model
from stilyagi.config.rules import DocRuleConfig
from stilyagi.model.region import RegionOwner, RegionSegment, RegionView
from stilyagi.model.source import SourceSpan
from stilyagi.rules.base import RuleContext
from stilyagi.rules.builtin import documentation
from stilyagi.rules.builtin.summary import SummarySource, starts_with_markup

if typ.TYPE_CHECKING:
    import collections.abc as cabc

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

#: One docstring text with two content lines and a synthetic separator.
_TWO_LINES = "Read records\nMore detail."


def _context(region: RegionView) -> RuleContext[DocRuleConfig]:
    """Return an enabled context carrying only ``region``."""
    return RuleContext(
        rule_config=DocRuleConfig(enabled=True),
        document=model.Document(syntax=model.Syntax.PYTHON_DOCSTRING),
        source_bytes=b"",
        reported_path="doc.py",
        regions=(region,),
    )


def _synthetic_region(
    *,
    owner: RegionOwner | None = None,
    kind: str = "python_docstring",
) -> RegionView:
    """Return a region whose whole text has no source backing."""
    return RegionView(
        "r0",
        kind,
        "python",
        ("python", "docstring"),
        {},
        (RegionSegment(None, _TWO_LINES, synthetic_reason="softbreak_space"),),
        owner=owner,
    )


def _region_with(
    *segments: RegionSegment,
    owner: RegionOwner | None = None,
) -> RegionView:
    """Return a python_docstring region built from explicit segments."""
    return RegionView(
        "r0",
        "python_docstring",
        "python",
        ("python", "docstring"),
        {},
        segments,
        owner=owner,
    )


class TestUnmappableAnchors:
    """A rule omits a finding whose anchor has no source backing."""

    @pytest.mark.parametrize(
        ("check", "segments"),
        [
            pytest.param(
                documentation.check_summary_separation,
                (
                    RegionSegment(SourceSpan(0, 13), "Read records."),
                    RegionSegment(None, "\n", synthetic_reason="softbreak_space"),
                    RegionSegment(
                        None, "More detail.", synthetic_reason="decoded_text"
                    ),
                ),
                id="DOC001-second-line",
            ),
            pytest.param(
                documentation.check_summary_punctuation,
                (
                    RegionSegment(SourceSpan(0, 12), "Read records"),
                    RegionSegment(None, "x", synthetic_reason="decoded_text"),
                ),
                id="DOC002-final-character",
            ),
        ],
    )
    def test_a_summary_rule_omits_a_synthetic_anchor(
        self,
        check: cabc.Callable[
            [RuleContext[DocRuleConfig]], tuple[diagnostics.Diagnostic, ...]
        ],
        segments: tuple[RegionSegment, ...],
    ) -> None:
        """A rule whose anchor has no source backing stays silent."""
        region = _region_with(*segments, owner=RegionOwner("class", "Widget"))

        assert not check(_context(region)), "expected no finding for a synthetic anchor"

    def test_owner_summary_omits_a_synthetic_anchor(self) -> None:
        """DOC003 reports nothing when the name's first character is synthetic."""
        region = _region_with(
            RegionSegment(None, "Widget", synthetic_reason="decoded_text"),
            owner=RegionOwner("class", "Widget"),
        )

        result = documentation.check_owner_summary(_context(region))

        assert not result, "expected no finding for a synthetic anchor"


class TestUnsupportedShapes:
    """Shapes outside the declared targets produce no finding."""

    def test_an_ownerless_region_is_skipped_by_the_owner_rule(self) -> None:
        """DOC003 needs a name, so an absent owner is skipped."""
        result = documentation.check_owner_summary(_context(_synthetic_region()))

        assert not result, "expected an ownerless region to be skipped"

    def test_a_region_outside_the_documented_kinds_is_skipped(self) -> None:
        """A region kind with no summary policy yields no candidate lines."""
        region = _synthetic_region(owner=RegionOwner("class", "Widget"), kind="heading")

        result = documentation.check_summary_punctuation(_context(region))

        assert not result, "expected a non-documentation kind to be skipped"

    def test_the_opt_in_gate_precedes_every_selector(self) -> None:
        """A disabled rule never reaches the finding selector."""
        disabled = RuleContext(
            rule_config=DocRuleConfig(),
            document=model.Document(syntax=model.Syntax.PYTHON_DOCSTRING),
            source_bytes=b"",
            reported_path="doc.py",
            regions=(_synthetic_region(owner=RegionOwner("class", "Widget")),),
        )

        assert not documentation.check_owner_summary(disabled), (
            "expected a disabled rule to report nothing"
        )


class TestSummarySourceEdges:
    """The analysis helper refuses inputs it cannot map."""

    def test_an_out_of_range_anchor_is_absent(self) -> None:
        """An index past the reconstructed text has no span."""
        source = SummarySource.of(_synthetic_region())

        assert source.anchor(len(source.text)) is None, (
            "expected an out-of-range index to map to no span"
        )

    def test_an_empty_trimmed_range_is_absent(self) -> None:
        """A range with no lines trims to an empty candidate."""
        source = SummarySource.of(_synthetic_region())

        assert source.trimmed(()) == ("", -1), (
            "expected an empty line range to trim to empty text"
        )

    def test_a_blank_line_starts_no_markup(self) -> None:
        """Whitespace-only text is not a structural line."""
        assert not starts_with_markup("   "), "expected a blank line to start no markup"
