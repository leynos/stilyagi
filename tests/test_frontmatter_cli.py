"""CLI-level proof that Markdown repairs retain YAML frontmatter bytes."""

import typing as typ

import pytest
from stilyagi import cli, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.fix_fixtures import find_source_span

if typ.TYPE_CHECKING:
    import pathlib

    from stilyagi.rules.registry import RuleRunner

_FRONTMATTER_SOURCE = (
    b"---\r\n"
    b'title: "Caf\xc3\xa9"\r\n'
    b"# Preserve this comment\r\n"
    b"quoted: 'a: b'\r\n"
    b"description: |\r\n"
    b"  first line\r\n"
    b"---\r\n"
    b"\r\n"
    b"Paragraph text.\r\n"
)


def _body_fix_runner(
    reported_path: str,
    applicability: Applicability,
) -> RuleRunner:
    """Offer a body-only edit that disappears after successful repair."""

    def run_rules(
        document: model.Document,
        _resolved_config: config.StilyagiConfig,
    ) -> list[diagnostics.Diagnostic]:
        """Return the diagnostic only while its source-backed body text exists."""
        try:
            span = find_source_span(document, "Paragraph text.")
        except ValueError:
            return []
        return [
            diagnostics.Diagnostic(
                path=reported_path,
                code="PUN201",
                message="Rewrite the sample paragraph.",
                severity=diagnostics.Severity.ERROR,
                fix=Fix(
                    "Rewrite the sample paragraph",
                    applicability,
                    (TextEdit.replace(span, "Section text."),),
                ),
            )
        ]

    return run_rules


@pytest.mark.parametrize(
    "repair_case",
    [
        pytest.param((".md", Applicability.SAFE), id="safe-md"),
        pytest.param((".markdown", Applicability.SAFE), id="safe-markdown"),
        pytest.param((".mdc", Applicability.SAFE), id="safe-mdc"),
        pytest.param((".md", Applicability.UNSAFE), id="unsafe-opt-in-md"),
        pytest.param((".markdown", Applicability.UNSAFE), id="unsafe-opt-in-markdown"),
        pytest.param((".mdc", Applicability.UNSAFE), id="unsafe-opt-in-mdc"),
    ],
)
def test_cli_repairs_the_body_and_preserves_frontmatter_bytes(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    repair_case: tuple[str, Applicability],
) -> None:
    """Keep the complete LF/CRLF YAML prefix through a real check/fix pass."""
    suffix, applicability = repair_case
    monkeypatch.chdir(tmp_path)
    target = tmp_path / f"notes{suffix}"
    target.write_bytes(_FRONTMATTER_SOURCE)
    prefix_end = _FRONTMATTER_SOURCE.index(b"Paragraph text.")
    original_prefix = _FRONTMATTER_SOURCE[:prefix_end]
    monkeypatch.setattr(
        cli.rules_registry,
        "run_rules",
        _body_fix_runner(target.name, applicability),
    )

    exit_code = cli.run_check(
        cli.CheckOptions(
            targets=(target.name,),
            fix=True,
            no_cache=True,
            unsafe_fixes=applicability is Applicability.UNSAFE,
        )
    )
    output = capsys.readouterr()
    repaired = target.read_bytes()

    assert exit_code == 0, "expected the repaired file to pass verification"
    assert repaired.startswith(original_prefix), (
        "expected every original frontmatter byte and closing line ending"
    )
    assert repaired[prefix_end:] == b"Section text.\r\n", (
        "expected the body edit to preserve CRLF line endings"
    )
    assert "1 files fixed, 1 fixes applied" in output.err, (
        "expected the CLI to report its repair"
    )


def _frontmatter_edit_runner(
    reported_path: str,
    source: bytes,
    edit_kind: str,
) -> RuleRunner:
    """Offer one edit that targets or crosses the protected YAML prefix."""

    def run_rules(
        document: model.Document,
        _resolved_config: config.StilyagiConfig,
    ) -> list[diagnostics.Diagnostic]:
        """Build the requested unsafe candidate from actual IR spans."""
        title = find_source_span(document, "Café")
        body = find_source_span(document, "Paragraph text.")
        match edit_kind:
            case "frontmatter-value":
                edit = TextEdit.replace(title, "Tea")
            case "closing-boundary":
                fence = source.index(b"\r\n---\r\n") + len(b"\r\n---")
                edit = TextEdit(fence, fence, "!")
            case "cross-boundary":
                edit = TextEdit(title.byte_start, body.byte_end, "rewritten")
            case "opening-boundary":
                edit = TextEdit(0, 0, "!")
            case _:
                raise ValueError(edit_kind)
        return [
            diagnostics.Diagnostic(
                path=reported_path,
                code="PUN202",
                message="An unsafe frontmatter edit was proposed.",
                severity=diagnostics.Severity.ERROR,
                fix=Fix(
                    "Edit protected metadata",
                    Applicability.SAFE,
                    (edit,),
                ),
            )
        ]

    return run_rules


@pytest.mark.parametrize(
    "edit_kind",
    [
        pytest.param("frontmatter-value", id="metadata-value"),
        pytest.param("closing-boundary", id="closing-fence-boundary"),
        pytest.param("cross-boundary", id="metadata-through-body"),
        pytest.param("opening-boundary", id="opening-fence-boundary"),
    ],
)
def test_cli_refuses_edits_to_or_across_frontmatter(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    edit_kind: str,
) -> None:
    """Refuse frontmatter and boundary edits before writing any source bytes."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "notes.mdc"
    target.write_bytes(_FRONTMATTER_SOURCE)
    original = target.read_bytes()
    monkeypatch.setattr(
        cli.rules_registry,
        "run_rules",
        _frontmatter_edit_runner(target.name, original, edit_kind),
    )

    exit_code = cli.run_check(
        cli.CheckOptions(targets=(target.name,), fix=True, no_cache=True)
    )
    output = capsys.readouterr()

    assert exit_code == 1, "expected the remaining diagnostic to keep exit code one"
    assert target.read_bytes() == original, (
        "expected the rejected plan to leave bytes intact"
    )
    assert "fix-error/frontmatter-protected" in output.out, (
        "expected the refusal to identify protected frontmatter"
    )
