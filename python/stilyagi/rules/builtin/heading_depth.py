"""``MD001``: report heading depth jumps greater than one.

The first heading may use any depth. The finding's primary span is the
canonical heading node span, so it includes the ``#`` prefix and remains
non-empty even for a heading with no text. That span is diagnostic only: the
heading marker is never offered as an editable range.
"""

import typing as typ

from stilyagi import diagnostics
from stilyagi.fixes import Applicability, Fix
from stilyagi.rules.builtin import text

if typ.TYPE_CHECKING:
    from stilyagi.config.rules import Md001Config
    from stilyagi.model.region import RegionView
    from stilyagi.rules.base import RuleContext


def check_heading_depth(
    context: RuleContext[Md001Config],
) -> tuple[diagnostics.Diagnostic, ...]:
    """Report heading depth jumps greater than one.

    Parameters
    ----------
    context:
        Rule context whose eligible regions are Markdown headings.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        One error per heading jump, in document order. A heading whose
        canonical node span the extractor could not locate is never reported,
        because ``MD001`` must point at real bytes; its depth still becomes the
        baseline the next heading is compared against.

    Examples
    --------
    >>> from stilyagi import model
    >>> from stilyagi.config.rules import Md001Config
    >>> from stilyagi.rules.base import RuleContext
    >>> check_heading_depth(
    ...     RuleContext(
    ...         rule_config=Md001Config(),
    ...         document=model.Document(syntax=model.Syntax.MARKDOWN),
    ...         source_bytes=b"",
    ...         reported_path="doc.md",
    ...     )
    ... )
    ()
    """
    found: list[diagnostics.Diagnostic] = []
    previous: int | None = None
    for region in context.regions:
        depth = region.depth
        if depth is None:
            continue
        jumped_from = _jumped_from(region, previous, depth)
        if jumped_from is not None:
            found.append(_heading_diagnostic(context, region, jumped_from, depth))
        previous = depth
    return tuple(found)


def _jumped_from(
    region: RegionView,
    previous: int | None,
    depth: int,
) -> int | None:
    """Return the depth jumped from when this heading is reportable.

    Returning the baseline rather than a boolean lets the caller hand the
    narrowed value straight to the diagnostic constructor, so no second check
    is needed to convince a type checker the jump had a starting depth.

    Returns
    -------
    int | None
        The previous depth when the jump exceeds one level and the canonical
        node span is locatable, otherwise ``None``.
    """
    if previous is None or region.node_span is None:
        return None
    if depth - previous <= 1:
        return None
    return previous


def _heading_diagnostic(
    context: RuleContext[Md001Config],
    region: RegionView,
    previous: int,
    depth: int,
) -> diagnostics.Diagnostic:
    """Build one ``MD001`` diagnostic for a skipped heading level."""
    line, column = text.location(context, region.node_span)
    return diagnostics.Diagnostic(
        path=context.reported_path,
        code="MD001",
        message=(
            f"Heading level jumped from h{previous} to h{depth}; "
            "do not skip heading levels"
        ),
        severity=diagnostics.Severity.ERROR,
        line=line,
        column=column,
        span=region.node_span,
        fix=Fix(
            title="Heading level skips a level",
            applicability=Applicability.MANUAL,
            edits=(),
        ),
    )
