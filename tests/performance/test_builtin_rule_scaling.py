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
from stilyagi.engine import rule_view
from stilyagi.rules.builtin import text

from tests.support.rule_fixtures import LintSetup

pytest_plugins = ("tests.package_skeleton_support",)

pytestmark = pytest.mark.usefixtures("reset_extraction_state")


class RecordProperty(typ.Protocol):
    """Callable shape of pytest's ``record_property`` fixture."""

    def __call__(self, name: str, value: object, **extra: object) -> None:
        """Record one named test property."""


def _paragraphs(count: int) -> str:
    """Return ``count`` paragraphs that each contain one repeated word."""
    return "the the item.\n\n" * count


@pytest.mark.parametrize("count", [10, 100, 1000])
def test_indexes_are_built_once_per_document(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
    record_property: RecordProperty,
) -> None:
    """Projection and tokenization happen once; tokenization per segment."""
    calls = {"project": 0, "tokenize_segments": 0, "alpha_tokens": 0}
    _spy(monkeypatch, rule_view, "project", calls)
    _spy(monkeypatch, text, "tokenize_segments", calls)
    _spy(monkeypatch, text, "alpha_tokens", calls)

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
    _spy(monkeypatch, text, "tokenize_segments", calls)
    _spy(monkeypatch, text, "alpha_tokens", calls)

    LintSetup(rules=rules).run(_paragraphs(20))

    assert calls == {"tokenize_segments": 1, "alpha_tokens": 20}, (
        "expected a second text rule not to retokenize"
    )


def _spy(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    name: str,
    calls: dict[str, int],
) -> None:
    """Replace ``module.name`` with a wrapper that counts into ``calls``.

    The count is keyed by the attribute name, so a call site names the
    operation it measures once rather than repeating a second label beside it.
    """
    original = getattr(module, name)

    def wrapper(*args: object, **kwargs: object) -> object:
        calls[name] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
