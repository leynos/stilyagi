"""Recognition contracts for source-backed YAML frontmatter boundaries.

The planner contracts in `test_fix_frontmatter.py` show that frontmatter is
protected; these tests pin down which IR shapes are recognized as frontmatter
at all, so a malformed or ambiguous envelope cannot silently disarm the guard.
"""

import typing as typ

import pytest
from stilyagi import engine, model
from stilyagi.engine import ir_view
from stilyagi.engine.fix_planning.frontmatter import (
    YamlFrontmatter,
    edit_conflicts_with_frontmatter,
    frontmatter_is_unchanged,
    is_frontmatter_boundary_insertion,
    yaml_frontmatter,
)
from stilyagi.fixes import TextEdit

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_SOURCE = "---\ntitle: Café\n---\n\nHello world\n"
# The protected span ends after the closing fence's line ending. Kept as text
# and encoded where it is asserted: a byte-literal escape for the accented
# letter splits the word, and the spelling gate then reads a fragment of it.
_PREFIX = "---\ntitle: Café\n---\n"


def _document(ir: cabc.Mapping[str, object] | None) -> model.Document:
    """Build a Markdown document carrying one chosen IR envelope."""
    return model.Document(syntax=model.Syntax.MARKDOWN, ir=ir)


def _region(**overrides: object) -> dict[str, object]:
    """Return one YAML frontmatter region with the requested fields replaced."""
    region: dict[str, object] = {
        "kind": "frontmatter",
        "attrs": {"format": "yaml"},
        "segments": [
            {
                "text": "---\ntitle: Café\n---",
                "source": {"byte_start": 0, "byte_end": 20},
            }
        ],
    }
    region.update(overrides)
    return region


def _envelope(*regions: object) -> dict[str, object]:
    """Return an IR envelope carrying exactly the supplied regions."""
    return {"regions": list(regions)}


def test_yaml_frontmatter_recognizes_a_source_backed_region() -> None:
    """Return the byte-faithful protected prefix for one recognized region."""
    source_bytes = _SOURCE.encode()

    frontmatter = yaml_frontmatter(_document(_envelope(_region())), source_bytes)

    assert frontmatter is not None, "a source-backed YAML region must be recognized"
    assert frontmatter.span is not None, "recognition must retain the source span"
    assert frontmatter.prefix_bytes == _PREFIX.encode(), (
        "the protected prefix must include its closing line ending"
    )


@pytest.mark.parametrize(
    ("ir", "expected_reason"),
    [
        pytest.param(None, "no IR", id="absent-ir"),
        pytest.param({}, "no regions", id="absent-regions"),
        pytest.param({"regions": "none"}, "regions not a sequence", id="regions-type"),
        pytest.param(_envelope(), "no frontmatter region", id="empty-regions"),
        pytest.param(_envelope("prose"), "region not a mapping", id="region-type"),
        pytest.param(_envelope(_region(kind="prose")), "wrong kind", id="region-kind"),
        pytest.param(
            _envelope(_region(attrs={"format": "toml"})),
            "wrong attribute format",
            id="region-format",
        ),
        pytest.param(
            _envelope(_region(attrs=None)), "attributes not a mapping", id="attrs-type"
        ),
        pytest.param(
            _envelope({1: "non-string key", "kind": "frontmatter"}),
            "mapping with a non-string key",
            id="attrs-key-type",
        ),
    ],
)
def test_yaml_frontmatter_ignores_unrecognized_envelopes(
    ir: cabc.Mapping[str, object] | None,
    expected_reason: str,
) -> None:
    """Treat every non-frontmatter IR shape as absent rather than protected."""
    assert yaml_frontmatter(_document(ir), _SOURCE.encode()) is None, (
        f"an envelope with {expected_reason} must not claim frontmatter"
    )


def test_yaml_frontmatter_refuses_ambiguous_multiple_regions() -> None:
    """Refuse to choose between several frontmatter regions."""
    frontmatter = yaml_frontmatter(
        _document(_envelope(_region(), _region())), _SOURCE.encode()
    )

    assert frontmatter == YamlFrontmatter(None, None, None), (
        "several frontmatter regions must disable rather than guess at protection"
    )


@pytest.mark.parametrize(
    "segments",
    [
        pytest.param("none", id="segments-not-a-sequence"),
        pytest.param([], id="no-segments"),
        pytest.param(["segment"], id="segment-not-a-mapping"),
        pytest.param([{"text": "x"}], id="segment-without-source"),
        pytest.param(
            [{"text": "x", "source": {"byte_start": 0}}], id="source-without-end"
        ),
        pytest.param(
            [{"text": "x", "source": {"byte_start": -1, "byte_end": 2}}],
            id="negative-start",
        ),
        pytest.param(
            [{"text": "x", "source": {"byte_start": 5, "byte_end": 2}}],
            id="reversed-span",
        ),
        pytest.param(
            [{"text": "x", "source": {"byte_start": "0", "byte_end": 2}}],
            id="string-offsets",
        ),
    ],
)
def test_yaml_frontmatter_requires_a_valid_source_span(segments: object) -> None:
    """Refuse a region that cannot supply one ordered source span."""
    frontmatter = yaml_frontmatter(
        _document(_envelope(_region(segments=segments))), _SOURCE.encode()
    )

    assert frontmatter == YamlFrontmatter(None, None, None), (
        "a region without a usable source span cannot protect anything"
    )


@pytest.mark.parametrize(
    ("region", "reason"),
    [
        pytest.param(_region(), "span beyond the source", id="span-too-long"),
        pytest.param(
            _region(
                segments=[
                    {
                        "text": "---\ntitle: Tea\n---",
                        "source": {"byte_start": 0, "byte_end": 20},
                    }
                ]
            ),
            "text disagreeing with the source",
            id="text-mismatch",
        ),
        pytest.param(
            _region(
                segments=[
                    {
                        "text": "---\ntitle: Café\n---",
                        "source": {"byte_start": 1, "byte_end": 21},
                    }
                ]
            ),
            "segment offsets not matching the chosen span",
            id="offset-mismatch",
        ),
    ],
)
def test_yaml_frontmatter_requires_the_region_text_to_match_its_source(
    region: dict[str, object],
    reason: str,
) -> None:
    """Refuse frontmatter whose recorded text no longer describes the source."""
    source_bytes = _SOURCE.encode()
    if reason == "span beyond the source":
        region = _region(
            segments=[
                {
                    "text": "x",
                    "source": {"byte_start": 0, "byte_end": len(source_bytes) + 10},
                }
            ]
        )

    frontmatter = yaml_frontmatter(_document(_envelope(region)), source_bytes)

    assert frontmatter == YamlFrontmatter(None, None, None), (
        f"frontmatter whose {reason} must not be protected"
    )


def test_yaml_frontmatter_refuses_undecodable_region_bytes() -> None:
    """Refuse frontmatter whose claimed source range is not valid UTF-8."""
    source_bytes = b"---\ntitle: \xff\n---\n"

    frontmatter = yaml_frontmatter(
        _document(
            _envelope(
                _region(
                    segments=[
                        {
                            "text": "---\ntitle: Café\n---",
                            "source": {"byte_start": 0, "byte_end": 20},
                        }
                    ]
                )
            )
        ),
        source_bytes,
    )

    assert frontmatter == YamlFrontmatter(None, None, None), (
        "undecodable frontmatter bytes cannot be verified and must not be protected"
    )


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        pytest.param(b"\r\n", 22, id="crlf"),
        pytest.param(b"\n", 21, id="lf"),
        pytest.param(b"\r", 21, id="cr"),
        pytest.param(b"", 20, id="no-ending"),
    ],
)
def test_yaml_frontmatter_includes_one_closing_line_ending(
    ending: bytes,
    expected: int,
) -> None:
    """Extend the protected prefix over exactly one closing line ending."""
    source = _PREFIX.removesuffix("\n").encode() + ending + b"body"

    frontmatter = yaml_frontmatter(
        _document(
            _envelope(
                _region(
                    segments=[
                        {
                            "text": "---\ntitle: Café\n---",
                            "source": {"byte_start": 0, "byte_end": 20},
                        }
                    ]
                )
            )
        ),
        source,
    )

    assert frontmatter is not None, "the region must be recognized"
    assert frontmatter.protected_end == expected, (
        "the protected prefix must cover exactly one closing line ending"
    )


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


def test_yaml_frontmatter_reads_the_extracted_document() -> None:
    """Recognize the frontmatter of a real Rust extraction result."""
    document = engine.extract_document(_SOURCE, model.Syntax.MARKDOWN)

    frontmatter = yaml_frontmatter(document, _SOURCE.encode())

    assert frontmatter is not None, "Rust's own frontmatter region must be recognized"
    assert frontmatter.prefix_bytes == _PREFIX.encode(), (
        "the real extraction must yield the same protected prefix"
    )
