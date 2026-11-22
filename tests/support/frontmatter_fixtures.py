"""Shared YAML-frontmatter source and rule stand-in for repair contracts.

The planner contracts in `test_fix_frontmatter.py` call the planner directly.
The command-level contracts in `test_frontmatter_cli.py` and the
`markdown_frontmatter_repair` scenario instead drive a real `check --fix` run,
and both need the same two things: one source carrying every YAML shape the
plan names, and a rule that offers a single body-only edit. Keeping them here
means the two command-level suites cannot drift into testing different
documents, and a change to the run-request contract is repaired once.
"""

import typing as typ

from stilyagi import diagnostics
from stilyagi.fixes import Applicability, Fix, TextEdit

from tests.support.fix_fixtures import find_source_span

if typ.TYPE_CHECKING:
    from stilyagi.rules.registry import RuleRunner, RuleRunRequest

FRONTMATTER_SOURCE = (
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

#: The body text the stand-in rule diagnoses, and the bytes it replaces it
#: with. The replacement keeps the CRLF ending the surrounding document uses.
BODY_TEXT = "Paragraph text."
REPLACED_BODY = b"Section text.\r\n"


def body_fix_runner(
    reported_path: str,
    applicability: Applicability = Applicability.SAFE,
) -> RuleRunner:
    """Return a rule that diagnoses the body text while its bytes survive.

    The diagnostic names a span found in the document's own IR provenance, so
    the offsets the planner splices are the extractor's rather than ones the
    test invented. It stands down once the replacement means its needle is
    gone, which is what lets a re-check after a repair come back clean.

    Parameters
    ----------
    reported_path:
        Path to attribute the diagnostic to; the run's reported identity for
        the file.
    applicability:
        Applicability the offered fix claims, so a case can prove that an
        unsafe edit still needs the unsafe opt-in.

    Returns
    -------
    RuleRunner
        A one-argument rule runner matching the pipeline's request contract.

    Examples
    --------
    >>> from tests.support.frontmatter_fixtures import body_fix_runner
    >>> callable(body_fix_runner("notes.mdc"))
    True
    """

    def run_rules(request: RuleRunRequest) -> list[diagnostics.Diagnostic]:
        """Return the diagnostic only while its source-backed body text exists."""
        try:
            span = find_source_span(request.document, BODY_TEXT)
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
