"""Validation of the per-rule configuration tables the builtin pack consumes.

Each builtin rule owns a frozen option record. Its parser validates the raw
``[tool.stilyagi.rule.CODE]`` table into that record, so rule code never reads
a raw TOML mapping. Malformed values raise
:class:`stilyagi.config.InvalidConfigError` with the rule code and option name,
which the existing configuration error path reports before exiting 2.

Recognized builtin tables are validated even when the rule is not selected.
Tables for other rule families are preserved untouched for future slices.
"""

import collections.abc as cabc
import dataclasses as dc
import functools
import pathlib
import typing as typ

from .schema import InvalidConfigError

if typ.TYPE_CHECKING:
    from .schema import StilyagiConfig

type RuleOptionParser = cabc.Callable[
    [cabc.Mapping[str, object], str, pathlib.Path], object
]

_TERM_KEYS: frozenset[str] = frozenset({"terms", "case_sensitive"})
_EMPTY_KEYS: frozenset[str] = frozenset()
_DEFAULT_PATH = pathlib.Path("<config>")


@dc.dataclass(frozen=True, slots=True)
class Md001Config:
    """Configuration for ``MD001`` (heading depth).

    ``MD001`` has no options in this slice; the empty frozen record keeps the
    rule hook shape uniform with the other builtins.
    """


@dc.dataclass(frozen=True, slots=True)
class Sty001Config:
    """Configuration for ``STY001`` (repeated word).

    ``STY001`` has no options in this slice.
    """


@dc.dataclass(frozen=True, slots=True)
class Term001Config:
    """Configuration for ``TERM001`` (banned term).

    Parameters
    ----------
    terms:
        Configured terms, already normalized for the selected comparison mode
        and coalesced so no term is compared twice.
    case_sensitive:
        When true, compare the configured spelling exactly.
    """

    terms: tuple[str, ...] = ()
    case_sensitive: bool = False

    @property
    def is_active(self) -> bool:
        """Whether the rule has any configured term.

        Returns
        -------
        bool
            ``True`` when at least one term was configured.

        Examples
        --------
        >>> Term001Config().is_active
        False
        >>> Term001Config(("obviously",)).is_active
        True
        """
        return bool(self.terms)


def rule_table(config: StilyagiConfig, code: str) -> cabc.Mapping[str, object]:
    """Return the raw per-rule configuration table for ``code``.

    Parameters
    ----------
    config:
        Effective global configuration.
    code:
        Rule code whose table is requested.

    Returns
    -------
    collections.abc.Mapping[str, object]
        The rule's raw table, or an empty mapping when none was configured.

    Examples
    --------
    >>> from stilyagi.config.schema import StilyagiConfig
    >>> dict(rule_table(StilyagiConfig(), "TERM001"))
    {}
    """
    tables = getattr(config, "rules", None) or {}
    table = tables.get(code) if isinstance(tables, cabc.Mapping) else None
    return typ.cast("cabc.Mapping[str, object]", table) if table else {}


def validate_builtin_tables(
    config: StilyagiConfig,
    *,
    path: pathlib.Path = _DEFAULT_PATH,
) -> None:
    """Validate every recognized builtin rule table present in ``config``.

    A recognized table with an unknown option or a malformed value raises
    :class:`stilyagi.config.InvalidConfigError` naming the rule and option, so
    a broken table fails even when its rule is not selected.

    Parameters
    ----------
    config:
        Effective global configuration.
    path:
        Originating config or target path used in error keys.

    Examples
    --------
    >>> from stilyagi.config.schema import StilyagiConfig
    >>> validate_builtin_tables(StilyagiConfig())
    """
    for code, parser in _PARSERS:
        table = rule_table(config, code)
        if table:
            parser(table, code, path)


def parse_optionless[T](
    table: cabc.Mapping[str, object],
    code: str,
    path: pathlib.Path = _DEFAULT_PATH,
    *,
    config_type: type[T],
) -> T:
    """Validate a rule table that accepts no options into ``config_type``.

    Rules with no options share this parser; :data:`_PARSERS` and the builtin
    pack bind each one with :func:`functools.partial`. Any option present
    raises :class:`stilyagi.config.InvalidConfigError`, so a misspelled option
    cannot pass silently.

    Parameters
    ----------
    table:
        Raw ``[tool.stilyagi.rule.CODE]`` mapping.
    code:
        Rule code, used verbatim in error keys.
    path:
        Originating config path used in error keys.
    config_type:
        The empty frozen record the rule's options validate into.

    Returns
    -------
    T
        A fresh instance of ``config_type``.

    Examples
    --------
    >>> parse_optionless({}, "MD001", config_type=Md001Config)
    Md001Config()
    """
    _reject_unknown(table, code, _EMPTY_KEYS, path)
    return config_type()


def parse_term001(
    table: cabc.Mapping[str, object],
    code: str,
    path: pathlib.Path = _DEFAULT_PATH,
) -> Term001Config:
    """Validate a ``TERM001`` table into a frozen config.

    An unknown option, a term that is not a single alphabetic word, or a
    mistyped flag raises :class:`stilyagi.config.InvalidConfigError` naming the
    offending key.

    Parameters
    ----------
    table:
        Raw ``[tool.stilyagi.rule.TERM001]`` mapping.
    code:
        Rule code, used verbatim in error keys.
    path:
        Originating config path used in error keys.

    Returns
    -------
    Term001Config
        Frozen, validated configuration with terms normalized for comparison
        and duplicates coalesced.

    Examples
    --------
    >>> parse_term001({"terms": ["obviously"]}, "TERM001")
    Term001Config(terms=('obviously',), case_sensitive=False)
    """
    _reject_unknown(table, code, _TERM_KEYS, path)
    case_sensitive = _parse_case_sensitive(table, code, path)
    return Term001Config(
        terms=_parse_terms(table, code, path, case_sensitive=case_sensitive),
        case_sensitive=case_sensitive,
    )


def _reject_unknown(
    table: cabc.Mapping[str, object],
    code: str,
    allowed: frozenset[str],
    path: pathlib.Path,
) -> None:
    """Raise for the first unknown option in a recognized rule table."""
    unknown = set(table) - allowed
    if unknown:
        raise InvalidConfigError(
            path,
            f"rule.{code}.{min(unknown)}",
            "is not supported",
        )


def _parse_terms(
    table: cabc.Mapping[str, object],
    code: str,
    path: pathlib.Path,
    *,
    case_sensitive: bool,
) -> tuple[str, ...]:
    """Return normalized, deduplicated single-token terms."""
    raw = table.get("terms", ())
    if not isinstance(raw, cabc.Sequence) or isinstance(raw, (str, bytes)):
        raise InvalidConfigError(
            path, f"rule.{code}.terms", "must be a list of strings"
        )
    terms: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(typ.cast("cabc.Sequence[object]", raw)):
        term = _validated_term(entry, f"rule.{code}.terms[{index}]", path)
        normalized = term if case_sensitive else term.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
    return tuple(terms)


def _validated_term(entry: object, key: str, path: pathlib.Path) -> str:
    """Return one configured term, rejecting anything but a single word."""
    if not isinstance(entry, str):
        raise InvalidConfigError(path, key, "must be a string")
    if not entry.isalpha():
        raise InvalidConfigError(path, key, "must be a single alphabetic word")
    return entry


def _parse_case_sensitive(
    table: cabc.Mapping[str, object],
    code: str,
    path: pathlib.Path,
) -> bool:
    """Return the configured case-sensitivity flag."""
    value = table.get("case_sensitive", False)
    if not isinstance(value, bool):
        raise InvalidConfigError(
            path,
            f"rule.{code}.case_sensitive",
            "must be a boolean",
        )
    return value


_PARSERS: tuple[tuple[str, RuleOptionParser], ...] = (
    ("MD001", functools.partial(parse_optionless, config_type=Md001Config)),
    ("STY001", functools.partial(parse_optionless, config_type=Sty001Config)),
    ("TERM001", parse_term001),
)

__all__ = [
    "Md001Config",
    "RuleOptionParser",
    "Sty001Config",
    "Term001Config",
    "parse_optionless",
    "parse_term001",
    "rule_table",
    "validate_builtin_tables",
]
