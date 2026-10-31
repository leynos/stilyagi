"""Operation-count scaling probe for the builtin text rules.

The gate here is the number of index and tokenization operations, not wall
time: this host is shared and a timing threshold would be a flaky assertion.
Elapsed milliseconds are recorded as a test property for inspection only.

The document projection and the segment tokenization are the work that would
otherwise repeat per selected rule, so their call counts are what the contract
pins: once per document, and once per eligible segment regardless of how many
text rules run.
"""

import time
import typing as typ

import pytest
from stilyagi import diagnostics_location, engine, model
from stilyagi.engine import ir_view, rule_view
from stilyagi.rules import inline_code
from stilyagi.rules.base import RegionTarget
from stilyagi.rules.builtin import text

from tests.support.rule_fixtures import LintSetup

_TEXT_TARGET = RegionTarget(kinds=("heading", "paragraph", "table_cell"))

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")


class RecordProperty(typ.Protocol):
    """Callable shape of pytest's ``record_property`` fixture."""

    def __call__(self, name: str, value: object, **extra: object) -> None:
        """Record one named test property."""


def _paragraphs(count: int) -> str:
    """Return ``count`` paragraphs that each contain one repeated word."""
    return "the the item.\n\n" * count


def _code_paragraphs(count: int) -> str:
    """Return ``count`` paragraphs that each hold a finding and a code span."""
    return "the the `code` item.\n\n" * count


def _source_backed_segments(source: str) -> int:
    """Count the eligible text segments the projection yields for ``source``."""
    document = engine.extract_document(source, model.Syntax.MARKDOWN)
    view = rule_view.project(document, source_bytes=source.encode("utf-8"))
    return sum(
        1
        for region in view.for_target(_TEXT_TARGET)
        for segment in region.segments
        if segment.span is not None
    )


@pytest.mark.parametrize("count", [10, 100, 1000])
def test_indexes_are_built_once_per_document(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
    record_property: RecordProperty,
) -> None:
    """Projection and tokenization happen once; tokenization per segment."""
    calls = {"project": 0, "tokenize_segments": 0, "alpha_tokens": 0}
    _spy(monkeypatch, (rule_view, "project"), calls)
    _spy(monkeypatch, (text, "tokenize_segments"), calls)
    _spy(monkeypatch, (text, "alpha_tokens"), calls)

    started = time.perf_counter()
    result = LintSetup().run(_paragraphs(count))
    record_property("elapsed_ms", round((time.perf_counter() - started) * 1000, 2))

    assert len(result) == count, "expected one finding per paragraph"
    assert calls == {"project": 1, "tokenize_segments": 1, "alpha_tokens": count}, (
        "expected projection and tokenization to run once per document"
    )


@pytest.mark.parametrize(
    "rules",
    [
        pytest.param({}, id="one-text-rule"),
        pytest.param({"TERM001": {"terms": ["item"]}}, id="two-text-rules"),
    ],
)
def test_a_second_text_rule_does_not_retokenize(
    rules: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selection changes which rules run, not how often text is tokenized."""
    calls = {"tokenize_segments": 0, "alpha_tokens": 0}
    _spy(monkeypatch, (text, "tokenize_segments"), calls)
    _spy(monkeypatch, (text, "alpha_tokens"), calls)

    LintSetup(rules=rules).run(_paragraphs(20))

    assert calls == {"tokenize_segments": 1, "alpha_tokens": 20}, (
        "expected a second text rule not to retokenize"
    )


@pytest.mark.parametrize("count", [10, 100, 1000])
def test_line_starts_are_validated_once_and_located_per_finding(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line mapping validates the index once, then bisects once per finding."""
    calls = {"line_index": 0, "validated_line_starts": 0, "bisect": 0}
    _spy(monkeypatch, (ir_view, "line_index"), calls)
    _spy(monkeypatch, (diagnostics_location, "validated_line_starts"), calls)
    _spy(
        monkeypatch,
        (diagnostics_location, "bisect_right"),
        calls,
        label="bisect",
    )

    result = LintSetup().run(_paragraphs(count))

    assert len(result) == count, "expected one finding per paragraph"
    assert calls["line_index"] == 1, "expected one line index per document"
    assert calls["validated_line_starts"] == 1, "expected one validation per document"
    assert calls["bisect"] == count, "expected one line search per finding"


@pytest.mark.parametrize("count", [10, 100])
def test_inline_code_lookup_searches_once_per_segment(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inline-code containment costs one search per segment, not per finding."""
    source = _code_paragraphs(count)
    segments = _source_backed_segments(source)
    calls = {"contains": 0, "bisect": 0, "bisect-findings": 0}
    _spy(monkeypatch, (inline_code.InlineCodeIndex, "contains"), calls)
    _spy(monkeypatch, (inline_code, "bisect_right"), calls, label="bisect")
    _spy(
        monkeypatch,
        (diagnostics_location, "bisect_right"),
        calls,
        label="bisect-findings",
    )

    result = LintSetup(rules={"TERM001": {"terms": ["item"]}}).run(source)

    assert len(result) == 2 * count, "expected a style and a term finding"
    assert calls["contains"] == segments, "expected one containment query per segment"
    assert calls["bisect"] == segments, "expected one inline search per segment"
    assert calls["bisect-findings"] == len(result), (
        "expected inline indexing not to add line searches"
    )


def _spy(
    monkeypatch: pytest.MonkeyPatch,
    target: tuple[object, str],
    calls: dict[str, int],
    *,
    label: str | None = None,
) -> None:
    """Replace the attribute named by ``target`` with a counting wrapper.

    ``target`` pairs the module or class with the attribute to patch, so the
    wrapper keeps four parameters while still naming both halves of the patch.
    The count is keyed by ``label``, defaulting to the attribute name, so a
    call site names the operation it measures once rather than repeating a
    second label beside it. Patch two targets exposing the same attribute name
    by giving each an explicit ``label``.
    """
    module, name = target
    original = getattr(module, name)

    def wrapper(*args: object, **kwargs: object) -> object:
        calls[label or name] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
