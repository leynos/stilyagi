"""Recognition contracts for source-backed YAML frontmatter boundaries.

The planner contracts in `test_fix_frontmatter.py` show that frontmatter is
protected; these tests pin down which IR shapes are recognized as frontmatter
at all, so a malformed or ambiguous envelope cannot silently disarm the guard.
What an edit may touch once a prefix *is* recognized is covered separately in
`test_fix_frontmatter_guard.py`.
"""

import typing as typ

import pytest
from stilyagi import engine, model
from stilyagi.engine.fix_planning.frontmatter import (
    YamlFrontmatter,
    yaml_frontmatter,
)

from tests.support import frontmatter_documents as docs

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_yaml_frontmatter_recognizes_a_source_backed_region() -> None:
    """Return the byte-faithful protected prefix for one recognized region."""
    source_bytes = docs.SOURCE.encode()

    frontmatter = yaml_frontmatter(
        docs.document(docs.envelope(docs.region())), source_bytes
    )

    assert frontmatter is not None, "a source-backed YAML region must be recognized"
    assert frontmatter.span is not None, "recognition must retain the source span"
    assert frontmatter.prefix_bytes == docs.PREFIX.encode(), (
        "the protected prefix must include its closing line ending"
    )


@pytest.mark.parametrize(
    ("ir", "expected_reason"),
    [
        pytest.param(None, "no IR", id="absent-ir"),
        pytest.param({}, "no regions", id="absent-regions"),
        pytest.param({"regions": "none"}, "regions not a sequence", id="regions-type"),
        pytest.param(docs.envelope(), "no frontmatter region", id="empty-regions"),
        pytest.param(docs.envelope("prose"), "region not a mapping", id="region-type"),
        pytest.param(
            docs.envelope(docs.region(kind="prose")), "wrong kind", id="region-kind"
        ),
        pytest.param(
            docs.envelope(docs.region(attrs={"format": "toml"})),
            "wrong attribute format",
            id="region-format",
        ),
        pytest.param(
            docs.envelope(docs.region(attrs=None)),
            "attributes not a mapping",
            id="attrs-type",
        ),
        pytest.param(
            docs.envelope({1: "non-string key", "kind": "frontmatter"}),
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
    assert yaml_frontmatter(docs.document(ir), docs.SOURCE.encode()) is None, (
        f"an envelope with {expected_reason} must not claim frontmatter"
    )


def test_yaml_frontmatter_refuses_ambiguous_multiple_regions() -> None:
    """Refuse to choose between several frontmatter regions."""
    frontmatter = yaml_frontmatter(
        docs.document(docs.envelope(docs.region(), docs.region())), docs.SOURCE.encode()
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
        docs.document(docs.envelope(docs.region(segments=segments))),
        docs.SOURCE.encode(),
    )

    assert frontmatter == YamlFrontmatter(None, None, None), (
        "a region without a usable source span cannot protect anything"
    )


_VERIFIED_SEGMENT = {
    "text": "---\ntitle: Café\n---",
    "source": {"byte_start": 0, "byte_end": 20},
}


@pytest.mark.parametrize(
    ("region", "reason"),
    [
        pytest.param(
            docs.region(
                segments=[
                    {
                        "text": "x",
                        "source": {
                            "byte_start": 0,
                            "byte_end": len(docs.SOURCE.encode()) + 10,
                        },
                    }
                ]
            ),
            "span beyond the source",
            id="span-too-long",
        ),
        pytest.param(
            docs.region(
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
            docs.region(
                segments=[
                    {
                        "text": "---\ntitle: Café\n---",
                        "source": {"byte_start": 1, "byte_end": 21},
                    }
                ]
            ),
            "offsets addressing different bytes than its text",
            id="offsets-address-different-bytes",
        ),
        pytest.param(
            docs.region(
                segments=[
                    {
                        "text": "---\ntitle: Tea\n---",
                        "source": {"byte_start": 0, "byte_end": 20},
                    },
                    _VERIFIED_SEGMENT,
                ]
            ),
            "first segment disagreeing while a later one agrees",
            id="later-segment-agrees",
        ),
    ],
)
def test_yaml_frontmatter_requires_the_region_text_to_match_its_source(
    region: dict[str, object],
    reason: str,
) -> None:
    """Refuse frontmatter whose recorded text no longer describes the source.

    The last case pins the refusal to the first claimed segment. Searching on
    for a segment that agrees would let a region with a contradictory opening
    segment protect a prefix on the strength of a later one, which is a
    different region's claim.
    """
    frontmatter = yaml_frontmatter(
        docs.document(docs.envelope(region)), docs.SOURCE.encode()
    )

    assert frontmatter == YamlFrontmatter(None, None, None), (
        f"frontmatter with {reason} must not be protected"
    )


def test_yaml_frontmatter_refuses_undecodable_region_bytes() -> None:
    """Refuse frontmatter whose claimed source range is not valid UTF-8."""
    source_bytes = b"---\ntitle: \xff\n---\n"

    frontmatter = yaml_frontmatter(
        docs.document(
            docs.envelope(
                docs.region(
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
    source = docs.PREFIX.removesuffix("\n").encode() + ending + b"body"

    frontmatter = yaml_frontmatter(
        docs.document(
            docs.envelope(
                docs.region(
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


def test_yaml_frontmatter_reads_the_extracted_document() -> None:
    """Recognize the frontmatter of a real Rust extraction result."""
    document = engine.extract_document(docs.SOURCE, model.Syntax.MARKDOWN)

    frontmatter = yaml_frontmatter(document, docs.SOURCE.encode())

    assert frontmatter is not None, "Rust's own frontmatter region must be recognized"
    assert frontmatter.prefix_bytes == docs.PREFIX.encode(), (
        "the real extraction must yield the same protected prefix"
    )
