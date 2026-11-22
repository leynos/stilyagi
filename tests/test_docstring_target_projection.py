"""Targeting and owner-projection tests for documentation rules.

The 3.2.2 rules read Python docstrings and Rust documentation comments rather
than Markdown, so the rule-facing projection has to expose each region's
owner and a target has to name more than one syntax. These tests pin that
boundary against real extracted documents, because a handwritten IR fixture
would prove only that the Python reader agrees with itself.

The negative controls matter as much as the positives: a target that ignored
its syntax list or its owner kinds would still "find" a region, and only an
exclusion test can tell the difference.
"""

import pytest
from stilyagi import engine, model
from stilyagi.engine import rule_projection, rule_view
from stilyagi.model.region import RegionOwner, RegionView
from stilyagi.rules.base import RegionTarget

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")

_PYTHON_SOURCE = '''"""Module summary.

More detail.
"""


class Widget:
    """Widget."""


def reader():
    """Read records."""
'''

_RUST_SOURCE = """//! Module docs.

/// Widget.
pub struct Widget;

/// Reads records.
pub fn reader() {}
"""


def _regions(source: str, syntax: model.Syntax) -> tuple[RegionView, ...]:
    """Extract ``source`` and return its projected regions."""
    document = engine.extract_document(source, syntax)
    return rule_view.project(document, source_bytes=source.encode("utf-8")).regions


def _ownerless(kind: str, syntax: str) -> RegionView:
    """Return one projected region with no owner metadata."""
    return RegionView("r0", kind, syntax, (syntax,), {}, ())


class TestOwnerProjection:
    """The projection carries the extractor's owner metadata verbatim."""

    def test_python_docstrings_project_their_owner(self) -> None:
        """Module, class, and function owners survive with their names."""
        owners = [
            (region.owner.kind, region.owner.name)
            for region in _regions(_PYTHON_SOURCE, model.Syntax.PYTHON_DOCSTRING)
            if region.owner is not None
        ]

        assert owners == [
            ("module", None),
            ("class", "Widget"),
            ("function", "reader"),
        ], f"unexpected Python owner projection: {owners}"

    def test_rust_doc_comments_project_their_owner(self) -> None:
        """A doc comment on a named item records its kind and name."""
        owners = [
            (region.owner.kind, region.owner.name)
            for region in _regions(_RUST_SOURCE, model.Syntax.RUST_DOC_COMMENT)
            if region.owner is not None
        ]

        assert owners == [
            ("module", None),
            ("struct", "Widget"),
            ("function", "reader"),
        ], f"unexpected Rust owner projection: {owners}"

    def test_markdown_regions_have_no_owner(self) -> None:
        """A Markdown region never invents owner metadata."""
        regions = _regions("# Title\n\nBody.\n", model.Syntax.MARKDOWN)

        assert regions, "expected the Markdown source to project regions"
        assert [region.owner for region in regions] == [None] * len(regions), (
            "expected every Markdown region to project no owner"
        )

    def test_malformed_owner_is_counted_and_the_region_survives(self) -> None:
        """An unusable owner field is reported without discarding the text."""
        document = model.Document(
            syntax=model.Syntax.PYTHON_DOCSTRING,
            ir={
                "regions": [
                    {
                        "id": "r1",
                        "kind": "python_docstring",
                        "syntax": "python",
                        "owner": {"kind": 7},
                        "segments": [{"text": "Doc."}],
                    }
                ]
            },
        )

        view = rule_projection.project(document)

        assert [region.owner for region in view.regions] == [None], (
            "expected an unusable owner to project as absent"
        )
        assert view.anomaly_counts == (("malformed_region", 1),), (
            f"expected one malformed_region recovery, got {view.anomaly_counts}"
        )


class TestSyntaxTargeting:
    """A target claims only the syntaxes it names."""

    def test_default_target_stays_markdown_only(self) -> None:
        """The default syntax list keeps existing Markdown rules unchanged."""
        heading = RegionView("r0", "heading", "markdown", (), {"depth": 1}, ())

        assert RegionTarget(kinds=("heading",)).matches_region(heading), (
            "expected the default target to claim a Markdown heading"
        )
        assert not RegionTarget(kinds=("heading",)).matches_region(
            _ownerless("heading", "python")
        ), "expected the default target to refuse a Python region"

    def test_a_target_can_name_several_syntaxes(self) -> None:
        """A documentation target reads both docstring syntaxes."""
        target = RegionTarget(
            kinds=("python_docstring", "rust_doc_comment"),
            syntaxes=("python", "rust"),
        )
        regions = (
            *_regions(_PYTHON_SOURCE, model.Syntax.PYTHON_DOCSTRING),
            *_regions(_RUST_SOURCE, model.Syntax.RUST_DOC_COMMENT),
        )

        claimed = [region.syntax for region in target_filter(target, regions)]

        assert sorted(set(claimed)) == ["python", "rust"], (
            f"expected both syntaxes to be claimed, got {claimed}"
        )

    def test_markdown_is_not_claimed_by_a_documentation_target(self) -> None:
        """A documentation target leaves Markdown headings alone."""
        target = RegionTarget(
            kinds=("python_docstring", "rust_doc_comment"),
            syntaxes=("python", "rust"),
        )
        markdown = _regions("# Title\n\nBody.\n", model.Syntax.MARKDOWN)

        claimed = target_filter(target, markdown)

        assert not claimed, (
            f"expected a documentation target to claim no Markdown region: {claimed}"
        )


class TestOwnerKindTargeting:
    """An owner-kind requirement is absent-tolerant only when it is empty."""

    @staticmethod
    def _docstring(owner: RegionOwner | None) -> tuple[RegionView, ...]:
        """Return one python_docstring region carrying ``owner``."""
        return (
            RegionView(
                "r0",
                "python_docstring",
                "python",
                ("python", "docstring"),
                {},
                (),
                owner=owner,
            ),
        )

    def test_empty_owner_kinds_accept_absent_owner(self) -> None:
        """No declared kind means every owner state passes."""
        target = RegionTarget(
            kinds=("python_docstring",),
            syntaxes=("python",),
        )

        assert target_filter(target, self._docstring(None)), (
            "expected an ownerless region to satisfy an unrestricted target"
        )

    def test_a_declared_owner_kind_requires_a_present_owner(self) -> None:
        """A nonempty kind list refuses a region with no owner."""
        target = RegionTarget(
            kinds=("python_docstring",),
            syntaxes=("python",),
            owner_kinds=("class", "function"),
        )

        assert not target_filter(target, self._docstring(None)), (
            "expected an ownerless region to fail a kind-restricted target"
        )

    def test_a_matching_owner_kind_satisfies_the_target(self) -> None:
        """A declared kind that matches the region's owner is claimed."""
        target = RegionTarget(
            kinds=("python_docstring",),
            syntaxes=("python",),
            owner_kinds=("class", "function"),
        )

        assert target_filter(target, self._docstring(RegionOwner("class", "Widget"))), (
            "expected a matching owner kind to satisfy the target"
        )
        assert not target_filter(target, self._docstring(RegionOwner("module"))), (
            "expected a nonmatching owner kind to be refused"
        )


def target_filter(
    target: RegionTarget,
    regions: tuple[RegionView, ...],
) -> tuple[RegionView, ...]:
    """Return the regions ``target`` claims from ``regions``."""
    return rule_projection.select_regions(regions, target)
