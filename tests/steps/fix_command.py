"""Shared BDD steps for the `stilyagi check --fix` command.

The scenarios here exercise the mutating half of the fix workflow through the
same in-process command boundary the `check` scenarios use. Every "a rule
offering ..." step injects a stub through `CheckCollaborators.rule_runner`, and
the stub's byte offsets are derived from the real extracted IR through
`tests/support/fix_fixtures.py`, so a scenario can never pass by describing a
document the extractor would not have produced.
"""

import collections.abc as cabc
import io
import pathlib
import sys
import typing as typ

import pytest
from pytest_bdd import given, parsers, then, when
from stilyagi import cli, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.fix_fixtures import (
    NoUnclaimedByteError,
    SourceTextNotFoundError,
    find_source_span,
    find_unclaimed_span,
)

#: The one paragraph the safe and unsafe rules rewrite, and the text they
#: replace it with. Named so the scenarios and the assertions cannot drift.
_SOURCE_TEXT = "Paragraph text.\n"
_REPAIRED_TEXT = "Section text.\n"


class FixCommandState(typ.TypedDict, total=False):
    """State shared across the `stilyagi check --fix` scenarios."""

    root: pathlib.Path
    target: pathlib.Path
    original: bytes
    exit_code: int
    stdout: str
    stderr: str


def _write_source(root: pathlib.Path, text: bytes) -> pathlib.Path:
    """Write the scenario's one Markdown file and return its path."""
    target = root / "notes.md"
    target.write_bytes(text)
    return target


def _state_with_source(root: pathlib.Path, text: bytes) -> FixCommandState:
    """Build the shared state for a tree holding one known Markdown file."""
    target = _write_source(root, text)
    return {"root": root, "target": target, "original": text}


def _safe_paragraph_rule() -> _RuleRunner:
    """Return the safe rule the straightforward scenarios inject.

    A factory rather than a constant so the edit is derived per run, exactly
    as a real rule would: `--fix` re-lints through the same injected runner.

    Returns
    -------
    _RuleRunner
        A runner offering the safe paragraph replacement.
    """
    return _span_edit("Paragraph", "Section", Applicability.SAFE)


def _rule_scenario(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    runner: _RuleRunner,
    text: bytes = _SOURCE_TEXT.encode(),
) -> FixCommandState:
    """Inject one stubbed rule runner and lay down the scenario's file."""
    monkeypatch.setattr(cli.rules_registry, "run_rules", runner)
    return _state_with_source(tmp_path, text)


@given(
    "a Markdown file and a rule offering one safe source-backed fix",
    target_fixture="fix_command_state",
)
def a_markdown_file_and_a_safe_rule(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Create one file whose only finding is safely rewritable."""
    return _rule_scenario(tmp_path, monkeypatch, runner=_safe_paragraph_rule())


@given(
    "a Markdown file and a rule offering one unsafe source-backed fix",
    target_fixture="fix_command_state",
)
def a_markdown_file_and_an_unsafe_rule(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Create one file whose only finding is withheld until the opt-in."""
    return _rule_scenario(
        tmp_path,
        monkeypatch,
        runner=_span_edit("Paragraph", "Section", Applicability.UNSAFE),
    )


@given(
    "a Markdown file and a rule offering a fix over a soft line break",
    target_fixture="fix_command_state",
)
def a_markdown_file_and_a_synthetic_span_rule(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Offer an edit over bytes the IR does not claim as source-backed."""
    return _rule_scenario(
        tmp_path,
        monkeypatch,
        runner=_synthetic_span_edit(),
        text=b"First line\nsecond line.\n",
    )


@given(
    "a Markdown file and two rules offering different edits to one span",
    target_fixture="fix_command_state",
)
def a_markdown_file_and_two_conflicting_rules(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Offer two different replacements for the same source bytes."""
    return _rule_scenario(
        tmp_path,
        monkeypatch,
        runner=_two_rules(
            _span_edit("Paragraph", "Section", Applicability.SAFE, code="PUN201"),
            _span_edit("Paragraph", "Passage", Applicability.SAFE, code="PUN202"),
        ),
    )


@given(
    "a Markdown file and two rules offering the identical edit",
    target_fixture="fix_command_state",
)
def a_markdown_file_and_two_identical_rules(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Offer the same replacement twice, which must coalesce into one edit."""
    return _rule_scenario(
        tmp_path,
        monkeypatch,
        runner=_two_rules(
            _span_edit("Paragraph", "Section", Applicability.SAFE, code="PUN201"),
            _span_edit("Paragraph", "Section", Applicability.SAFE, code="PUN202"),
        ),
    )


@given(
    "a CRLF Markdown file and a rule offering one safe source-backed fix",
    target_fixture="fix_command_state",
)
def a_crlf_markdown_file_and_a_safe_rule(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Create one CRLF file so the write must preserve its line endings."""
    monkeypatch.setattr(cli.rules_registry, "run_rules", _safe_paragraph_rule())
    return _state_with_source(tmp_path, b"Paragraph text.\r\n")


@given(
    "a Markdown file named notes.md on disk",
    target_fixture="fix_command_state",
)
def a_markdown_file_named_notes_on_disk(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Create the file a stream input must never overwrite (D-05)."""
    monkeypatch.setattr(cli.rules_registry, "run_rules", _safe_paragraph_rule())
    return _state_with_source(tmp_path, _SOURCE_TEXT.encode())


@given(
    "a tree holding two Markdown files and an injected rule",
    target_fixture="fix_command_state",
)
def a_tree_holding_two_markdown_files(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FixCommandState:
    """Create a discoverable tree whose flags are rejected before any check.

    The rule never runs: `_FIX_DIFF_CONFLICT` is decided before discovery, so
    this step exists to give the rejected invocation a real tree rather than to
    produce a finding. The scenario is defined here instead of reusing the
    check command's tree step because both modules would otherwise define
    `I run "{command}" in that tree` and collide at collection time.

    Returns
    -------
    FixCommandState
        The shared state for the freshly written tree.
    """
    monkeypatch.setattr(cli.rules_registry, "run_rules", _safe_paragraph_rule())
    for name in ("alpha", "beta"):
        path = tmp_path / "docs" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name.title()}\n", encoding="utf-8")
    return {"root": tmp_path}


@when(parsers.parse('the fix command "{command}" runs in that tree'))
def run_stilyagi_command_in_that_tree(
    fix_command_state: FixCommandState,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    """Run one quoted `stilyagi` invocation in-process and capture it."""
    program, *argv = command.split()
    assert program == "stilyagi", f"unsupported command: {command}"
    if "-" in argv:
        monkeypatch.setattr(sys, "stdin", io.StringIO(_SOURCE_TEXT))
    monkeypatch.chdir(fix_command_state["root"])
    fix_command_state["exit_code"] = cli.main(argv)
    captured = capsys.readouterr()
    fix_command_state["stdout"] = captured.out
    fix_command_state["stderr"] = captured.err


@then("the fix command exits with code 0")
def the_fix_command_exits_with_code_zero(fix_command_state: FixCommandState) -> None:
    """Assert the run left nothing standing."""
    assert_with_context(
        fix_command_state["exit_code"] == 0,
        "expected fix_command_state['exit_code'] == 0",
    )


@then("the fix command exits with code 1")
def the_fix_command_exits_with_code_one(fix_command_state: FixCommandState) -> None:
    """Assert the run still reports a finding."""
    assert_with_context(
        fix_command_state["exit_code"] == 1,
        "expected fix_command_state['exit_code'] == 1",
    )


@then("the fix command exits with code 2")
def the_fix_command_exits_with_code_two(fix_command_state: FixCommandState) -> None:
    """Assert the run failed as an operational or usage error."""
    assert_with_context(
        fix_command_state["exit_code"] == 2,
        "expected fix_command_state['exit_code'] == 2",
    )


@then("standard output holds a unified diff that git apply accepts")
def standard_output_holds_an_applicable_unified_diff(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the patch names both sides of the rewrite in diff form."""
    stdout = fix_command_state["stdout"]
    assert_with_context(
        stdout.startswith("--- a/notes.md\n+++ b/notes.md\n"),
        "expected a unified diff header on standard output",
    )
    assert_with_context(
        "-Paragraph text.\n" in stdout and "+Section text.\n" in stdout,
        "expected the patch to show the planned replacement",
    )


@then("standard error holds the diagnostic summary")
def standard_error_holds_the_diagnostic_summary(
    fix_command_state: FixCommandState,
) -> None:
    """Assert diagnostics stay off the stream the patch owns."""
    assert_with_context(
        "PUN201" in fix_command_state["stderr"],
        "expected the diagnostic to be summarised on standard error",
    )
    assert_with_context(
        "git apply" not in fix_command_state["stderr"],
        "expected a patch-only standard output for the diff preview",
    )


@then("the Markdown file on disk is unchanged")
def the_markdown_file_on_disk_is_unchanged(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the target still holds exactly the bytes it was created with."""
    on_disk = fix_command_state["target"].read_bytes()
    assert_with_context(
        on_disk == fix_command_state["original"],
        "expected the Markdown file on disk to be byte-identical",
    )


@then("the Markdown file on disk contains the repaired text")
def the_markdown_file_on_disk_contains_the_repaired_text(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the planned replacement reached the filesystem."""
    on_disk = fix_command_state["target"].read_bytes()
    assert_with_context(
        b"Section text." in on_disk,
        "expected the repaired text to be written to the file",
    )


@then("the text output offers the --unsafe-fixes option")
def the_text_output_offers_the_unsafe_fixes_option(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the D-15 affordance names the flag that widens the selection."""
    assert_with_context(
        "--unsafe-fixes" in fix_command_state["stderr"],
        "expected standard error to name --unsafe-fixes",
    )


@then("the text output reports a synthetic-span fix error")
def the_text_output_reports_a_synthetic_span_fix_error(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the refusal is attributed and the file was left alone.

    The report is read from both streams: nothing was written, so this run is
    deliberately byte-identical to a plain check and its report goes to the
    normal diagnostics stream rather than to the mutation stream.
    """
    output = fix_command_state["stdout"] + fix_command_state["stderr"]
    assert_with_context(
        "fix-error/synthetic-span" in output,
        "expected a synthetic-span fix error in the text output",
    )


@then("the text output reports an overlapping-edits fix error naming both rules")
def the_text_output_reports_an_overlapping_edits_fix_error(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the conflict names every rule that could not be applied."""
    output = fix_command_state["stdout"] + fix_command_state["stderr"]
    assert_with_context(
        "fix-error/overlapping-edits" in output,
        "expected an overlapping-edits fix error in the text output",
    )
    assert_with_context(
        "PUN201" in output and "PUN202" in output,
        "expected the conflict to name both contributing rules",
    )


@then("the text output states that the file was not modified")
def the_text_output_states_the_file_was_not_modified(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the refusal says what happened to the file, not just why."""
    output = fix_command_state["stdout"] + fix_command_state["stderr"]
    assert_with_context(
        "file was not modified" in output,
        "expected the refusal to state the file remained untouched",
    )


@then("the Markdown file on disk still uses CRLF line endings")
def the_markdown_file_on_disk_still_uses_crlf(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the write did not normalise the file's line endings."""
    on_disk = fix_command_state["target"].read_bytes()
    assert_with_context(
        on_disk.endswith(b"\r\n") and b"\n\n" not in on_disk.removesuffix(b"\r\n"),
        "expected the repaired file to keep CRLF line endings",
    )


@then("only the repaired bytes differ")
def only_the_repaired_bytes_differ(fix_command_state: FixCommandState) -> None:
    """Assert the patch is exactly the one replacement it promised."""
    original = fix_command_state["original"]
    on_disk = fix_command_state["target"].read_bytes()
    assert_with_context(
        on_disk == original.replace(b"Paragraph", b"Section"),
        "expected the only difference to be the planned replacement",
    )


@then("the fixed document is written to standard output")
def the_fixed_document_is_written_to_standard_output(
    fix_command_state: FixCommandState,
) -> None:
    """Assert a stream input's repair reaches the user, not the disk (D-05)."""
    assert_with_context(
        fix_command_state["stdout"] == _REPAIRED_TEXT,
        "expected the fixed document alone on standard output",
    )


@then("the standard error reports that --fix and --diff conflict")
def the_standard_error_reports_the_fix_diff_conflict(
    fix_command_state: FixCommandState,
) -> None:
    """Assert the rejected flag pair is named rather than silently resolved."""
    assert_with_context(
        "--fix and --diff cannot be combined" in fix_command_state["stderr"],
        "expected standard error to name the conflicting flags",
    )


#: The callable shape the check pipeline accepts as its injected rule runner.
type _RuleRunner = cabc.Callable[
    [model.Document, config.StilyagiConfig], list[diagnostics.Diagnostic]
]

#: The callable that derives one diagnostic's edit from the extracted document.
#: Returning ``None`` means the edit cannot be offered against this document.
type _EditMaker = cabc.Callable[
    [model.Document, config.StilyagiConfig], diagnostics.Diagnostic | None
]


def _rule_offering(make_edit: _EditMaker) -> _RuleRunner:
    """Return a rule runner that offers at most one edit.

    Every stub built here is idempotent by construction: `--fix` re-lints the
    files it wrote using the same injected runner, so a stub that re-derives an
    edit from a needle the rewrite already removed would raise on the second
    pass. An edit maker that cannot find its needle contributes no diagnostic,
    which is what a real rule does with source text it no longer matches.

    Returns
    -------
    _RuleRunner
        A runner wrapping the supplied edit maker.
    """

    def run(
        document: model.Document,
        resolved_config: config.StilyagiConfig,
    ) -> list[diagnostics.Diagnostic]:
        """Return one diagnostic, or none once the edit no longer applies."""
        diagnostic = make_edit(document, resolved_config)
        return [] if diagnostic is None else [diagnostic]

    return run


def _span_edit(
    needle: str,
    replacement: str,
    applicability: Applicability,
    *,
    code: str = "PUN201",
) -> _RuleRunner:
    """Return a rule that replaces one source-backed needle with new text."""

    def make_edit(
        document: model.Document,
        _config: config.StilyagiConfig,
    ) -> diagnostics.Diagnostic | None:
        """Build the diagnostic, or none when the needle is gone."""
        try:
            span = find_source_span(document, needle)
        except SourceTextNotFoundError:
            return None
        return diagnostics.Diagnostic(
            path="notes.md",
            code=code,
            message="Synthetic fix.",
            severity=diagnostics.Severity.ERROR,
            fix=Fix(
                "Synthetic fix",
                applicability,
                (TextEdit.replace(span, replacement),),
            ),
        )

    return _rule_offering(make_edit)


def _synthetic_span_edit(
    applicability: Applicability = Applicability.SAFE,
    *,
    code: str = "PUN201",
) -> _RuleRunner:
    """Return a rule editing bytes the extractor does not claim as source.

    The range is measured from the document rather than hard-coded, so the rule
    always offers a genuinely synthetic span: an invented offset would land
    inside a real span for one input and the admissibility check would accept
    it, letting the scenario pass without exercising the refusal at all.

    Returns
    -------
    _RuleRunner
        A runner offering one edit over an unclaimed byte range.
    """

    def make_edit(
        document: model.Document,
        _config: config.StilyagiConfig,
    ) -> diagnostics.Diagnostic | None:
        """Build the diagnostic over the document's first unclaimed byte."""
        try:
            span = find_unclaimed_span(document)
        except NoUnclaimedByteError:
            return None
        return diagnostics.Diagnostic(
            path="notes.md",
            code=code,
            message="Synthetic fix.",
            severity=diagnostics.Severity.ERROR,
            fix=Fix("Synthetic fix", applicability, (TextEdit.replace(span, ""),)),
        )

    return _rule_offering(make_edit)


def _two_rules(*rules: _RuleRunner) -> _RuleRunner:
    """Return one runner whose rules each offer their own edit.

    Composing runners rather than specs keeps every constituent rule the same
    idempotent object used on its own, so the conflict scenarios differ from
    the single-rule ones only in how many rules contribute.

    Returns
    -------
    _RuleRunner
        A runner that concatenates each constituent rule's diagnostics.
    """

    def run(
        document: model.Document,
        resolved_config: config.StilyagiConfig,
    ) -> list[diagnostics.Diagnostic]:
        """Return every constituent rule's diagnostics for this document."""
        return [
            diagnostic
            for rule in rules
            for diagnostic in rule(document, resolved_config)
        ]

    return run
