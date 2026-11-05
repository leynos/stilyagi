"""Pytest-BDD steps for a real YAML-frontmatter repair at the command boundary.

This scenario runs `check --fix` over a real temporary component file rather
than a subprocess. The rule runner is injected through the same documented
`CheckCollaborators` seam the fix-command scenarios use, because the built-in
rule registry is still empty: a process-boundary run would have no fixable
diagnostic to apply, and the scenario would pass by doing nothing.

The injected rule derives its edit from the real extracted IR, so the splice
offsets are the ones the production extractor produced, not ones the test
invented.
"""

import pathlib
import typing as typ

import pytest
from pytest_bdd import given, then, when
from stilyagi import cli, config, diagnostics, model
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.fix_fixtures import find_source_span

if typ.TYPE_CHECKING:
    from stilyagi.rules.registry import RuleRunner

_REPORTED_NAME = "notes.mdc"

#: A CRLF fenced prefix carrying every YAML shape the plan names: a quoted
#: scalar, a comment, a single-quoted scalar containing a colon, and a
#: multiline value.
_FRONTMATTER_SOURCE = (
    b"---\r\n"
    + 'title: "Café"\r\n'.encode()
    + b"# Preserve this comment\r\n"
    + b"quoted: 'a: b'\r\n"
    + b"description: |\r\n"
    + b"  first line\r\n"
    + b"---\r\n"
    + b"\r\n"
    + b"Paragraph text.\r\n"
)

#: The body text the repair replaces, and the bytes it is replaced with. The
#: replacement keeps the CRLF ending the surrounding document already uses.
_BODY_TEXT = "Paragraph text."
_REPLACED_BODY = b"Section text.\r\n"


class FrontmatterRepairState(typ.TypedDict, total=False):
    """Carry the target, its original bytes, and the run's observable result."""

    root: pathlib.Path
    target: pathlib.Path
    original: bytes
    prefix: bytes
    exit_code: int
    repaired: bytes


def _body_fix_runner(reported_path: str) -> RuleRunner:
    """Offer a body-only edit that disappears once the repair has applied."""

    def run_rules(
        document: model.Document,
        _resolved_config: config.StilyagiConfig,
    ) -> list[diagnostics.Diagnostic]:
        """Return the diagnostic only while its source-backed body text exists."""
        try:
            span = find_source_span(document, _BODY_TEXT)
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
                    Applicability.SAFE,
                    (TextEdit.replace(span, "Section text."),),
                ),
            )
        ]

    return run_rules


@given(
    "an mdc file with YAML frontmatter and a fixable body diagnostic",
    target_fixture="frontmatter_repair_state",
)
def mdc_file_with_fixable_body_diagnostic(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FrontmatterRepairState:
    """Create the component file and inject the rule that proposes its repair."""
    monkeypatch.chdir(tmp_path)
    target = tmp_path / _REPORTED_NAME
    target.write_bytes(_FRONTMATTER_SOURCE)
    monkeypatch.setattr(
        cli.rules_registry,
        "run_rules",
        _body_fix_runner(_REPORTED_NAME),
    )
    return {
        "root": tmp_path,
        "target": target,
        "original": _FRONTMATTER_SOURCE,
        "prefix": _FRONTMATTER_SOURCE[: _FRONTMATTER_SOURCE.index(_BODY_TEXT.encode())],
    }


@when("I apply the body fix")
def apply_the_body_fix(frontmatter_repair_state: FrontmatterRepairState) -> None:
    """Run the real mutating command over the prepared component file."""
    target = frontmatter_repair_state["target"]
    frontmatter_repair_state["exit_code"] = cli.run_check(
        cli.CheckOptions(targets=(target.name,), fix=True, no_cache=True)
    )
    frontmatter_repair_state["repaired"] = target.read_bytes()


@then("the body is repaired")
def the_body_is_repaired(frontmatter_repair_state: FrontmatterRepairState) -> None:
    """Require a real body rewrite and a clean post-fix verification pass."""
    repaired = frontmatter_repair_state["repaired"]
    prefix = frontmatter_repair_state["prefix"]
    assert repaired != frontmatter_repair_state["original"], (
        "expected the run to change the file"
    )
    assert repaired[len(prefix) :] == _REPLACED_BODY, (
        "expected the body edit to replace exactly the diagnosed paragraph"
    )
    assert frontmatter_repair_state["exit_code"] == 0, (
        "expected the repaired file to pass verification"
    )


@then("the entire frontmatter prefix is byte-identical")
def the_frontmatter_prefix_is_byte_identical(
    frontmatter_repair_state: FrontmatterRepairState,
) -> None:
    """Compare the written prefix with the original, byte for byte."""
    repaired = frontmatter_repair_state["repaired"]
    prefix = frontmatter_repair_state["prefix"]
    assert repaired.startswith(prefix), (
        "expected every original frontmatter byte and its closing line ending"
    )
    assert prefix.startswith(b"---\r\n"), (
        "expected the protected prefix to open with a fenced YAML block"
    )
    assert b"\r\n---\r\n" in prefix, (
        "expected the protected prefix to span the whole fenced block"
    )
