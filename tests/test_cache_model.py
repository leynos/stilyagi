"""Contracts for persistent extraction-cache identities and filenames."""

import dataclasses as dc

import pytest
from stilyagi.cache.model import (
    CacheFileKind,
    ExtractionRequest,
    cache_entry_name,
    cache_key,
    classify_cache_filename,
)


@pytest.fixture
def request_data() -> ExtractionRequest:
    """Build one stable Markdown extraction identity for key tests."""
    return ExtractionRequest(
        source_text="# Café\r\n",
        syntax="markdown",
        reported_identity="docs/guide.md",
        effective_config={
            "lint": {"ignore": [], "select": ["DOC", "STY"]},
            "extract": {"frontmatter": True, "gfm": True},
        },
        native_extension_digest="native-a",
        package_version="1.2.3",
        builtin_pack_signature="builtin-a",
    )


def test_cache_key_is_stable_for_equivalent_mapping_order(
    request_data: ExtractionRequest,
) -> None:
    """Sort effective config keys before deriving extraction identity."""
    reordered = dc.replace(
        request_data,
        effective_config={
            "extract": {"gfm": True, "frontmatter": True},
            "lint": {"select": ["DOC", "STY"], "ignore": []},
        },
    )

    assert cache_key(request_data) == cache_key(reordered), (
        "equivalent config mappings must produce the same identity"
    )


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param({"source_text": "# Café\n"}, id="source-bytes"),
        pytest.param({"syntax": "python_docstring"}, id="syntax"),
        pytest.param({"reported_identity": "docs/other.md"}, id="reported-identity"),
        pytest.param(
            {"effective_config": {"lint": {"select": ["DOC"]}}},
            id="effective-config",
        ),
        pytest.param({"native_extension_digest": "native-b"}, id="native-extension"),
        pytest.param({"package_version": "1.2.4"}, id="package-version"),
        pytest.param({"builtin_pack_signature": "builtin-b"}, id="builtin-pack"),
        pytest.param({"nlp_signature": "active-model-a"}, id="nlp-signature"),
    ],
)
def test_each_extraction_identity_dimension_changes_the_key(
    request_data: ExtractionRequest,
    changed: dict[str, object],
) -> None:
    """Ensure every source, config, runtime, and identity input affects the key."""
    assert cache_key(request_data) != cache_key(dc.replace(request_data, **changed)), (
        "every extraction identity dimension must invalidate reuse"
    )


def test_cache_key_uses_complete_frontmatter_and_line_ending_bytes(
    request_data: ExtractionRequest,
) -> None:
    """Invalidate identity when frontmatter or source line endings change."""
    frontmatter_edit = dc.replace(
        request_data,
        source_text="---\ntitle: Café\nsummary: longer\n---\n# Café\r\n",
    )

    assert cache_key(request_data) != cache_key(frontmatter_edit), (
        "frontmatter bytes and line endings must participate in identity"
    )


def test_cache_entry_name_is_a_lowercase_sha256_digest(
    request_data: ExtractionRequest,
) -> None:
    """Map a valid request digest to the exact owned entry filename."""
    entry_name = cache_entry_name(cache_key(request_data))

    assert len(entry_name) == 69, "entry names must contain a full digest and suffix"
    assert entry_name.endswith(".json"), "entry names must use the JSON suffix"
    assert entry_name[:-5].lower() == entry_name[:-5], (
        "entry digests must use lowercase hexadecimal"
    )
    assert classify_cache_filename(entry_name) is CacheFileKind.ENTRY, (
        "generated digest filenames must be recognized as entries"
    )


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        pytest.param(
            ".tmp-0123456789abcdef0123456789abcdef", CacheFileKind.TEMP, id="temp"
        ),
        pytest.param("A" * 64 + ".json", None, id="uppercase-entry"),
        pytest.param("a" * 63 + ".json", None, id="short-entry"),
        pytest.param("a" * 64 + ".JSON", None, id="wrong-suffix"),
        pytest.param(".tmp-0123456789abcdef0123456789abcdeg", None, id="bad-temp-hex"),
        pytest.param("unrelated.json", None, id="unknown"),
    ],
)
def test_cache_filename_classifier_is_exact(
    filename: str,
    expected: CacheFileKind | None,
) -> None:
    """Classify only exact cache entry and temporary filename forms."""
    assert classify_cache_filename(filename) is expected, (
        "the filename classifier must accept only exact owned forms"
    )


def test_cache_entry_name_rejects_non_digest_keys() -> None:
    """Reject keys that cannot safely identify a fixed cache entry name."""
    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        cache_entry_name("not-a-key")
