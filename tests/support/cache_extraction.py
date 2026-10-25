"""Share a real-storage extraction service and request helper across tests."""

import dataclasses as dc
import typing as typ

import pytest
from stilyagi import engine, model
from stilyagi.cache.extraction import (
    CacheExtractionInput,
    CacheExtractionService,
    CacheServiceConfig,
)

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi.config import StilyagiConfig


@dc.dataclass(frozen=True, slots=True)
class CacheTestRequest:
    """Collect per-request options varied by extraction cache tests."""

    source: str = "# Café\r\n"
    identity: str = "guide.md"
    from_stdin: bool = False
    force_fresh: bool = False


_DEFAULT_REQUEST = CacheTestRequest()


@pytest.fixture
def cache_invocation(
    tmp_path: pathlib.Path,
) -> tuple[CacheExtractionService, list[str]]:
    """Build a real-storage service with an independently counted extractor."""
    calls: list[str] = []

    def extract(
        source: str,
        syntax: model.Syntax,
        source_path: str | None,
    ) -> engine.ExtractionResult:
        """Count calls independently of the service counters."""
        calls.append(source)
        return engine.extract_document_result(source, syntax, source_path=source_path)

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=tmp_path,
            package_version="test-version",
            extractor=extract,
            native_digest_factory=lambda: "native-digest",
            builtin_signature_factory=lambda _config: "builtin-signature",
        )
    )
    return service, calls


def extract_cached_document(
    service: CacheExtractionService,
    config: StilyagiConfig,
    request: CacheTestRequest = _DEFAULT_REQUEST,
) -> engine.ExtractionResult:
    """Run the service with one stable Markdown request."""
    return service.extract(
        CacheExtractionInput(
            source_text=request.source,
            syntax=model.Syntax.MARKDOWN,
            reported_identity=request.identity,
            effective_config=config,
            cache_dir=config.cache_dir,
            from_stdin=request.from_stdin,
            force_fresh=request.force_fresh,
        )
    )
