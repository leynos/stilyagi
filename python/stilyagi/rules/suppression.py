"""Resolve canonical IR suppression directives into a per-document plan.

The plan is computed before rule selection so that changing ``select`` or
``ignore`` cannot move an ``ignore-next`` target, and so that a stateful rule
can be evaluated in full before its findings are filtered.
"""

import dataclasses as dc
import typing as typ

from stilyagi.engine import rule_view
from stilyagi.engine.ir_mapping import span_fields, string_tuple
from stilyagi.model.source import SourceSpan

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import model

__all__ = [
    "IgnoreDirective",
    "InlineSuppression",
    "RuleInterval",
    "SuppressionPlan",
    "expand_prefixes",
    "resolve_suppressions",
]


def expand_prefixes(
    prefixes: cabc.Sequence[str],
    concrete_codes: cabc.Sequence[str],
) -> tuple[str, ...]:
    """Expand code prefixes against the concrete builtin inventory.

    ``ALL`` matches every concrete code. Any other prefix matches by
    :meth:`str.startswith`, so an unmatched prefix is a valid no-op.

    Parameters
    ----------
    prefixes:
        Configured prefixes or exact codes.
    concrete_codes:
        Concrete builtin codes in inventory order.

    Returns
    -------
    tuple[str, ...]
        Matching codes in concrete inventory order.

    Examples
    --------
    >>> expand_prefixes(("MD",), ("MD001", "STY001", "TERM001"))
    ('MD001',)
    >>> expand_prefixes(("ALL",), ("MD001", "STY001"))
    ('MD001', 'STY001')
    >>> expand_prefixes(("NOPE",), ("MD001",))
    ()
    """
    wanted = set(prefixes)
    return tuple(
        code
        for code in concrete_codes
        if "ALL" in wanted or any(code.startswith(prefix) for prefix in wanted)
    )


@dc.dataclass(frozen=True, slots=True)
class IgnoreDirective:
    """One IR suppression entry with its codes resolved to concrete codes.

    Parameters
    ----------
    codes:
        Concrete rule codes the directive suppresses.
    span:
        Byte range of the directive comment, when the IR supplies one.
    kind:
        Directive shape: ``file``, ``range``, or ``inline``.
    range_role:
        ``open`` or ``close`` for range directives.
    """

    codes: tuple[str, ...]
    span: SourceSpan | None
    kind: str
    range_role: str | None

    def covers(self, code: str) -> bool:
        """Return whether this directive names ``code``.

        Parameters
        ----------
        code:
            Candidate rule code.

        Returns
        -------
        bool
            ``True`` when the directive suppresses this code.

        Examples
        --------
        >>> IgnoreDirective(("MD001",), None, "file", None).covers("MD001")
        True
        >>> IgnoreDirective(("MD001",), None, "file", None).covers("STY001")
        False
        """
        return code in self.codes


@dc.dataclass(frozen=True, slots=True)
class RuleInterval:
    """A half-open byte range over which one code is suppressed."""

    code: str
    byte_start: int
    byte_end: int

    def covers(self, byte_start: int) -> bool:
        """Return whether the interval covers a finding start.

        Parameters
        ----------
        byte_start:
            The finding's primary span start.

        Returns
        -------
        bool
            ``True`` when the start falls inside the interval.

        Examples
        --------
        >>> RuleInterval("STY001", 10, 20).covers(10)
        True
        >>> RuleInterval("STY001", 10, 20).covers(20)
        False
        """
        return self.byte_start <= byte_start < self.byte_end


@dc.dataclass(frozen=True, slots=True)
class InlineSuppression:
    """An ``ignore-next`` directive bound to one eligible prose unit."""

    codes: tuple[str, ...]
    unit: SourceSpan


@dc.dataclass(frozen=True, slots=True)
class SuppressionPlan:
    """The resolved suppression decision for one document.

    Parameters
    ----------
    file_codes:
        Codes suppressed for the whole document.
    intervals:
        Range suppression intervals produced by ``disable``/``enable`` pairs.
    inline:
        ``ignore-next`` directives bound to their consumed units.
    directives:
        Every parsed directive, for diagnostics and truth-table tests.
    """

    file_codes: frozenset[str]
    intervals: tuple[RuleInterval, ...]
    inline: tuple[InlineSuppression, ...]
    directives: tuple[IgnoreDirective, ...] = ()

    def suppresses(self, code: str, span: SourceSpan | None) -> bool:
        """Return whether the plan suppresses a finding.

        File suppression is code-based; range and inline suppression need the
        finding's primary span start. A finding without a span therefore
        cannot be hidden by a located directive.

        Parameters
        ----------
        code:
            Candidate rule code.
        span:
            The finding's primary byte span, when it has one.

        Returns
        -------
        bool
            ``True`` when the finding must be dropped.

        Examples
        --------
        >>> plan = SuppressionPlan(frozenset({"MD001"}), (), ())
        >>> plan.suppresses("MD001", None)
        True
        >>> plan.suppresses("STY001", None)
        False
        """
        if code in self.file_codes:
            return True
        if span is None:
            return False
        start = span.byte_start
        return any(
            interval.code == code and interval.covers(start)
            for interval in self.intervals
        ) or any(
            code in suppression.codes
            and suppression.unit.byte_start <= start < suppression.unit.byte_end
            for suppression in self.inline
        )


def resolve_suppressions(
    document: model.Document,
    *,
    concrete_codes: cabc.Sequence[str],
    source_length: int,
    prose_units: cabc.Sequence[SourceSpan] | None = None,
) -> SuppressionPlan:
    """Parse and resolve every suppression directive for one document.

    Parameters
    ----------
    document:
        Extracted document whose IR may carry suppressions.
    concrete_codes:
        Concrete builtin codes used to expand directive prefixes.
    source_length:
        Length of the original source in bytes, so an unclosed range can end
        at end-of-file.
    prose_units:
        The document projection's prose units, when the caller already built
        it. Supplied to avoid projecting the document's regions twice.

    Returns
    -------
    SuppressionPlan
        File, range, and inline decisions resolved to concrete codes.

    Examples
    --------
    >>> from stilyagi import model
    >>> plan = resolve_suppressions(
    ...     model.Document(syntax=model.Syntax.MARKDOWN),
    ...     concrete_codes=("MD001",),
    ...     source_length=0,
    ... )
    >>> plan.file_codes
    frozenset()
    """
    directives = _directives(document, concrete_codes)
    return SuppressionPlan(
        file_codes=_file_codes(directives),
        intervals=_range_intervals(directives, source_length),
        inline=_inline_suppressions(directives, document, prose_units),
        directives=directives,
    )


def _directives(
    document: model.Document,
    concrete_codes: cabc.Sequence[str],
) -> tuple[IgnoreDirective, ...]:
    """Convert raw IR suppression entries into resolved directives."""
    resolved: list[IgnoreDirective] = []
    for raw in rule_view.raw_suppressions(document):
        kind = raw.get("kind")
        if not isinstance(kind, str):
            continue
        raw_codes = string_tuple(raw.get("codes"))
        codes = (
            tuple(concrete_codes)
            if kind == "file" and not raw_codes
            else expand_prefixes(raw_codes, concrete_codes)
        )
        if not codes:
            continue
        resolved.append(
            IgnoreDirective(
                codes=codes,
                span=_span(raw.get("span")),
                kind=kind,
                range_role=_optional_string(raw.get("range_role")),
            )
        )
    return tuple(resolved)


def _file_codes(directives: cabc.Iterable[IgnoreDirective]) -> frozenset[str]:
    """Return codes suppressed for the whole document."""
    codes: set[str] = set()
    for directive in directives:
        if directive.kind == "file":
            codes.update(directive.codes)
    return frozenset(codes)


def _range_intervals(
    directives: cabc.Iterable[IgnoreDirective],
    source_length: int,
) -> tuple[RuleInterval, ...]:
    """Fold ordered range directives into per-code suppression intervals."""
    events = sorted(
        (
            directive
            for directive in directives
            if directive.kind == "range"
            and directive.span is not None
            and directive.range_role in {"open", "close"}
        ),
        key=lambda directive: (
            directive.span.byte_start if directive.span is not None else 0
        ),
    )
    active: dict[str, int] = {}
    intervals: list[RuleInterval] = []
    for directive in events:
        span = directive.span
        if span is None:
            continue
        for code in directive.codes:
            if directive.range_role == "open":
                active.setdefault(code, span.byte_start)
                continue
            start = active.pop(code, None)
            if start is not None:
                intervals.append(RuleInterval(code, start, span.byte_start))
    intervals.extend(
        RuleInterval(code, start, source_length)
        for code, start in sorted(active.items())
    )
    return tuple(intervals)


def _inline_suppressions(
    directives: cabc.Iterable[IgnoreDirective],
    document: model.Document,
    prose_units: cabc.Sequence[SourceSpan] | None,
) -> tuple[InlineSuppression, ...]:
    """Bind each ``ignore-next`` directive to the next nonempty prose unit."""
    units = (
        rule_view.ignore_next_units(document)
        if prose_units is None
        else tuple(prose_units)
    )
    bound: list[InlineSuppression] = []
    for directive in directives:
        if directive.kind != "inline" or directive.span is None:
            continue
        unit = next(
            (
                candidate
                for candidate in units
                if candidate.byte_start >= directive.span.byte_end
            ),
            None,
        )
        if unit is not None:
            bound.append(InlineSuppression(directive.codes, unit))
    return tuple(bound)


def _span(value: object) -> SourceSpan | None:
    """Return a well-ordered span from a raw IR span mapping."""
    fields = span_fields(value)
    if fields is None:
        return None
    try:
        return SourceSpan(*fields)
    except ValueError:
        return None


def _optional_string(value: object) -> str | None:
    """Return a string-valued IR field, or ``None``."""
    return value if isinstance(value, str) else None
