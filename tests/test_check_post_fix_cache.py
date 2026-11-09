"""Command-boundary coverage for the post-fix extraction-cache bypass.

`cli_run.relint_written_files` re-checks the files a `--fix` run wrote, and it
sets `force_fresh=True` so that re-check reads the bytes now on disk rather
than a warm entry for the bytes they replaced. The extraction service's own
tests prove a `force_fresh` request bypasses storage; they cannot prove the
command boundary asks for one.

That distinction matters because the two failures look the same from the cache
tests and different from the user's terminal. A missing `force_fresh` leaves
the re-lint reporting the *pre-fix* document, so a repaired file is described
by diagnostics that no longer apply -- and the re-lint publishes a cache entry
for content it never verified. This module drives `cli.run_check`, so the flag
is exercised where it is set.

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
from stilyagi.cache.model import CACHE_NAMESPACE_NAME, OWNER_MARKER_NAME
from stilyagi.cli_args import CheckOptions
from stilyagi.fixes import Applicability, Fix, TextEdit

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
    ) -> None:
        """Bypass covers the read half, not just publication.

        The cold case above only proves the re-lint writes nothing. A run that
        *read* a stale entry and then declined to write would leave that test
        green and the user reading diagnostics for a document that no longer
        exists. So warm the cache with the repaired bytes first and then run
        the fix, which is the shape that can distinguish the two.

        The counters are the signal: `cache_hits` must stay at zero and
        `cache_bypasses` must count the fresh re-lint. The summary is emitted
        at INFO on the extraction logger, so the assertion reads it through a
        `caplog` level rather than through `run_check`'s `--verbose` handler,
        which `basicConfig` declines to install once pytest owns the root.
        """
        (tmp_path / "notes.md").write_text(AFTER, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        with contextlib.redirect_stderr(io.StringIO()):
            assert cli.run_check(CheckOptions(targets=("notes.md",))) == 0, (
                "expected the warm-up run to succeed"
            )
        warm = _entry_payloads(tmp_path)
        assert len(warm) == 1, (
            f"expected the warm-up to publish one entry, found {len(warm)}"
        )
        assert "Section" in str(warm[0].get("ir_json")), (
            "expected the warm entry to describe the repaired bytes"
        )

        (tmp_path / "notes.md").write_text(BEFORE, encoding="utf-8")
        with caplog.at_level(logging.INFO, logger="stilyagi.cache.extraction"):
            assert (
                cli.run_check(
                    CheckOptions(targets=("notes.md",), fix=True),
                    collaborators=cli.CheckCollaborators(
                        rule_runner=_rewrite_paragraph
                    ),
                )
                == 0
            ), "expected the fix run to succeed"

        summary = [
            record
            for record in caplog.records
            if getattr(record, "operation", None) == "extraction_cache_summary"
        ]
        assert summary, "expected the run to report its cache counters"
        # The counters ride on the record as structured extras rather than in
        # the message, so each one is read by name. Binding them once also
        # keeps the failure messages free of attribute access on a `LogRecord`,
        # which static checkers reject even though the extras are present.
        hits = getattr(summary[-1], "cache_hits", None)
        bypasses = getattr(summary[-1], "cache_bypasses", None)
        assert hits == 0, (
            "expected the re-lint to bypass the warm entry for the repaired "
            f"bytes rather than read it, got hits={hits}"
        )
        assert bypasses == 1, (
            f"expected exactly one bypass, the post-fix re-lint, got {bypasses}"
        )
