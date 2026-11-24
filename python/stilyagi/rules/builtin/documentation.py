"""Opt-in documentation-summary rules for Python docstrings and Rust docs.

Three diagnostic-only rules share one bounded summary analysis:

- ``DOC001`` reports a Python docstring whose summary line runs straight into
  further explanation without a blank separator.
- ``DOC002`` reports a plain summary that does not end in ``.``, ``!``, or
  ``?``.
- ``DOC003`` reports a summary that merely repeats its documented owner's
  name.

Each rule is inert until its ``enabled`` option is set, because the default
``DOC`` selection prefix already includes these codes. Markdown and ordinary
comments are outside the supported surface: the rules' targets name only
docstring regions, and the analysis skips any candidate it cannot judge
without a Markdown parser.
"""

import functools
import typing as typ

from stilyagi import diagnostics
from stilyagi.rules.builtin import text
from stilyagi.rules.builtin.markup import has_excluded_markup, starts_with_markup
from stilyagi.rules.builtin.summary import PhysicalLine, SummarySource

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.config.rules import DocRuleConfig
    from stilyagi.model.region import RegionView
    from stilyagi.model.source import SourceSpan
    from stilyagi.rules.base import RuleContext

__all__ = [
    "check_documentation",
    "check_owner_summary",
    "check_summary_punctuation",
    "check_summary_separation",
]

_PYTHON_DOCSTRING = "python_docstring"
_RUST_DOC_COMMENT = "rust_doc_comment"

#: Final visible characters DOC002 accepts as terminal punctuation.
_TERMINAL_PUNCTUATION: frozenset[str] = frozenset(".!?")

#: Owner kinds whose summaries may name themselves with a trailing call.
_FUNCTION_OWNER_KINDS: frozenset[str] = frozenset({"function"})


def check_documentation(
    context: RuleContext[DocRuleConfig],
    *,
    find: cabc.Callable[
        [RuleContext[DocRuleConfig], RegionView],
        diagnostics.Diagnostic | None,
    ],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report one documentation rule's findings for every selected region.

    The finding selector decides what the rule reports. This function applies
    the shared opt-in gate and the document order, so every rule in the family
    behaves the same way when it is not configured.

    Parameters
    ----------
    context:
        Rule context whose regions the rule's target already selected.
    find:
        The rule's finding selector, returning one diagnostic or ``None`` for
        a region.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        Findings in document order, empty while the rule is not opted in.

    Examples
    --------
    >>> from stilyagi import model
    >>> from stilyagi.config.rules import DocRuleConfig
    >>> from stilyagi.rules.base import RuleContext
    >>> check_documentation(
    ...     RuleContext(
    ...         rule_config=DocRuleConfig(),
    ...         document=model.Document(syntax=model.Syntax.PYTHON_DOCSTRING),
    ...         source_bytes=b"",
    ...         reported_path="example.py",
    ...     ),
    ...     find=_separation_finding,
    ... )
    ()
    """
    if not context.rule_config.enabled:
        return ()
    return tuple(
        diagnostic
        for region in context.regions
        if (diagnostic := find(context, region)) is not None
    )


def _separation_finding(
    context: RuleContext[DocRuleConfig],
    region: RegionView,
) -> diagnostics.Diagnostic | None:
    """Return the ``DOC001`` finding for one region, if any."""
    source = SummarySource.of(region)
    index = source.first_content_index()
    if index is None or index + 1 == len(source.lines):
        return None
    following = source.lines[index + 1]
    if source.is_blank(following):
        return None
    line_text = source.line_text(following)
    anchor_index = following.start + _leading_blank_length(line_text)
    span = source.anchor(anchor_index)
    if span is None:
        return None
    return _diagnostic(
        context,
        "DOC001",
        "Docstring summary needs a blank line before further explanation",
        span,
    )


def _punctuation_finding(
    context: RuleContext[DocRuleConfig],
    region: RegionView,
) -> diagnostics.Diagnostic | None:
    """Return the ``DOC002`` finding for one region, if any."""
    source = SummarySource.of(region)
    lines = _summary_lines(region, source)
    summary, start = source.trimmed(lines)
    if not summary or not _is_plain_summary(source, lines, summary):
        return None
    if summary[-1] in _TERMINAL_PUNCTUATION:
        return None
    span = source.anchor(start + len(summary) - 1)
    if span is None:
        return None
    return _diagnostic(
        context,
        "DOC002",
        "Summary must end with '.', '!' or '?'",
        span,
    )


def _redundancy_finding(
    context: RuleContext[DocRuleConfig],
    region: RegionView,
) -> diagnostics.Diagnostic | None:
    """Return the ``DOC003`` finding for one region, if any."""
    owner = region.owner
    if owner is None or not owner.name:
        return None
    name = owner.name
    source = SummarySource.of(region)
    summary, start = source.trimmed(_summary_lines(region, source))
    if not _repeats_owner(summary, name, owner.kind):
        return None
    span = source.anchor(start)
    if span is None:
        return None
    return _diagnostic(
        context,
        "DOC003",
        f"Summary only repeats the documented name {name!r}",
        span,
    )


def _summary_lines(
    region: RegionView,
    source: SummarySource,
) -> tuple[PhysicalLine, ...]:
    """Return the candidate lines for one region's summary.

    Returns
    -------
    tuple[PhysicalLine, ...]
        One line for a Python docstring, or the first paragraph for a Rust
        documentation comment.
    """
    if region.kind == _PYTHON_DOCSTRING:
        return source.first_content_line()
    if region.kind == _RUST_DOC_COMMENT:
        return source.first_paragraph()
    return ()


def _is_plain_summary(
    source: SummarySource,
    lines: cabc.Sequence[PhysicalLine],
    summary: str,
) -> bool:
    """Return whether punctuation policy applies to this candidate."""
    if has_excluded_markup(summary):
        return False
    return not any(starts_with_markup(source.line_text(line)) for line in lines)


def _repeats_owner(summary: str, name: str, kind: str) -> bool:
    """Return whether ``summary`` is exactly the owner's name.

    Returns
    -------
    bool
        ``True`` when the summary matches the name, optionally with ``()`` for
        a function owner and optionally one final period.
    """
    candidates = {name}
    if kind in _FUNCTION_OWNER_KINDS:
        candidates.add(f"{name}()")
    if summary in candidates:
        return True
    return summary.endswith(".") and summary[:-1] in candidates


def _leading_blank_length(text_value: str) -> int:
    """Return how many leading Unicode whitespace characters a line has."""
    return len(text_value) - len(text_value.lstrip())


def _diagnostic(
    context: RuleContext[DocRuleConfig],
    code: str,
    message: str,
    span: SourceSpan,
) -> diagnostics.Diagnostic:
    """Build one warning diagnostic anchored at ``span``."""
    line, column = text.location(context, span)
    return diagnostics.Diagnostic(
        path=context.reported_path,
        code=code,
        message=message,
        severity=diagnostics.Severity.WARNING,
        line=line,
        column=column,
        span=span,
    )


#: The ``DOC001`` hook: report a Python summary with no blank separator.
check_summary_separation = functools.partial(
    check_documentation, find=_separation_finding
)

#: The ``DOC002`` hook: report a plain summary with no terminal punctuation.
check_summary_punctuation = functools.partial(
    check_documentation, find=_punctuation_finding
)

#: The ``DOC003`` hook: report a summary that repeats its owner's name.
check_owner_summary = functools.partial(check_documentation, find=_redundancy_finding)
