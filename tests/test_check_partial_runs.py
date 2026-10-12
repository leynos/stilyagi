"""Command-boundary coverage for a mutating run that only partly succeeded.

A run can write some of what it planned and fail on the rest. That middle
outcome is its own boundary: a refusal always leaves its target alone, so the
run reaches the *mutating* reporter only because something else was written,
and the refusals it has to report arrive by the route that exists solely for
this case. The reporter that serves a run which changed nothing at all is
covered, with the refusals it carries, in `tests/test_check_refusals.py`.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_check_partial_runs.py
"""

import io
import json
import pathlib
import sys
import typing as typ

from stilyagi import cli, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.fix_fixtures import find_source_span

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import pytest


def refuse_one_filename(
    filename: str,
) -> cabc.Callable[[pathlib.Path, pathlib.Path], None]:
    """Build a selective `Path.replace` stand-in for a partial run.

    A blanket stand-in cannot reach the mutating reporter. If every write
    raises, nothing is written, `outcome.changed_anything` is false, and the
    run takes the *unmodified* branch -- which is why the refusals covered in
    `tests/test_check_refusals.py` never need this stand-in. Reaching
    `print_mutation_report` needs a run that both wrote something and refused
    something, so the refusal has to name its target.

    `Path.replace` receives the staged path first and the target second, so the
    target's name is what separates one file from another.

    Returns
    -------
    cabc.Callable[[pathlib.Path, pathlib.Path], None]
        A stand-in that refuses the named target and delegates for every other.
    """
    original_replace = pathlib.Path.replace

    def replace(self: pathlib.Path, target: pathlib.Path, *args: object) -> None:
        """Refuse the named target, and let every other swap proceed."""
        if target.name == filename:
            message = "Read-only file system"
            raise PermissionError(message)
        original_replace(self, target, *args)

    return replace


def plan_one_edit_each(
    document: model.Document,
    _config: config.StilyagiConfig,
) -> list[diagnostics.Diagnostic]:
    """Offer one safe source-backed edit per file, chosen by its own text.

    A runner sees a document and not a path, so the two files are told apart by
    what they contain. Both edits are deliberately *source-backed*: an edit the
    planner rejects outright would be refused in phase one and ride along in
    `checked`, which is the route `tests/test_check_refusals.py` covers. The
    refusal under test here is the one discovered at write time, so both plans
    have to be admissible enough to reach the writing phase.

    The needles also keep the re-lint quiet. It reads `a.md` back as "Section
    text." and `b.md` as "# Memo", matching neither branch, so neither file
    contributes a finding of its own and the refusal under test is the run's
    only one.

    Returns
    -------
    list[diagnostics.Diagnostic]
        One fixable finding for each file that still holds its original text.
    """
    prose = "".join(region.text for region in document.regions)
    if "Paragraph" in prose:
        return [
            diagnostics.Diagnostic(
                path="notes.md",
                code="PUN201",
                message="Use the preferred paragraph term.",
                severity=diagnostics.Severity.WARNING,
                fix=Fix(
                    "Rewrite paragraph",
                    Applicability.SAFE,
                    (
                        TextEdit.replace(
                            find_source_span(document, "Paragraph"), "Section"
                        ),
                    ),
                ),
            )
        ]
    if "Notes" in prose:
        return [
            diagnostics.Diagnostic(
                path="notes.md",
                code="PUN201",
                message="Rename the heading text.",
                severity=diagnostics.Severity.WARNING,
                fix=Fix(
                    "Rename heading",
                    Applicability.SAFE,
                    (TextEdit.replace(find_source_span(document, "Notes"), "Memo"),),
                ),
            )
        ]
    return []


class TestRefusalsInAPartialRun:
    """A run that wrote something still reports what it refused.

    A refused write leaves its target alone, so `outcome.changed_anything` is
    false whenever *every* write is refused, and such a run reports through
    `print_unmodified_report` -- which is the reporter
    `tests/test_check_refusals.py` exercises throughout. The mutating reporter
    is reached only when some write succeeded, which is why it needs a run that
    both wrote a file and refused one. The two are separate code paths, and the
    assessment that prompted this coverage named both.

    The distinction matters because the refusals reach a partial run by a
    second route. A phase-one refusal rides along in the plan and so is visible
    in `checked`; a write failure is discovered after every plan was read and
    exists only in the outcome. A run that reported the first kind alone would
    look correct while silently dropping the second.
    """

    def test_a_refused_write_is_reported_alongside_a_written_file(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Report a filesystem refusal even though the run did write a file.

        Two files, one write allowed and one refused, so the run reaches the
        mutating reporter with a non-empty outcome. The re-lint is silent for
        both files, which makes the refusal the run's only finding: the exit
        status cannot stand in for its presence in the report, so the
        assertions below have to read the output.

        The report is read from standard error rather than from the injected
        stream, because that is where a mutating run puts it: the stream it was
        handed already carries the diagnostics this report supersedes. The
        refused target is left byte-identical, and the summary counts it as
        skipped rather than fixed. All three are asserted because a run that
        reported the refusal while still claiming to have fixed the file would
        satisfy the refusal assertion alone.
        """
        (tmp_path / "a.md").write_text("Paragraph text.\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()
        errors = io.StringIO()
        monkeypatch.setattr(sys, "stderr", errors)

        monkeypatch.setattr(pathlib.Path, "replace", refuse_one_filename("b.md"))

        exit_code = cli.run_check(
            cli.CheckOptions(targets=("a.md", "b.md"), fix=True),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=plan_one_edit_each
            ),
        )

        assert_with_context(
            (tmp_path / "a.md").read_text(encoding="utf-8") == "Section text.\n",
            "expected the permitted write to have happened",
        )
        assert_with_context(
            (tmp_path / "b.md").read_text(encoding="utf-8") == "# Notes\n",
            "expected the refused target to be left exactly as it was",
        )
        report = errors.getvalue()
        assert_with_context(
            "fix-error/write-failed: b.md:" in report,
            f"expected the refused write in the report, got {report!r}",
        )
        assert_with_context(
            "Read-only file system" in report,
            "expected the refusal to carry the filesystem's reason",
        )
        assert_with_context(
            "1 files fixed, 1 fixes applied, 1 files skipped (conflict), "
            "1 fixes rejected" in report,
            "expected the summary to separate the write from the refusal",
        )
        assert exit_code == 2, "expected a refused write to make the run exit two"


def _json_document_in(stream: str) -> str:
    """Return the JSON document a mutating reporter embedded in its stream.

    The document starts at the first ``{`` and runs to the last ``}``. Those
    bounds are used rather than a line offset because the reporter's human
    prose is a prefix, not a suffix: the rerun hint and the console log records
    precede the document, so the tail of the stream is the document's own
    closing brace. Slicing to the last brace is what makes the return value
    fail to parse if a sentence were appended after it -- which is the
    regression under test.

    Returns
    -------
    str
        The document's own text, without the human prose that precedes it.
    """
    return stream[stream.index("{") : stream.rindex("}") + 1]


class TestThePartialRunJsonReportKeepsItsDocumentIntact:
    """A partial run's JSON document is not contaminated by human prose.

    The mutating reporter writes to standard error, which a partial run shares
    with the rerun hint and with console log records. "The stream parses whole"
    is therefore *not* the contract here, and asserting it would encode a
    misunderstanding: the hint and the log are legitimately on that stream. The
    contract is narrower and is what this pins -- the document is emitted
    intact, so the JSON a consumer extracts is parseable, and the summary
    sentence that used to be appended to it is gone.
    """

    def test_a_partial_run_emits_a_parseable_json_document(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Extract the document from the mutating reporter's stream and parse it.

        The summary sentence is asserted *absent* rather than merely not
        required, because a trailing sentence after the closing brace is
        exactly the regression being pinned, and a test that only parsed a
        substring would pass while it was there.
        """
        (tmp_path / "a.md").write_text("Paragraph text.\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# Notes\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        stream = io.StringIO()
        errors = io.StringIO()
        monkeypatch.setattr(sys, "stderr", errors)

        monkeypatch.setattr(pathlib.Path, "replace", refuse_one_filename("b.md"))

        exit_code = cli.run_check(
            cli.CheckOptions(targets=("a.md", "b.md"), fix=True, output_format="json"),
            collaborators=cli.CheckCollaborators(
                output=stream, rule_runner=plan_one_edit_each
            ),
        )

        report = errors.getvalue()
        document = json.loads(_json_document_in(report))
        assert_with_context(
            [refusal["identifier"] for refusal in document["fix_errors"]]
            == ["fix-error/write-failed"],
            f"expected the refused write in {document!r}",
        )
        assert_with_context(
            document["fix_errors"][0]["path"] == "b.md",
            "expected the refusal to name the refused target",
        )
        assert_with_context(
            "files fixed," not in report,
            f"expected no summary sentence beside the document, got {report!r}",
        )
        assert exit_code == 2, "expected a partial run to exit two"
