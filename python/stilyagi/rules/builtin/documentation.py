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

import typing as typ

from stilyagi import diagnostics
from stilyagi.rules.builtin import text
from stilyagi.rules.builtin.summary import (
    PhysicalLine,
    SummarySource,
    has_excluded_markup,
    starts_with_markup,
)

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.config.rules import DocRuleConfig
    from stilyagi.model.region import RegionView
    from stilyagi.model.source import SourceSpan
    from stilyagi.rules.base import RuleContext

__all__ = [
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


def check_summary_separation(
    context: RuleContext[DocRuleConfig],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report Python summaries that touch their explanation without a blank.

    The first nonblank physical line is the summary. A single content line, or
    one followed by a blank line, passes. Blank-only content is skipped because
    missing documentation is not in this slice.

    Parameters
    ----------
    context:
        Rule context whose regions are Python docstrings owned by a module,
        class, or function.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        One warning per offending docstring, in document order.

    Examples
    --------
    >>> from stilyagi import model
    >>> from stilyagi.config.rules import DocRuleConfig
    >>> from stilyagi.rules.base import RuleContext
    >>> check_summary_separation(
    ...     RuleContext(
    ...         rule_config=DocRuleConfig(),
    ...         document=model.Document(syntax=model.Syntax.PYTHON_DOCSTRING),
    ...         source_bytes=b"",
    ...         reported_path="example.py",
    ...     )
    ... )
    ()
    """
    return _enabled_findings(context, _separation_diagnostic)


def check_summary_punctuation(
    context: RuleContext[DocRuleConfig],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report plain documentation summaries missing terminal punctuation.

    The candidate is the Python summary line or the Rust first paragraph.
    A candidate containing markup, or any constituent line starting with a
    structural marker, is skipped rather than parsed.

    Parameters
    ----------
    context:
        Rule context whose regions are Python docstrings or Rust
        documentation comments.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        At most one warning per region, in document order.

    Examples
    --------
    >>> from stilyagi import model
    >>> from stilyagi.config.rules import DocRuleConfig
    >>> from stilyagi.rules.base import RuleContext
    >>> check_summary_punctuation(
    ...     RuleContext(
    ...         rule_config=DocRuleConfig(),
    ...         document=model.Document(syntax=model.Syntax.RUST_DOC_COMMENT),
    ...         source_bytes=b"",
    ...         reported_path="example.rs",
    ...     )
    ... )
    ()
    """
    return _enabled_findings(context, _punctuation_diagnostic)


def check_owner_summary(
    context: RuleContext[DocRuleConfig],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report a summary that only repeats its documented owner's name.

    Matching is whole-summary and case-sensitive. A name may be followed by
    ``()`` for a function owner and by a single final period; anything else is
    content and passes.

    Parameters
    ----------
    context:
        Rule context whose regions are named Python classes or functions, or
        named Rust items.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        One warning per redundant summary, in document order.

    Examples
    --------
    >>> from stilyagi import model
    >>> from stilyagi.config.rules import DocRuleConfig
    >>> from stilyagi.rules.base import RuleContext
    >>> check_owner_summary(
    ...     RuleContext(
    ...         rule_config=DocRuleConfig(),
    ...         document=model.Document(syntax=model.Syntax.PYTHON_DOCSTRING),
    ...         source_bytes=b"",
    ...         reported_path="example.py",
    ...     )
    ... )
    ()
    """
    return _enabled_findings(context, _redundancy_diagnostic)


def _enabled_findings(
    context: RuleContext[DocRuleConfig],
    find: cabc.Callable[
        [RuleContext[DocRuleConfig], RegionView],
        diagnostics.Diagnostic | None,
    ],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Return one rule's findings for every selected region while enabled.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        Findings in document order, empty while the rule is not opted in.
    """
    if not context.rule_config.enabled:
        return ()
    return tuple(
        diagnostic
        for region in context.regions
        if (diagnostic := find(context, region)) is not None
    )


def _separation_diagnostic(
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


def _punctuation_diagnostic(
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


def _redundancy_diagnostic(
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
