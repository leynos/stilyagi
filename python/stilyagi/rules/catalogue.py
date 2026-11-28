"""Pure queries over the shipped builtin rule catalogue.

The catalogue is a static inventory query: it never reads a document, resolves
project configuration, discovers plugins, or writes cache state. That boundary
lets a maintainer inspect a rule in a repository whose configuration is broken.
Effective enablement for one file is a separate question, answered by the
policy layer during a check.

:func:`list_rules` keeps the inventory's descriptor objects unchanged, so a
caller can rely on identity as well as equality, and sorts them by code so the
result is deterministic regardless of declaration order.
"""

import dataclasses as dc
import typing as typ

from stilyagi.rules.description import SEVERITY_NAMES
from stilyagi.rules.registry import builtin_metadata

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.rules.base import RuleMetadata

__all__ = [
    "RuleFilters",
    "RuleNotFoundError",
    "get_rule",
    "list_rules",
]


class RuleNotFoundError(LookupError):
    """Raised when no builtin rule has the requested exact code.

    Parameters
    ----------
    code:
        The code that matched no rule, retained verbatim for callers that
        render the failure and for tests that assert the exact miss. Keeping
        the raw value is deliberate: this is a domain query miss, and how the
        command line chooses to present it -- including escaping control
        characters so a failure stays on one line -- belongs to the adapter
        that writes standard error.
    """

    def __init__(self, code: str) -> None:
        """Record the missing code in the message and on the exception."""
        self.code = code
        super().__init__(f"unknown rule code: {code}")


@dc.dataclass(frozen=True, slots=True)
class RuleFilters:
    """Immutable catalogue filters, independent of the command line.

    Every field defaults to ``None``, which means "do not filter on this
    dimension". Supplied filters combine with logical AND.

    Parameters
    ----------
    prefix:
        Case-sensitive code prefix, or ``None``. An empty prefix is invalid.
    pack:
        Exact pack name, or ``None``. An empty name is invalid.
    severity:
        Exact default severity, or ``None``.
    preview:
        Required preview status, or ``None``.
    fixable:
        Required edit capability, or ``None``. ``True`` includes unsafe edits;
        a manual suggestion does not count as fixable.

    Examples
    --------
    >>> RuleFilters(prefix="MD")
    RuleFilters(prefix='MD', pack=None, severity=None, preview=None, fixable=None)
    >>> RuleFilters(prefix="md")
    RuleFilters(prefix='md', pack=None, severity=None, preview=None, fixable=None)
    """

    prefix: str | None = None
    pack: str | None = None
    severity: str | None = None
    preview: bool | None = None
    fixable: bool | None = None

    def __post_init__(self) -> None:
        """Reject filter values the catalogue cannot honour."""
        _require_nonempty_filter("prefix", self.prefix)
        _require_nonempty_filter("pack", self.pack)
        if self.severity is not None and self.severity not in SEVERITY_NAMES:
            message = f"unsupported severity filter: {self.severity}"
            raise ValueError(message)
        for name, value in (
            ("preview", self.preview),
            ("fixable", self.fixable),
        ):
            _require_optional_bool(name, value=value)


def _require_nonempty_filter(name: str, value: str | None) -> None:
    """Reject an empty prefix or pack filter at construction."""
    if value is not None and not value:
        message = f"{name} filter must be non-empty"
        raise ValueError(message)


def _require_optional_bool(name: str, *, value: bool | None) -> None:
    """Reject a non-boolean preview or fixability filter."""
    if value is not None and not isinstance(value, bool):
        message = f"{name} filter must be a boolean or None"
        raise ValueError(message)


def list_rules(filters: RuleFilters | None = None) -> tuple[RuleMetadata, ...]:
    """Return every builtin rule satisfying ``filters``, sorted by code.

    Parameters
    ----------
    filters:
        The filter conjunction, or ``None`` to select the complete inventory.

    Returns
    -------
    tuple[RuleMetadata, ...]
        Matching descriptors in ascending code order. An unmatched filter
        yields an empty tuple rather than an error, and opt-in rules are
        included when no filter excludes them.

    Examples
    --------
    >>> [rule.code for rule in list_rules()]
    ['DOC001', 'DOC002', 'DOC003', 'MD001', 'STY001', 'TERM001']
    >>> [rule.code for rule in list_rules(RuleFilters(fixable=True))]
    ['STY001']
    >>> list_rules(RuleFilters(prefix="ZZ"))
    ()
    """
    return _select_rules(builtin_metadata(), filters or RuleFilters())


def get_rule(code: str) -> RuleMetadata:
    """Return the single builtin rule whose code equals ``code``.

    Matching is exact and case-sensitive: a prefix, a lower-case spelling, or
    an unknown code raises :class:`RuleNotFoundError`.

    Parameters
    ----------
    code:
        Complete rule code, for example ``TERM001``.

    Returns
    -------
    RuleMetadata
        The unique descriptor with this code.

    Examples
    --------
    >>> get_rule("MD001").name
    'heading-depth'
    >>> get_rule("md001")
    Traceback (most recent call last):
    stilyagi.rules.catalogue.RuleNotFoundError: unknown rule code: md001
    """
    return _lookup_rule(builtin_metadata(), code)


def _select_rules(
    registry: cabc.Sequence[RuleMetadata],
    filters: RuleFilters,
) -> tuple[RuleMetadata, ...]:
    """Select matching descriptors from ``registry`` without mutating it.

    The helper takes its inventory as a parameter so generated tests can drive
    the query with synthetic descriptors and an independent oracle.

    Returns
    -------
    tuple[RuleMetadata, ...]
        Matching descriptors in ascending code order.
    """
    return tuple(
        sorted(
            (rule for rule in registry if _matches(rule, filters)),
            key=lambda rule: rule.code,
        )
    )


def _lookup_rule(
    registry: cabc.Sequence[RuleMetadata],
    code: str,
) -> RuleMetadata:
    """Return the descriptor with the exact code.

    Returns
    -------
    RuleMetadata
        The first descriptor whose code matches exactly.

    Raises
    ------
    RuleNotFoundError
        No descriptor in ``registry`` has the exact code.
    """
    for rule in registry:
        if rule.code == code:
            return rule
    raise RuleNotFoundError(code)


def _matches(rule: RuleMetadata, filters: RuleFilters) -> bool:
    """Return whether one descriptor satisfies every supplied filter."""
    description = rule.description
    wanted = (
        (filters.pack, rule.pack),
        (filters.severity, rule.default_severity),
        (filters.preview, description.preview),
        (filters.fixable, description.fixable),
    )
    prefix_matches = filters.prefix is None or rule.code.startswith(filters.prefix)
    return prefix_matches and all(
        expected is None or value == expected for expected, value in wanted
    )
