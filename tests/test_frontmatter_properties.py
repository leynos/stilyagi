"""Property tests for the YAML-frontmatter guard over generated sources.

The guard has three parts. Per edit, `classify_edit` refuses anything that
overlaps the protected prefix, and separately suspends the admissibility bound
for a zero-width insertion at exactly `protected_end`. At plan level,
`_preserves_yaml_frontmatter` re-extracts the replacement and compares the
recognized prefix byte-for-byte. The hand-written contracts pin selected
examples of each. These properties generate the document instead -- several
YAML shapes, all three line endings, with and without a byte-order mark, and
both an ended file and a fence terminated by a line ending -- so each part is
measured across the shapes rather than at the ones someone thought to write
down.

The properties are:

* an edit wholly inside a body span is accepted and leaves the frontmatter
  bytes unchanged, with the mark still in front of them
  (`test_a_body_edit_is_accepted_and_leaves_the_prefix_byte_identical`);
* an edit whose start lies inside the protected prefix is refused
  (`test_an_edit_starting_inside_the_prefix_is_refused`);
* an insertion at `protected_end` is accepted when the fence is terminated,
  and refused when the fence ends the file
  (`test_a_terminated_fence_admits_a_body_insertion_and_keeps_the_prefix`,
  `test_an_eof_fenced_prefix_refuses_an_insertion_that_extends_the_fence`);
* a character-aligned body edit never trips the UTF-8 boundary check
  (`test_a_character_aligned_body_edit_never_cuts_utf8`).

Each of the three parts is pinned by a property that fails when that part alone
is weakened, which is what keeps a guard that merely *looks* at the prefix from
passing: an accepted plan is visible as `fixed_bytes`, and a refusal has to be
reported as a rejection naming the protection rather than as an empty plan.
"""

import hypothesis as hyp
import hypothesis.strategies as st
from stilyagi import config, diagnostics, engine, model
from stilyagi.engine import ir_view
from stilyagi.engine.fix_planning.frontmatter import (
    frontmatter_is_unchanged,
    yaml_frontmatter,
)
from stilyagi.engine.fix_planning.offset_view import OffsetView
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import Applicability, Fix, FixLevel, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.frontmatter_strategies import (
    FrontmatterCase,
    character_boundaries,
    eof_fenced_case,
    frontmatter_case,
    replacement_text,
)

_PREFIX_REJECTION = "fix-error/frontmatter-protected"


def _request(case: FrontmatterCase, edit: TextEdit) -> FixPlanRequest:
    """Build a permissive safe-level planning request offering one edit."""
    return FixPlanRequest(
        case.source_bytes,
        case.document,
        (
            diagnostics.Diagnostic(
                "docs/example.md",
                "PUN201",
                "Rewrite the sample paragraph.",
                fix=Fix("Rewrite the sample paragraph", Applicability.SAFE, (edit,)),
            ),
        ),
        FixLevel.SAFE,
        config.LintConfig(),
    )


def _require_body_span(case: FrontmatterCase) -> ir_view.SourceSpan:
    """Return the case's body span, which the terminated family always has."""
    span = case.body_span
    assert span is not None, "expected a terminated fence to have a body span"
    return span


def _body_edit(case: FrontmatterCase, replacement: str) -> TextEdit:
    """Replace the generated body span with ``replacement``."""
    return TextEdit.replace(_require_body_span(case), replacement)


@hyp.given(case=frontmatter_case(), replacement=replacement_text())
@hyp.settings(max_examples=64, deadline=None)
def test_a_body_edit_is_accepted_and_leaves_the_prefix_byte_identical(
    case: FrontmatterCase,
    replacement: str,
) -> None:
    """A repair confined to the body preserves the generated metadata.

    Acceptance is asserted first: the property would hold vacuously over a
    tree where every edit were refused, which is exactly how a guard
    regression looks from the preservation side alone.
    """
    plan = plan_fixes(_request(case, _body_edit(case, replacement)))

    assert_with_context(not plan.rejections, "expected a body edit to be accepted")
    fixed_bytes = plan.fixed_bytes
    assert fixed_bytes is not None, "expected an accepted body edit to write bytes"

    # The returned bytes are restored into the source's own shape, so the mark
    # has to be split off again before they can be compared with a prefix the
    # IR addresses past it.
    fixed_view = OffsetView.of(fixed_bytes)
    assert_with_context(
        fixed_view.body.startswith(case.prefix_bytes),
        "expected the replacement to begin with the original frontmatter prefix",
    )

    before = yaml_frontmatter(case.document, case.body)
    after = yaml_frontmatter(
        engine.extract_document(
            fixed_view.body.decode("utf-8-sig"), model.Syntax.MARKDOWN
        ),
        fixed_view.body,
    )
    assert_with_context(
        frontmatter_is_unchanged(before, after),
        "expected the re-extracted frontmatter to hold the same prefix bytes",
    )
    assert_with_context(
        fixed_view.bom == OffsetView.of(case.source_bytes).bom,
        "expected the source's byte-order mark, if any, to survive the repair",
    )


@hyp.given(data=st.data())
@hyp.settings(max_examples=64, deadline=None)
def test_an_edit_starting_inside_the_prefix_is_refused(
    data: st.DataObject,
) -> None:
    """Any edit whose start lies in the protected prefix offers nothing to write.

    The generated body span is widened leftwards by drawing a start inside
    ``[0, protected_end)``, so the edit overlaps real metadata rather than a
    hand-picked fence line, and the whole plan must refuse.

    The start is drawn from character boundaries, not arbitrary integers. A
    start inside ``Café`` would be refused as ``fix-error/non-utf8-boundary``
    before the guard is ever consulted, and asserting the guard's own
    identifier on such a case would fail for a reason unrelated to the prefix.
    """
    case = data.draw(frontmatter_case())
    prefix_boundaries = character_boundaries(
        case.body, ir_view.SourceSpan(0, case.protected_end)
    )
    start = data.draw(st.sampled_from(prefix_boundaries[:-1]))
    edit = TextEdit(
        start, _require_body_span(case).byte_end, data.draw(replacement_text())
    )

    plan = plan_fixes(_request(case, edit))

    assert_with_context(
        plan.fixed_bytes is None,
        "expected an edit overlapping the protected prefix to write nothing",
    )
    assert_with_context(
        bool(plan.rejections) and plan.rejections[0].identifier == _PREFIX_REJECTION,
        "expected the refusal to name frontmatter protection",
    )
    assert_with_context(
        not plan.edits, "expected a refused plan to report no accepted edits"
    )


@hyp.given(case=frontmatter_case(), insertion=replacement_text())
@hyp.settings(max_examples=64, deadline=None)
def test_a_terminated_fence_admits_a_body_insertion_and_keeps_the_prefix(
    case: FrontmatterCase,
    insertion: str,
) -> None:
    """A closing line ending makes ``protected_end`` the start of the body.

    The per-edit overlap test is suspended at exactly this position, so an
    insertion here is the one shape the guard deliberately allows. Asserting
    that it is accepted, and not merely harmless, is what keeps the property
    from passing over a tree where the suspension was removed.
    """
    edit = TextEdit(case.protected_end, case.protected_end, insertion)

    plan = plan_fixes(_request(case, edit))

    assert_with_context(not plan.rejections, "expected a body insertion to be accepted")
    fixed_bytes = plan.fixed_bytes
    assert fixed_bytes is not None, "expected an accepted insertion to write bytes"
    assert_with_context(
        OffsetView.of(fixed_bytes).body.startswith(case.prefix_bytes),
        "expected the insertion to leave the prefix as it was",
    )


@hyp.given(case=eof_fenced_case(), insertion=replacement_text())
@hyp.settings(max_examples=64, deadline=None)
def test_an_eof_fenced_prefix_refuses_an_insertion_that_extends_the_fence(
    case: FrontmatterCase,
    insertion: str,
) -> None:
    """A fence at the end of the file makes the plan-level comparison the guard.

    With no closing line ending, ``protected_end`` is the end of the source,
    so there is no body for an insertion to precede. The per-edit overlap test
    admits the position and :func:`is_frontmatter_boundary_insertion` suspends
    the admissibility bound there, which leaves only the re-extraction and
    prefix comparison to notice that the inserted text has become part of the
    fence. This property is what fails when that comparison is weakened.
    """
    assert_with_context(
        case.protected_end == len(case.body),
        "expected an EOF-fenced case to end at its protected prefix",
    )
    edit = TextEdit(case.protected_end, case.protected_end, insertion)

    plan = plan_fixes(_request(case, edit))

    assert_with_context(
        plan.fixed_bytes is None,
        "expected an insertion past an unterminated fence to write nothing",
    )
    assert_with_context(
        bool(plan.rejections) and plan.rejections[0].identifier == _PREFIX_REJECTION,
        "expected the refusal to name frontmatter protection",
    )


@hyp.given(case=frontmatter_case(), data=st.data())
@hyp.settings(max_examples=64, deadline=None)
def test_a_character_aligned_body_edit_never_cuts_utf8(
    case: FrontmatterCase,
    data: st.DataObject,
) -> None:
    """Generated whole-character edits are accepted for non-ASCII bodies too.

    ``Café`` in both the metadata and the body makes a byte-arithmetic splicing
    error visible: an edit that landed mid-character would be refused as
    ``fix-error/non-utf8-boundary``, and a splice that split the code point
    anyway would fail to decode. Both are measured here on the same edit.
    """
    boundaries = character_boundaries(case.body, _require_body_span(case))
    start_index = data.draw(st.integers(min_value=0, max_value=len(boundaries) - 1))
    end_index = data.draw(
        st.integers(min_value=start_index, max_value=len(boundaries) - 1)
    )
    span = ir_view.SourceSpan(boundaries[start_index], boundaries[end_index])
    edit = TextEdit.replace(span, data.draw(replacement_text()))

    plan = plan_fixes(_request(case, edit))

    assert_with_context(
        not any(
            rejection.identifier == "fix-error/non-utf8-boundary"
            for rejection in plan.rejections
        ),
        "expected character-aligned edit boundaries to pass the UTF-8 check",
    )
    fixed_bytes = plan.fixed_bytes
    assert fixed_bytes is not None, "expected an accepted character-aligned edit"
    assert fixed_bytes.decode() is not None, (
        "expected the accepted splice to leave decodable bytes"
    )
