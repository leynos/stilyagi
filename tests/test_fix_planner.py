"""Behavioural contracts for admissible fix planning and conflicts."""

import dataclasses as dc
import pathlib

import pytest
from stilyagi import config, diagnostics, engine, model
from stilyagi.engine.fix_planning.plan import FixPlanRequest, plan_fixes
from stilyagi.fixes import Applicability, Fix, FixLevel, TextEdit

from tests.support.assertions import assert_with_context
from tests.support.fix_fixtures import find_source_span

_MARKDOWN_FIXTURES = pathlib.Path("tests/fixtures/corpus/markdown/valid")


def _document(source: str, segments: tuple[tuple[str, bool], ...]) -> model.Document:
    """Build a minimal IR document whose spans are derived from source text."""
    cursor = 0
    raw_segments: list[dict[str, object]] = []
    for text, is_source_backed in segments:
        if is_source_backed:
            start = source.encode().find(text.encode(), cursor)
            cursor = start + len(text.encode())
            raw_segments.append({
                "text": text,
                "source": {"byte_start": start, "byte_end": cursor},
            })
        else:
            raw_segments.append({"text": text, "synthetic": "test"})
    return model.Document(
        model.Syntax.MARKDOWN, ir={"regions": [{"segments": raw_segments}]}
    )


@dc.dataclass(frozen=True, slots=True)
class _RequestOptions:
    """Optional planner controls for one test request."""

    level: FixLevel = FixLevel.SAFE
    lint_config: config.LintConfig | None = None


def _request(
    source: str,
    document: model.Document,
    diagnostics_list: tuple[diagnostics.Diagnostic, ...],
    options: _RequestOptions | None = None,
) -> FixPlanRequest:
    """Build a planner request with default permissive fixability."""
    resolved_options = options or _RequestOptions()
    return FixPlanRequest(
        source.encode(),
        document,
        diagnostics_list,
        resolved_options.level,
        resolved_options.lint_config or config.LintConfig(),
    )


def _diagnostic(code: str, fix: Fix) -> diagnostics.Diagnostic:
    """Build one rule diagnostic carrying a candidate fix."""
    return diagnostics.Diagnostic("docs/example.md", code, "example", fix=fix)


@pytest.mark.parametrize(
    ("applicability", "level", "expected_edit_count"),
    [
        pytest.param("safe", FixLevel.SAFE, 1, id="safe"),
        pytest.param("unsafe", FixLevel.SAFE, 0, id="unsafe-safe-level"),
        pytest.param("unsafe", FixLevel.UNSAFE, 1, id="unsafe-unsafe-level"),
        pytest.param("manual", FixLevel.UNSAFE, 0, id="manual"),
    ],
)
def test_planner_obeys_fix_applicability(
    applicability: str,
    level: FixLevel,
    expected_edit_count: int,
) -> None:
    """Select only safe fixes unless the unsafe level explicitly permits them."""
    source = "Hello world"
    document = _document(source, ((source, True),))
    span = find_source_span(document, "world")
    candidate = _diagnostic(
        "PUN201",
        Fix(
            "Replace",
            Applicability(applicability),
            (TextEdit.replace(span, "earth"),),
        ),
    )

    plan = plan_fixes(
        _request(source, document, (candidate,), _RequestOptions(level=level))
    )

    assert_with_context(
        len(plan.edits) == expected_edit_count,
        "expected applicability selection to match the requested fix level",
    )


def test_planner_respects_unfixable_prefixes() -> None:
    """Keep reported diagnostics unplanned when an unfixable prefix matches."""
    source = "Hello world"
    document = _document(source, ((source, True),))
    span = find_source_span(document, "world")
    candidate = _diagnostic(
        "PUN201",
        Fix("Replace", Applicability.SAFE, (TextEdit.replace(span, "earth"),)),
    )

    plan = plan_fixes(
        _request(
            source,
            document,
            (candidate,),
            _RequestOptions(lint_config=config.LintConfig(unfixable=("PUN",))),
        )
    )

    assert_with_context(not plan.edits, "expected an unfixable prefix to drop the fix")
    assert_with_context(
        plan.fixed_bytes == source.encode(), "expected an empty plan to be an identity"
    )


@pytest.mark.parametrize(
    "kind",
    [
        "synthetic",
        "straddling",
        "non-contiguous",
        "out-of-bounds",
        "inverted",
        "mid-code-point",
    ],
)
def test_planner_rejects_non_admissible_edits(kind: str) -> None:
    """Refuse synthetic, discontinuous, malformed, and non-UTF-8 edit spans."""
    source = "éalpha beta"
    document = _document(source, (("éalpha", True), (" ", False), ("beta", True)))
    alpha = find_source_span(document, "alpha")
    beta = find_source_span(document, "beta")
    edit = {
        "synthetic": TextEdit(alpha.byte_end, beta.byte_start, "x"),
        "straddling": TextEdit(alpha.byte_end - 1, beta.byte_start + 1, "x"),
        "non-contiguous": TextEdit(alpha.byte_start, beta.byte_end, "x"),
        "out-of-bounds": TextEdit(alpha.byte_start, len(source.encode()) + 1, "x"),
        "inverted": TextEdit(alpha.byte_end, alpha.byte_start, "x"),
        "mid-code-point": TextEdit(alpha.byte_start - 1, alpha.byte_start, "x"),
    }[kind]
    candidate = _diagnostic("PUN201", Fix("Bad", Applicability.SAFE, (edit,)))

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert_with_context(
        plan.fixed_bytes is None, "expected every inadmissible edit to abort mutation"
    )
    assert_with_context(bool(plan.rejections), "expected an inadmissibility rejection")


def test_planner_keeps_a_fix_atomic_and_detects_conflicts() -> None:
    """Reject a partly invalid fix and refuse two competing replacements."""
    source = "Hello world"
    document = _document(source, ((source, True),))
    span = find_source_span(document, "world")
    invalid = TextEdit(span.byte_start, len(source.encode()) + 1, "earth")
    partly_bad = _diagnostic(
        "PUN201",
        Fix("Mixed", Applicability.SAFE, (TextEdit.replace(span, "earth"), invalid)),
    )
    first = _diagnostic(
        "PUN202",
        Fix("First", Applicability.SAFE, (TextEdit.replace(span, "earth"),)),
    )
    second = _diagnostic(
        "PUN203",
        Fix("Second", Applicability.SAFE, (TextEdit.replace(span, "mars"),)),
    )

    invalid_plan = plan_fixes(_request(source, document, (partly_bad,)))
    conflict_plan = plan_fixes(_request(source, document, (first, second)))

    assert_with_context(
        not invalid_plan.edits, "expected a bad edit to reject its whole fix"
    )
    assert_with_context(
        conflict_plan.fixed_bytes is None, "expected a conflict to forbid mutation"
    )
    assert_with_context(
        conflict_plan.rejections[0].identifier == "fix-error/overlapping-edits",
        "expected the stable overlap rejection identifier",
    )


def test_planner_coalesces_identical_edits_and_accepts_merged_boundaries() -> None:
    """Deduplicate matching edits and permit insertions at touching-span boundaries."""
    source = "Hello world"
    document = _document(source, (("Hello", True), (" world", True)))
    boundary = find_source_span(document, "Hello").byte_end
    edit = TextEdit(boundary, boundary, ",")
    first = _diagnostic("PUN201", Fix("Comma", Applicability.SAFE, (edit,)))
    second = _diagnostic("PUN202", Fix("Comma", Applicability.SAFE, (edit,)))

    plan = plan_fixes(_request(source, document, (first, second)))

    assert_with_context(plan.edits == (edit,), "expected identical edits to coalesce")
    assert_with_context(
        plan.fixed_bytes == b"Hello, world", "expected boundary insertion to apply"
    )


def test_planner_aborts_when_ir_segment_text_disagrees_with_source() -> None:
    """Treat a provenance mismatch as a file-level non-mutation condition."""
    source = "Hello world"
    document = model.Document(
        model.Syntax.MARKDOWN,
        ir={
            "regions": [
                {
                    "segments": [
                        {"text": "HELLO", "source": {"byte_start": 0, "byte_end": 5}}
                    ]
                }
            ]
        },
    )
    candidate = _diagnostic(
        "PUN201", Fix("Bad IR", Applicability.SAFE, (TextEdit(0, 1, "h"),))
    )

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert_with_context(
        plan.fixed_bytes is None, "expected source disagreement to forbid mutation"
    )
    assert_with_context(
        plan.rejections[0].identifier == "fix-error/source-mismatch",
        "expected a source-mismatch rejection",
    )


def test_planner_accepts_list_paragraph_end_insertions_from_real_corpus() -> None:
    """Prove that list-item prose remains admissible despite its container shape."""
    source = (_MARKDOWN_FIXTURES / "lists.md.fixture").read_text(encoding="utf-8")
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    item = find_source_span(document, "Unordered item")
    candidate = _diagnostic(
        "PUN201",
        Fix("Add punctuation", Applicability.SAFE, (TextEdit.insert_after(item, "."),)),
    )

    plan = plan_fixes(_request(source, document, (candidate,)))

    assert_with_context(
        plan.fixed_bytes
        == source.replace("Unordered item", "Unordered item.").encode(),
        "expected the nested source-backed list paragraph to accept an end insertion",
    )
