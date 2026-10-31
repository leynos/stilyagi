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
    >>> from stilyagi import config, model
    >>> from stilyagi.config.rules import Md001Config
    >>> from stilyagi.rules.base import RuleContext
    >>> from stilyagi.rules.registry import RuleRunRequest
    >>> request = RuleRunRequest(
    ...     config=config.StilyagiConfig(),
    ...     config_path=None,
    ...     source_bytes=b"",
    ...     reported_path="doc.md",
    ...     document=model.Document(syntax=model.Syntax.MARKDOWN),
    ... )
    >>> check_heading_depth(
    ...     RuleContext(request=request, rule_config=Md001Config())
    ... )
    ()
    """
    found: list[diagnostics.Diagnostic] = []
    previous: int | None = None
    for region in context.regions:
        depth = region.depth
        if depth is None:
            continue
        if _is_skipped_level(region, previous, depth):
            found.append(_heading_diagnostic(context, region, previous, depth))
        previous = depth
    return tuple(found)


def _is_skipped_level(
    region: RegionView,
    previous: int | None,
    depth: int,
) -> bool:
    """Whether this heading jumps more than one level and can be located.

    Returns
    -------
    bool
        ``True`` when the jump is reportable against the canonical node span.
    """
    return (
        previous is not None and depth - previous > 1 and region.node_span is not None
    )


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
