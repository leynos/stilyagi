"""Behavioural contracts for frontmatter-protected fix planning."""

import typing as typ

from stilyagi import config, diagnostics, engine, model
from stilyagi.engine.fix_planning.frontmatter import edit_conflicts_with_frontmatter
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import Applicability, Fix, FixLevel, TextEdit

from tests.support.fix_fixtures import find_source_span


def _request(
    source: str,
    document: model.Document,
    candidates: tuple[diagnostics.Diagnostic, ...],
) -> FixPlanRequest:
    """Build a safe-level planner request for one frontmatter contract."""
    return FixPlanRequest(
        source.encode(),
        document,
        candidates,
        FixLevel.SAFE,
        config.LintConfig(),
    )


def _diagnostic(code: str, fix: Fix) -> diagnostics.Diagnostic:
    """Build one rule diagnostic carrying a candidate fix."""
    return diagnostics.Diagnostic("docs/example.md", code, "example", fix=fix)


def test_frontmatter_guard_rejects_invalid_edit_objects() -> None:
    """Treat malformed edits as unsafe even when frontmatter is absent."""
    invalid_edit = typ.cast("TextEdit", object())

    assert edit_conflicts_with_frontmatter(invalid_edit, None), (
        "expected the safety guard to reject values outside the TextEdit contract"
    )


def test_planner_rejects_edits_inside_yaml_frontmatter() -> None:
    """Refuse replacements and opening-boundary insertions in YAML metadata."""
    source = "---\r\ntitle: Café\r\n---\r\n\nHello world\r\n"
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    title = find_source_span(document, "Café")
    candidates = (
        _diagnostic(
            "PUN201",
            Fix("Change title", Applicability.SAFE, (TextEdit.replace(title, "Tea"),)),
        ),
        _diagnostic(
            "PUN202",
            Fix("Insert before metadata", Applicability.SAFE, (TextEdit(0, 0, "x"),)),
        ),
    )

    plans = tuple(
        plan_fixes(_request(source, document, (candidate,))) for candidate in candidates
    )

    assert all(plan.fixed_bytes is None for plan in plans), (
        "expected every YAML-overlapping candidate to be refused"
    )
    assert all(
        plan.rejections[0].identifier == "fix-error/frontmatter-protected"
        for plan in plans
    ), "expected every candidate to identify the protected frontmatter"


def test_planner_refuses_a_whole_bundle_that_edits_yaml_and_body() -> None:
    """A protected metadata edit must reject every edit in its fix bundle."""
    source = "---\ntitle: Café\n---\n\nHello world\n"
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    title = find_source_span(document, "Café")
    body = find_source_span(document, "world")
    candidate = _diagnostic(
        "PUN201",
        Fix(
            "Change metadata and prose",
            Applicability.SAFE,
            (TextEdit.replace(title, "Tea"), TextEdit.replace(body, "earth")),
        ),
    )

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert not plan.edits, "expected the entire fix bundle to be refused"
    assert plan.fixed_bytes is None, "expected no replacement bytes after refusal"
    assert plan.rejections[0].identifier == "fix-error/frontmatter-protected", (
        "expected the mixed metadata and prose bundle rejection"
    )


def test_planner_preserves_crlf_frontmatter_and_allows_insertion_after_it() -> None:
    """Keep the exact CRLF fenced prefix while permitting a safe body insertion."""
    source = "---\r\ntitle: Café\r\n---\r\n\nHello world\r\n"
    source_bytes = source.encode()
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    frontmatter = find_source_span(document, "---\r\ntitle: Café\r\n---")
    protected_end = frontmatter.byte_end + len(b"\r\n")
    insertion = TextEdit(protected_end, protected_end, "Added text.\n")
    candidate = _diagnostic(
        "PUN201", Fix("Add body text", Applicability.SAFE, (insertion,))
    )

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert plan.fixed_bytes == (
        source_bytes[:protected_end] + b"Added text.\n" + source_bytes[protected_end:]
    ), "expected the insertion to preserve the original CRLF metadata prefix"


def test_planner_rejects_removal_of_the_frontmatter_closing_line_ending() -> None:
    """Treat the closing fence's CRLF separator as part of its protected prefix."""
    source = "---\r\ntitle: Café\r\n---\r\n\nHello\r\n"
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    frontmatter = find_source_span(document, "---\r\ntitle: Café\r\n---")
    remove_separator = TextEdit(frontmatter.byte_end, frontmatter.byte_end + 2, "")
    candidate = _diagnostic(
        "PUN201",
        Fix("Join closing fence to body", Applicability.SAFE, (remove_separator,)),
    )

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert plan.fixed_bytes is None, "expected the closing separator to stay intact"
    assert plan.rejections[0].identifier == "fix-error/frontmatter-protected", (
        "expected removal of the protected closing separator to be refused"
    )


def test_planner_refuses_edits_that_create_frontmatter_from_body_text() -> None:
    """Re-extraction must reject edits that change frontmatter recognition."""
    source = "ordinary prose"
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    span = find_source_span(document, source)
    replacement = "---\ntitle: New metadata\n---\nBody prose"
    candidate = _diagnostic(
        "PUN201",
        Fix(
            "Turn prose into metadata",
            Applicability.SAFE,
            (TextEdit.replace(span, replacement),),
        ),
    )

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert plan.fixed_bytes is None, (
        "expected changed frontmatter recognition to refuse"
    )
    assert plan.rejections[0].identifier == "fix-error/frontmatter-protected", (
        "expected newly recognized frontmatter to invalidate the edit"
    )
