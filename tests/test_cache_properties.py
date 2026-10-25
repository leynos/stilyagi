"""Generated cache operations agree with an independent selection model."""

import dataclasses as dc
import pathlib
import shutil

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from stilyagi import engine, model
from stilyagi.cache.clean import clean_cache_tree
from stilyagi.cache.extraction import (
    CacheExtractionInput,
    CacheExtractionService,
    CacheServiceConfig,
)
from stilyagi.cache.model import (
    CACHE_NAMESPACE_NAME,
    ExtractionRequest,
    cache_entry_name,
    cache_key,
)
from stilyagi.config import StilyagiConfig
from stilyagi.config.inspection import _config_table

_FRONTMATTER_PREFIXES = (
    "",
    "---\ntitle: Café\n---\n",
    "---\ntitle: Café\nsummary: Longer\n---\r\n",
)
_OPERATIONS = (
    "read",
    "source",
    "frontmatter",
    "config",
    "version",
    "corrupt",
    "clean",
    "bypass",
)


@dc.dataclass(slots=True)
class _GeneratedCacheRun:
    """Keep generated cache state and independent expected outcomes together."""

    root: pathlib.Path
    body: str
    frontmatter_index: int
    source: str
    effective_config: StilyagiConfig
    version: str
    calls: list[str]
    service: CacheExtractionService
    valid_keys: set[str] = dc.field(default_factory=set)
    corrupted_keys: set[str] = dc.field(default_factory=set)
    cache_store_open: bool = False
    storage_was_removed: bool = False
    expected_hits: int = 0
    expected_misses: int = 0
    expected_invalid: int = 0
    expected_bypasses: int = 0

    def run(self, operation: str) -> None:
        """Apply one generated mutation or extraction request."""
        handlers = {
            "read": self._read,
            "source": self._change_source,
            "frontmatter": self._change_frontmatter,
            "config": self._change_config,
            "version": self._change_version,
            "corrupt": self._corrupt_entry,
            "clean": self._clean,
            "bypass": self._bypass,
        }
        handlers[operation]()

    def key(self) -> str:
        """Compute current identity independently from coordinator counters."""
        return cache_key(
            ExtractionRequest(
                source_text=self.source,
                syntax=model.Syntax.MARKDOWN.value,
                reported_identity="generated.md",
                effective_config=_config_table(self.effective_config),
                native_extension_digest="native",
                package_version=self.version,
                builtin_pack_signature="builtin",
            )
        )

    def assert_counters(self) -> None:
        """Compare service events with the independent selection model."""
        assert self.service.counters.hits == self.expected_hits, (
            "cache hit events must match the independent selection model"
        )
        assert self.service.counters.misses == self.expected_misses, (
            "cache miss events must match the independent selection model"
        )
        assert self.service.counters.invalid == self.expected_invalid, (
            "invalid-entry events must match the independent selection model"
        )
        assert self.service.counters.bypasses == self.expected_bypasses, (
            "bypass events must match the independent selection model"
        )

    def _change_source(self) -> None:
        """Toggle the Markdown body while leaving other identity inputs fixed."""
        self.body = "# changed\n" if self.body != "# changed\n" else ""
        self._refresh_source()

    def _change_frontmatter(self) -> None:
        """Cycle through frontmatter byte variants used by generated runs."""
        self.frontmatter_index = (self.frontmatter_index + 1) % len(
            _FRONTMATTER_PREFIXES
        )
        self._refresh_source()

    def _refresh_source(self) -> None:
        """Rebuild the exact source string from generated prefix and body."""
        prefix = _FRONTMATTER_PREFIXES[self.frontmatter_index]
        self.source = f"{prefix}{self.body}"

    def _change_config(self) -> None:
        """Toggle a resolved setting to produce a distinct cache identity."""
        current = self.effective_config.reserved.get("line-length", 88)
        next_length = 89 if current == 88 else 88
        self.effective_config = StilyagiConfig(
            cache_dir=self.effective_config.cache_dir,
            reserved={"line-length": next_length},
        )

    def _change_version(self) -> None:
        """Toggle the package version shared by the service and oracle."""
        self.version = "v2" if self.version == "v1" else "v1"
        self.service.package_version = self.version

    def _corrupt_entry(self) -> None:
        """Replace a known valid entry with malformed bytes for the next read."""
        key = self.key()
        if key not in self.valid_keys:
            return
        entry = self.root / "cache" / CACHE_NAMESPACE_NAME / cache_entry_name(key)
        entry.write_bytes(b"{")
        self.valid_keys.remove(key)
        self.corrupted_keys.add(key)

    def _clean(self) -> None:
        """Remove the disposable tree and reset modeled storage state."""
        self.storage_was_removed |= self.cache_store_open
        clean_cache_tree(self.root)
        self.valid_keys.clear()
        self.corrupted_keys.clear()
        self.cache_store_open = False

    def _read(self) -> None:
        """Request extraction through the ordinary cache-selection path."""
        self._extract(force_fresh=False)

    def _bypass(self) -> None:
        """Request extraction while bypassing every persistent cache entry."""
        self._extract(force_fresh=True)

    def _extract(self, *, force_fresh: bool) -> None:
        """Compare service output and parser calls with the independent oracle."""
        should_parse = self._predict_selection(force_fresh=force_fresh)
        before_calls = len(self.calls)
        result = self.service.extract(
            CacheExtractionInput(
                source_text=self.source,
                syntax=model.Syntax.MARKDOWN,
                reported_identity="generated.md",
                effective_config=self.effective_config,
                cache_dir=self.effective_config.cache_dir,
                force_fresh=force_fresh,
            )
        )
        expected = engine.extract_document_result(
            self.source,
            model.Syntax.MARKDOWN,
            source_path="generated.md",
        )
        assert result == expected, "cache selection must not change canonical IR output"
        assert len(self.calls) - before_calls == int(should_parse), (
            "the parser call count must match the independent selection prediction"
        )

    def _predict_selection(self, *, force_fresh: bool) -> bool:
        """Update the oracle and return whether Rust extraction must run."""
        if force_fresh:
            self.expected_bypasses += 1
            return True
        if self.storage_was_removed:
            self.storage_was_removed = False
            self.expected_bypasses += 1
            self.cache_store_open = False
            return True

        key = self.key()
        if key in self.corrupted_keys:
            self.corrupted_keys.remove(key)
            self.valid_keys.add(key)
            self.expected_invalid += 1
            self.expected_misses += 1
            self.cache_store_open = True
            return True
        if key in self.valid_keys:
            self.expected_hits += 1
            self.cache_store_open = True
            return False

        self.expected_misses += 1
        self.valid_keys.add(key)
        self.cache_store_open = True
        return True


def _generated_run(root: pathlib.Path, label: str) -> _GeneratedCacheRun:
    """Create an isolated service whose parser calls are counted separately."""
    shutil.rmtree(root)
    root.mkdir()
    body = f"# {label}\r\n" if label else ""
    source = f"{_FRONTMATTER_PREFIXES[0]}{body}"
    config = StilyagiConfig(cache_dir=pathlib.Path("cache"))
    version = "v1"
    calls: list[str] = []

    def extract(
        current_source: str,
        syntax: model.Syntax,
        identity: str | None,
    ) -> engine.ExtractionResult:
        """Count actual extractor calls independently of service counters."""
        calls.append(current_source)
        return engine.extract_document_result(
            current_source,
            syntax,
            source_path=identity,
        )

    service = CacheExtractionService(
        CacheServiceConfig(
            invocation_cwd=root,
            package_version=version,
            extractor=extract,
            native_digest_factory=lambda: "native",
            builtin_signature_factory=lambda _config: "builtin",
        )
    )
    return _GeneratedCacheRun(
        root=root,
        body=body,
        frontmatter_index=0,
        source=source,
        effective_config=config,
        version=version,
        calls=calls,
        service=service,
    )


@given(
    label=st.one_of(st.just(""), st.text(alphabet="abcé雪", max_size=8)),
    operations=st.lists(
        st.sampled_from(_OPERATIONS),
        min_size=1,
        max_size=20,
    ),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_generated_reads_mutations_corruption_clean_and_bypass(
    tmp_path: pathlib.Path,
    label: str,
    operations: list[str],
) -> None:
    """Track generated selections using an independent operation model."""
    run = _generated_run(tmp_path, label)
    try:
        for operation in operations:
            run.run(operation)
        run.assert_counters()
    finally:
        run.service.close()
