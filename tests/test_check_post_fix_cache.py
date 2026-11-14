"""Command-boundary coverage for the post-fix extraction-cache bypass.

`cli_run.relint_written_files` re-checks the files a `--fix` run wrote, and it
sets `force_fresh=True` so that re-check extracts the bytes now on disk. The
extraction service's own tests prove a `force_fresh` request bypasses storage;
they cannot prove the command boundary asks for one.

`force_fresh` is not what prevents a *stale* hit. The cache key already covers
`source_sha256` (`cache/model.py`), so an entry for the pre-fix bytes could
never be served for the repaired ones. What `force_fresh` buys is that the
re-lint touches no persistent storage at all: it neither reads an entry nor
publishes one for the bytes it just verified. Without the flag the re-lint
would still extract the repaired text, but it would consult storage first and
publish a second entry for content no planner reviewed.

This module drives `cli.run_check`, so the flag is exercised where it is set
rather than only where it is honoured.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_post_fix_cache.py
"""

import contextlib
import dataclasses as dc
import io
import json
import logging
import typing as typ

import pytest
from stilyagi import cli, diagnostics
from stilyagi.cache.extraction import CacheExtractionService, CacheServiceConfig
from stilyagi.cache.model import CACHE_NAMESPACE_NAME, OWNER_MARKER_NAME
from stilyagi.cli_args import CheckOptions
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.cache_extraction import (
    CacheServiceRegistrar,
    counting_extractor,
)
from tests.support.fix_fixtures import find_source_span

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi.rules.registry import RuleRunRequest


#: The source the planning pass reads, and the text the fix rewrites it to.
BEFORE = "Paragraph text.\n"
AFTER = "Section text.\n"


def _rewrite_paragraph(
    request: RuleRunRequest,
) -> list[diagnostics.Diagnostic]:
    """Offer one safe edit, and nothing once the re-lint reads its result."""
    prose = "".join(region.text for region in request.document.regions)
    if "Paragraph" not in prose:
        return []
    return [
        diagnostics.Diagnostic(
            path="notes.md",
            code="PUN201",
            message="Use the preferred paragraph term.",
            severity=diagnostics.Severity.ERROR,
            fix=Fix(
                "Rewrite paragraph",
                Applicability.SAFE,
                (
                    TextEdit.replace(
                        find_source_span(request.document, "Paragraph"), "Section"
                    ),
                ),
            ),
        )
    ]


def _namespace(root: pathlib.Path) -> pathlib.Path:
    """Return the owned cache namespace a run under `root` writes into."""
    return root / ".stilyagi_cache" / CACHE_NAMESPACE_NAME


def _entry_payloads(root: pathlib.Path) -> list[dict[str, object]]:
    """Return the decoded cache envelopes present, excluding the owner marker."""
    namespace = _namespace(root)
    if not namespace.is_dir():
        return []
    return [
        json.loads(path.read_bytes())
        for path in sorted(namespace.iterdir())
        if path.suffix == ".json" and path.name != OWNER_MARKER_NAME
    ]


def _entry_files(root: pathlib.Path) -> dict[str, bytes]:
    """Return the raw entry bytes present, keyed by name, excluding the marker.

    A re-lint that rewrote an entry keeps the same *name*, so comparing these
    bytes before and after is what distinguishes a served-entry bypass from a
    silent overwrite. The payload reader above cannot show that: it decodes
    the same envelope either way.

    Returns
    -------
    dict[str, bytes]
        Each entry's raw contents, keyed by its file name.
    """
    namespace = _namespace(root)
    return {
        path.name: path.read_bytes()
        for path in namespace.iterdir()
        if path.suffix == ".json" and path.name != OWNER_MARKER_NAME
    }


def _counting_service(
    tmp_path: pathlib.Path,
    calls: list[str],
    register: CacheServiceRegistrar,
) -> CacheExtractionService:
    """Build the injected service, recording each extraction into `calls`."""
    return register(
        CacheExtractionService(
            CacheServiceConfig(
                invocation_cwd=tmp_path,
                package_version="test-version",
                extractor=counting_extractor(calls),
                native_digest_factory=lambda: "native-digest",
                builtin_signature_factory=lambda _config: "builtin-signature",
            )
        )
    )


def _repair_the_target(tmp_path: pathlib.Path, service: CacheExtractionService) -> None:
    """Restore the pre-fix source and run `check --fix` over it."""
    (tmp_path / "notes.md").write_text(BEFORE, encoding="utf-8")
    with contextlib.redirect_stderr(io.StringIO()):
        assert (
            cli.run_check(
                CheckOptions(targets=("notes.md",), fix=True),
                collaborators=cli.CheckCollaborators(
                    rule_runner=_rewrite_paragraph,
                    extraction_cache=service,
                ),
            )
            == 0
        ), "expected the fix run to succeed"


def _warm_the_cache(
    tmp_path: pathlib.Path,
    service: CacheExtractionService,
    calls: list[str],
) -> None:
    """Run one plain `check` over the repaired bytes, then assert it published.

    The warm-up is the precondition the test below depends on: without an
    entry describing the repaired bytes there is nothing for the re-lint to
    wrongly read, and the test would pass for the wrong reason.
    """
    (tmp_path / "notes.md").write_text(AFTER, encoding="utf-8")
    with contextlib.redirect_stderr(io.StringIO()):
        assert (
            cli.run_check(
                CheckOptions(targets=("notes.md",)),
                collaborators=cli.CheckCollaborators(extraction_cache=service),
            )
            == 0
        ), "expected the warm-up run to succeed"
    assert calls == [AFTER], "expected the warm-up to extract the repaired bytes"
    warm = _entry_payloads(tmp_path)
    assert len(warm) == 1, (
        f"expected the warm-up to publish one entry, found {len(warm)}"
    )
    assert "Section" in str(warm[0].get("ir_json")), (
        "expected the warm entry to describe the repaired bytes"
    )


def _counters(records: list[logging.LogRecord]) -> tuple[object, object]:
    """Return the cache-hit and cache-bypass totals the run reported.

    The counters ride on the record as structured extras rather than in the
    message, so each one is read by name. Binding them here also keeps the
    failure messages free of attribute access on a `LogRecord`, which static
    checkers reject even though the extras are present.

    Returns
    -------
    tuple[object, object]
        The reported `cache_hits` and `cache_bypasses` totals.
    """
    summary = [
        record
        for record in records
        if getattr(record, "operation", None) == "extraction_cache_summary"
    ]
    assert summary, "expected the run to report its cache counters"
    return (
        getattr(summary[-1], "cache_hits", None),
        getattr(summary[-1], "cache_bypasses", None),
    )


@dc.dataclass(frozen=True, slots=True)
class FixedRun:
    """What one cache-enabled `check --fix` left behind.

    Both streams are captured rather than left to the terminal: the mutating
    path reports on standard error while a file target leaves standard output
    free, so a test that read only one of them would see an empty report and
    call it a pass.
    """

    exit_code: int
    stdout: str
    stderr: str


@pytest.fixture
def fixed_run(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixedRun:
    """Run one cache-enabled `check --fix` over a single repairable file."""
    (tmp_path / "notes.md").write_text(BEFORE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    stream = io.StringIO()
    error_stream = io.StringIO()
    with contextlib.redirect_stderr(error_stream):
        exit_code = cli.run_check(
            CheckOptions(targets=("notes.md",), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=_rewrite_paragraph
            ),
        )
    return FixedRun(exit_code, stream.getvalue(), error_stream.getvalue())


class TestPostFixCacheBypass:
    """A mutating run must not describe or cache bytes it has replaced."""

    def test_a_fix_run_rewrites_the_target(
        self,
        fixed_run: FixedRun,
        tmp_path: pathlib.Path,
    ) -> None:
        """The run applied the edit, so the re-lint has new bytes to read."""
        assert fixed_run.exit_code == 0, "expected a fully repaired file to exit zero"
        assert (tmp_path / "notes.md").read_text(encoding="utf-8") == AFTER, (
            "expected the fix to have been written to disk"
        )

    def test_the_re_lint_publishes_no_entry_for_the_repaired_bytes(
        self,
        fixed_run: FixedRun,
        tmp_path: pathlib.Path,
    ) -> None:
        """Keep exactly one entry, and keep it describing the pre-fix source.

        The count is the discriminating signal. The planning pass is
        cache-eligible and publishes an entry for the source it read. The
        re-lint reads different bytes, so with the bypass in place it neither
        reads nor writes storage; without it, the re-lint misses and publishes a
        *second* entry for content no planner verified. Two entries therefore
        means the command boundary stopped passing `force_fresh`.

        Counting alone would not say which entry survived, so the payload is
        checked as well: the retained `ir_json` must still describe
        "Paragraph", which is what makes it the warm entry a later plain
        `check` should hit.
        """
        payloads = _entry_payloads(tmp_path)
        assert len(payloads) == 1, (
            "expected only the planning pass's entry; a second means the "
            f"re-lint was cache-eligible, found {len(payloads)}"
        )
        assert "Paragraph" in str(payloads[0].get("ir_json")), (
            "expected the retained entry to describe the pre-fix source"
        )
        assert "Section" not in str(payloads[0].get("ir_json")), (
            "expected no entry to describe the repaired bytes"
        )

    def test_a_warm_entry_for_the_repaired_bytes_is_not_read(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        close_cache_services: CacheServiceRegistrar,
    ) -> None:
        """Bypass covers the read half, not just publication.

        The cold case above only proves the re-lint writes nothing. A run that
        *read* a stale entry and then declined to write would leave that test
        green and the user reading diagnostics for a document that no longer
        exists. So warm the cache with the repaired bytes first and then run
        the fix, which is the shape that can distinguish the two.

        Counting alone cannot tell a served hit from a recorded bypass, so the
        extractor is injected and asked directly: the planning pass must
        receive the pre-fix bytes and the re-lint the repaired ones. The warm
        entry's own bytes are compared before and after as well, because a
        re-lint that rewrote it would leave the counters looking correct while
        destroying the entry a later plain `check` should hit.

        The counters are also asserted: `cache_hits` must stay at zero and
        `cache_bypasses` must count the fresh re-lint. The summary is emitted
        at INFO on the extraction logger, so the assertion reads it through a
        `caplog` level rather than through `run_check`'s `--verbose` handler,
        which `basicConfig` declines to install once pytest owns the root.
        """
        calls: list[str] = []
        service = _counting_service(tmp_path, calls, close_cache_services)
        monkeypatch.chdir(tmp_path)
        _warm_the_cache(tmp_path, service, calls)
        warm_files = _entry_files(tmp_path)

        with caplog.at_level(logging.INFO, logger="stilyagi.cache.extraction"):
            _repair_the_target(tmp_path, service)

        assert calls == [AFTER, BEFORE, AFTER], (
            "expected the planning pass to read the pre-fix bytes and the "
            f"re-lint the repaired ones, got {calls}"
        )
        after = _entry_files(tmp_path)
        assert len(after) == 2, (
            "expected the warm entry plus the planning pass's entry, found "
            f"{len(after)}; a third means the re-lint published for bytes no "
            "planner verified"
        )
        for name, content in warm_files.items():
            assert after.get(name) == content, (
                f"expected the warm entry {name} to survive the fix unchanged"
            )

        hits, bypasses = _counters(caplog.records)
        assert hits == 0, (
            "expected the re-lint to bypass the warm entry for the repaired "
            f"bytes rather than read it, got hits={hits}"
        )
        assert bypasses == 1, (
            f"expected exactly one bypass, the post-fix re-lint, got {bypasses}"
        )
