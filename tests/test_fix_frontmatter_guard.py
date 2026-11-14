"""Guard contracts for edits judged against a recognized frontmatter prefix.

Recognition decides whether a file has frontmatter at all; these tests start
from that answer and pin what an edit may touch afterwards. The two questions
are separate because a guard bug and a recognition bug fail differently: a
guard that admits too much edits metadata, while recognition that admits too
much disarms the guard for every edit in the file.
"""

import pytest
from stilyagi.engine import ir_view
from stilyagi.engine.fix_planning.frontmatter import (
    YamlFrontmatter,
    edit_conflicts_with_frontmatter,
    frontmatter_is_unchanged,
    is_frontmatter_boundary_insertion,
)
from stilyagi.fixes import TextEdit


def test_edit_conflicts_rejects_edits_against_an_unrecognized_frontmatter() -> None:
    """Treat an unverifiable frontmatter as protected rather than absent."""
    unresolved = YamlFrontmatter(None, None, None)

    assert edit_conflicts_with_frontmatter(TextEdit(0, 1, "x"), unresolved), (
        "an edit must be refused while frontmatter recognition is unresolved"
    )


def test_edit_conflicts_permits_edits_when_no_frontmatter_exists() -> None:
    """Allow an edit when the source carries no frontmatter at all."""
    assert not edit_conflicts_with_frontmatter(TextEdit(0, 1, "x"), None), (
        "an absent frontmatter protects nothing"
    )


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        pytest.param(TextEdit(0, 0, "x"), True, id="insertion-at-start"),
        pytest.param(TextEdit(19, 19, "x"), True, id="insertion-at-prefix-end"),
        pytest.param(TextEdit(20, 20, "x"), False, id="insertion-after-prefix"),
        pytest.param(TextEdit(19, 21, ""), True, id="removal-across-prefix-end"),
        pytest.param(TextEdit(21, 24, "x"), False, id="replacement-after-prefix"),
    ],
)
def test_edit_conflicts_uses_the_protected_prefix_boundary(
    edit: TextEdit,
    *,
    expected: bool,
) -> None:
    """Protect the frontmatter span and its closing line ending, and no more."""
    frontmatter = YamlFrontmatter(ir_view.SourceSpan(0, 19), 20, b"prefix")

    assert edit_conflicts_with_frontmatter(edit, frontmatter) is expected, (
        "only edits overlapping the protected prefix may be refused"
    )


def test_boundary_insertion_requires_the_exact_protected_end() -> None:
    """Recognize only a zero-width edit at the protected prefix end."""
    frontmatter = YamlFrontmatter(ir_view.SourceSpan(0, 19), 20, b"prefix")

    assert is_frontmatter_boundary_insertion(TextEdit(20, 20, "x"), frontmatter), (
        "an insertion immediately after the prefix must be recognized"
    )
    assert not is_frontmatter_boundary_insertion(TextEdit(19, 19, "x"), frontmatter), (
        "an insertion before the prefix end is not a boundary insertion"
    )
    assert not is_frontmatter_boundary_insertion(TextEdit(20, 21, "x"), frontmatter), (
        "a replacement at the boundary is not an insertion"
    )
    assert not is_frontmatter_boundary_insertion(
        TextEdit(20, 20, "x"), YamlFrontmatter(None, None, None)
    ), "an unresolved frontmatter has no boundary to insert at"
    assert not is_frontmatter_boundary_insertion(TextEdit(20, 20, "x"), None), (
        "an absent frontmatter has no boundary to insert at"
    )


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        pytest.param(None, None, True, id="both-absent"),
        pytest.param(
            None,
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, b"a"),
            False,
            id="added",
        ),
        pytest.param(
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, b"a"),
            None,
            False,
            id="removed",
        ),
        pytest.param(
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, b"a"),
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, b"a"),
            True,
            id="unchanged",
        ),
        pytest.param(
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, b"a"),
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, b"b"),
            False,
            id="changed-bytes",
        ),
        pytest.param(
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, None),
            YamlFrontmatter(ir_view.SourceSpan(0, 1), 1, None),
            False,
            id="unverifiable",
        ),
    ],
)
def test_frontmatter_is_unchanged_compares_recognized_bytes(
    before: YamlFrontmatter | None,
    after: YamlFrontmatter | None,
    *,
    expected: bool,
) -> None:
    """Compare recognition across a splice rather than assuming it survived."""
    assert frontmatter_is_unchanged(before, after) is expected, (
        "a splice may only preserve frontmatter whose recognized bytes match"
    )
