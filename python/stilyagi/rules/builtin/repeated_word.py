"""``STY001``: report adjacent repeated words inside one segment.

Matching is limited to maximal runs of exact-spelling Unicode alphabetic
tokens separated only by ASCII spaces or tabs. A run never crosses markup, a
region boundary, a newline, or a synthetic segment.
"""

import typing as typ

from stilyagi import diagnostics
from stilyagi.fixes import Applicability, Fix, TextEdit
from stilyagi.rules.builtin import text

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.config.rules import Sty001Config
    from stilyagi.rules.base import RuleContext
    from stilyagi.rules.tokens import Token, TokenizedSegment


def check_repeated_word(
    context: RuleContext[Sty001Config],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report adjacent repeated words inside one source-backed segment.

    Parameters
    ----------
    context:
        Rule context whose eligible regions are headings, paragraphs, and
        table cells, with inline-code spans excluded.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        One warning per maximal repeat run, in document order.

    Examples
    --------
    >>> from stilyagi import config, model
    >>> from stilyagi.config.rules import Sty001Config
    >>> from stilyagi.rules.base import RuleContext
    >>> from stilyagi.rules.registry import RuleRunRequest
    >>> request = RuleRunRequest(
    ...     config=config.StilyagiConfig(),
    ...     config_path=None,
    ...     source_bytes=b"",
    ...     reported_path="doc.md",
    ...     document=model.Document(syntax=model.Syntax.MARKDOWN),
    ... )
    >>> check_repeated_word(
    ...     RuleContext(request=request, rule_config=Sty001Config())
    ... )
    ()
    """
    found: list[diagnostics.Diagnostic] = []
    for item in context.tokenized_segments:
        found.extend(_segment_repeats(context, item))
    return tuple(found)


def _segment_repeats(
    context: RuleContext[Sty001Config],
    item: TokenizedSegment,
) -> cabc.Iterator[diagnostics.Diagnostic]:
    """Yield repeated-word findings for one tokenized segment."""
    segment = item.segment
    tokens = item.tokens
    index = 0
    while index < len(tokens) - 1:
        run_end = index
        while _extends_run(segment.text, tokens, run_end, index):
            run_end += 1
        if run_end > index:
            yield _repeat_diagnostic(context, item, index, run_end)
            index = run_end + 1
            continue
        index += 1


def _extends_run(
    segment_text: str,
    tokens: cabc.Sequence[Token],
    run_end: int,
    index: int,
) -> bool:
    """Whether the token after ``run_end`` repeats the run's first word."""
    return (
        run_end + 1 < len(tokens)
        and tokens[run_end + 1].text == tokens[index].text
        and text.only_blanks_between(segment_text, tokens, run_end, run_end + 1)
    )


def _repeat_diagnostic(
    context: RuleContext[Sty001Config],
    item: TokenizedSegment,
    first: int,
    last: int,
) -> diagnostics.Diagnostic:
    """Build one ``STY001`` warning for a maximal repeated run.

    The diagnostic points at the second token, which is the first offending
    repetition. The edit still removes the whole run's suffix, from the first
    token's end through the last token's end, so a three-word run leaves one
    word rather than two.

    Returns
    -------
    diagnostics.Diagnostic
        A warning carrying the second token's span and the suffix edit.
    """
    segment = item.segment
    offsets = item.offsets
    tokens = item.tokens
    span = text.token_span(segment, offsets, tokens[first + 1])
    edit_start = text.token_span(segment, offsets, tokens[first]).byte_end
    edit_end = text.token_span(segment, offsets, tokens[last]).byte_end
    edit = TextEdit(edit_start, edit_end, "")
    word = tokens[first].text
    line, column = text.location(context, span)
    return diagnostics.Diagnostic(
        path=context.reported_path,
        code="STY001",
        message=f"Repeated word {word!r}",
        severity=diagnostics.Severity.WARNING,
        line=line,
        column=column,
        span=span,
        fix=Fix(
            title=f"Remove repeated {word!r}",
            applicability=Applicability.UNSAFE,
            edits=(edit,),
        ),
    )
