"""Cold, warm, corrupt, and identity paths for persistent extraction."""

import hashlib
import json
import typing as typ

import pytest
from stilyagi import engine, model
from stilyagi.cache.extraction import CacheExtractionService, CacheServiceConfig
from stilyagi.cache.model import CACHE_NAMESPACE_NAME
from stilyagi.config import StilyagiConfig

from tests.support.cache_extraction import (
    CacheTestRequest,
    extract_cached_document,
)

if typ.TYPE_CHECKING:
    import pathlib


def test_cold_and_warm_extraction_have_equal_ir_and_only_cold_parses(
    cache_invocation: tuple[CacheExtractionService, list[str]],
    tmp_path: pathlib.Path,
) -> None:
    """Read twice and verify only the cold extraction reaches Rust."""
    service, calls = cache_invocation
    config = StilyagiConfig(cache_dir=tmp_path / "cache")

    cold = extract_cached_document(service, config)
    warm = extract_cached_document(service, config)

    assert warm == cold, "warm extraction must restore the same canonical IR"
    assert calls == ["# Café\r\n"], "only the cold request should reach the extractor"
    assert service.counters.misses == 1, "the first request must be counted as a miss"
    assert service.counters.hits == 1, "the second request must be served from cache"
    service.close()


@pytest.mark.parametrize(
    ("changed", "identity"),
    [
        pytest.param("# Café\n", "guide.md", id="line-ending-bytes"),
        pytest.param("---\ntitle: Café\n---\n# Café\r\n", "guide.md", id="frontmatter"),
        pytest.param("# Café\r\n", "other.md", id="reported-identity"),
    ],
)
def test_source_and_identity_changes_miss_the_cache(
    cache_invocation: tuple[CacheExtractionService, list[str]],
    tmp_path: pathlib.Path,
    changed: str,
    identity: str,
) -> None:
    """Miss when source bytes or the reported source identity changes."""
    service, calls = cache_invocation
    config = StilyagiConfig(cache_dir=tmp_path / "cache")
    extract_cached_document(service, config)

    extract_cached_document(
        service,
        config,
        CacheTestRequest(source=changed, identity=identity),
    )

    assert len(calls) == 2, "each changed identity must reach the extractor"
    assert service.counters.misses == 2, "source or reported identity changes must miss"
    service.close()


@pytest.mark.parametrize("dimension", ["config", "extension", "version", "builtin"])
def test_each_runtime_key_dimension_prevents_reuse(
    cache_invocation: tuple[CacheExtractionService, list[str]],
    tmp_path: pathlib.Path,
    dimension: str,
) -> None:
    """Changing effective or runtime identity forces a second extraction."""
    first_service, calls = cache_invocation
    config = StilyagiConfig(cache_dir=tmp_path / "cache")
    extract_cached_document(first_service, config)
    first_service.close()

    native_digest = "native-b" if dimension == "extension" else "native-digest"
    package_version = "other-version" if dimension == "version" else "test-version"
    builtin_signature = (
        "other-builtin" if dimension == "builtin" else "builtin-signature"
    )

    def extract(
        source: str,
        syntax: model.Syntax,
        source_path: str | None,
    ) -> engine.ExtractionResult:
        """Share the independent parser count across service instances."""
        calls.append(source)
        return engine.extract_document_result(source, syntax, source_path=source_path)

    second_service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version=package_version,
            extractor=extract,
            native_digest_factory=lambda: native_digest,
            builtin_signature_factory=lambda _config: builtin_signature,
        )
    )
    second_config = (
        StilyagiConfig(cache_dir=config.cache_dir, reserved={"line-length": 89})
        if dimension == "config"
        else config
    )

    extract_cached_document(second_service, second_config)

    assert calls == ["# Café\r\n", "# Café\r\n"], (
        "a changed runtime identity must trigger a fresh extraction"
    )
    assert second_service.counters.misses == 1, "the changed runtime identity must miss"
    assert second_service.counters.hits == 0, "the old entry must not be reused"
    second_service.close()


def _corrupt_cache_entry(entry: pathlib.Path, corruption: str) -> None:
    """Apply one malformed, stale-checksum, or identity mutation."""
    if corruption == "truncated":
        entry.write_bytes(b"{")
        return

    envelope = json.loads(entry.read_bytes())
    if corruption == "checksum":
        envelope["ir_json"] = "{}"
    else:
        payload = json.loads(envelope["ir_json"])
        if corruption == "frontmatter-checksum":
            frontmatter = next(
                region
                for region in payload["regions"]
                if region["kind"] == "frontmatter"
            )
            frontmatter["attrs"]["format"] = "toml"
        else:
            payload["document"]["path"] = "wrong.md"
            envelope["ir_sha256"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest()
        envelope["ir_json"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    entry.write_text(json.dumps(envelope), encoding="utf-8")


@pytest.mark.parametrize(
    "corruption",
    ["truncated", "checksum", "identity", "frontmatter-checksum"],
)
def test_corrupt_entry_is_an_invalid_miss_then_replaced(
    cache_invocation: tuple[CacheExtractionService, list[str]],
    tmp_path: pathlib.Path,
    corruption: str,
) -> None:
    """Treat malformed, checksummed, or identity-mismatched entries as misses."""
    service, calls = cache_invocation
    config = StilyagiConfig(cache_dir=tmp_path / "cache")
    request = (
        CacheTestRequest(
            source="---\ntitle: Café\n---\n# Body\r\n",
            identity="guide.md",
        )
        if corruption == "frontmatter-checksum"
        else CacheTestRequest()
    )
    extract_cached_document(service, config, request)
    namespace = config.cache_dir / CACHE_NAMESPACE_NAME
    entry = next(namespace.glob("[0-9a-f]*.json"))
    _corrupt_cache_entry(entry, corruption)

    cold_again = extract_cached_document(service, config, request)
    warm_after_repair = extract_cached_document(service, config, request)

    assert cold_again == warm_after_repair, "repaired entries must hydrate the same IR"
    assert calls == [request.source, request.source], (
        "a corrupt entry must be replaced after one fresh extraction"
    )
    assert service.counters.invalid == 1, "the corrupt entry must be counted once"
    assert service.counters.misses == 2, (
        "the corrupt entry must cause one replacement miss"
    )
    assert service.counters.hits == 1, (
        "the repaired entry must serve the following request"
    )
    service.close()
