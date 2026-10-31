"""``TERM001``: report configured banned terms in prose.

The rule is opt-in: it has no effect until the project selects it and supplies
terms. Matching is over whole alphabetic tokens only, so a configured
``obviously`` never matches inside ``unobviously``. Comparison uses
:meth:`str.casefold` unless the configuration asks for exact case. The rule
reports the original token's byte span and never offers a fix.
"""

import typing as typ

from stilyagi import diagnostics
from stilyagi.rules.builtin import text

if typ.TYPE_CHECKING:
    from stilyagi.config.rules import Term001Config
    from stilyagi.rules.base import RuleContext


def check_banned_term(
    context: RuleContext[Term001Config],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report configured banned terms inside source-backed segments.

    Parameters
    ----------
    context:
        Rule context carrying validated terms and eligible regions.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        One error per banned-term occurrence, in document order.

    Examples
    --------
    >>> from stilyagi import config, model
    >>> from stilyagi.config.rules import Term001Config
    >>> from stilyagi.rules.base import RuleContext
    >>> from stilyagi.rules.registry import RuleRunRequest
    >>> request = RuleRunRequest(
    ...     config=config.StilyagiConfig(),
    ...     config_path=None,
    ...     source_bytes=b"",
    ...     reported_path="doc.md",
    ...     document=model.Document(syntax=model.Syntax.MARKDOWN),
    ... )
    >>> check_banned_term(
    ...     RuleContext(request=request, rule_config=Term001Config())
    ... )
    ()
    """
    config = context.rule_config
    if not config.is_active:
        return ()
    wanted = frozenset(config.terms)
    found: list[diagnostics.Diagnostic] = []
    for item in context.tokenized_segments:
        for token in item.tokens:
            candidate = token.text if config.case_sensitive else token.text.casefold()
            if candidate not in wanted:
                continue
            span = text.token_span(item.segment, item.offsets, token)
            line, column = text.location(context, span)
            found.append(
                diagnostics.Diagnostic(
                    path=context.reported_path,
                    code="TERM001",
                    message=f"Banned term {token.text!r}",
                    severity=diagnostics.Severity.ERROR,
                    line=line,
                    column=column,
                    span=span,
                )
            )
    return tuple(found)
