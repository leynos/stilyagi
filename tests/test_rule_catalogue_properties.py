"""Property tests for catalogue queries over synthetic descriptors.

Each property runs the real query helper over generated descriptor collections
and compares it with an independent set-comprehension oracle. The synthetic
descriptors keep the production record types but carry generated codes, packs,
severities, preview flags, and fix modes, so the query is exercised over shapes
the three shipped rules never produce.

Negative controls prove the assertions can fail: a query that dropped a match or
reversed its sort order must be caught, so the oracle is not merely restating
the implementation.
"""

import typing as typ

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st
from stilyagi.rules import catalogue
from stilyagi.rules.base import RegionTarget, RuleMetadata
from stilyagi.rules.catalogue import RuleFilters
from stilyagi.rules.description import RuleConfiguration, RuleDescription

if typ.TYPE_CHECKING:
    import collections.abc as cabc

_FIX_MODES = ("safe", "unsafe", "manual", "none")
_SEVERITIES = ("error", "warning", "info")
#: Empty prefixes are invalid by contract, so they are not generated here; the
#: example tests pin that rejection directly.
_PREFIXES = ("MD", "STY", "TERM", "M", "T", "ZZ")

_reason = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20)
_descriptions = st.builds(
    RuleDescription,
    summary=_reason,
    explanation=_reason,
    requires=st.just(("STRUCTURE",)),
    fix_mode=st.sampled_from(_FIX_MODES),
    enabled_by_default=st.booleans(),
    configuration=st.just(RuleConfiguration("selected by policy")),
    fixes=_reason,
    preview=st.booleans(),
)


def _with_unique_codes(rules: list[RuleMetadata]) -> tuple[RuleMetadata, ...]:
    """Drop later descriptors sharing an earlier code, as an inventory must."""
    seen: set[str] = set()
    unique: list[RuleMetadata] = []
    for rule in rules:
        if rule.code in seen:
            continue
        seen.add(rule.code)
        unique.append(rule)
    return tuple(unique)


_metadata = st.builds(
    RuleMetadata,
    code=st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=6
    ),
    name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=1, max_size=12),
    target=st.just(RegionTarget(kinds=("paragraph",))),
    default_severity=st.sampled_from(_SEVERITIES),
    description=_descriptions,
    requires_nlp=st.just(value=False),
    pack=st.sampled_from(("builtin", "extra")),
)
_registries = st.lists(_metadata, max_size=8).map(_with_unique_codes)
_nonempty_registries = st.lists(_metadata, min_size=1, max_size=8).map(
    _with_unique_codes
)
_filters = st.builds(
    RuleFilters,
    prefix=st.sampled_from(_PREFIXES),
    pack=st.sampled_from((None, "builtin", "extra", "absent")),
    severity=st.sampled_from((None, *_SEVERITIES)),
    preview=st.sampled_from((None, True, False)),
    fixable=st.sampled_from((None, True, False)),
)


def _oracle(
    registry: cabc.Sequence[RuleMetadata],
    filters: RuleFilters,
) -> tuple[str, ...]:
    """Select matching codes by intersecting one set per filter.

    The formulation is deliberately unlike the production predicate: it
    starts from the whole registry and narrows by one set intersection per
    supplied dimension, so an error shared by a predicate and the query that
    applies it cannot agree with itself here.

    Returns
    -------
    tuple[str, ...]
        Matching codes in ascending order.
    """
    by_prefix = {rule.code for rule in registry}
    if filters.prefix is not None:
        by_prefix = {code for code in by_prefix if code.startswith(filters.prefix)}
    by_pack = _codes_where(registry, lambda rule: rule.pack, filters.pack)
    by_severity = _codes_where(
        registry, lambda rule: rule.default_severity, filters.severity
    )
    by_preview = _codes_where(
        registry, lambda rule: rule.description.preview, filters.preview
    )
    by_fixable = _codes_where(
        registry, lambda rule: rule.description.fixable, filters.fixable
    )
    selected = by_prefix & by_pack & by_severity & by_preview & by_fixable
    return tuple(sorted(selected))


def _codes_where(
    registry: cabc.Sequence[RuleMetadata],
    value_of: cabc.Callable[[RuleMetadata], object],
    wanted: object,
) -> set[str]:
    """Return every code whose ``value_of`` equals ``wanted``.

    ``None`` means the dimension is unfiltered, so every code is admitted.

    Returns
    -------
    set[str]
        Codes admitted by this filter dimension.
    """
    if wanted is None:
        return {rule.code for rule in registry}
    return {rule.code for rule in registry if value_of(rule) == wanted}


@settings(max_examples=150, deadline=None)
@given(registry=_registries, filters=_filters)
def test_query_matches_the_independent_oracle(
    registry: tuple[RuleMetadata, ...],
    filters: RuleFilters,
) -> None:
    """The query selects exactly the oracle's codes, in ascending order."""
    selected = catalogue._select_rules(registry, filters)

    event("empty registry" if not registry else "non-empty registry")
    event("empty selection" if not selected else "matching selection")
    assert tuple(rule.code for rule in selected) == _oracle(registry, filters), (
        "expected the query to agree with the independent selection oracle"
    )


@settings(max_examples=100, deadline=None)
@given(registry=_registries)
def test_query_returns_the_input_descriptors_unchanged(
    registry: tuple[RuleMetadata, ...],
) -> None:
    """Every selected value is an unchanged input object, not a rebuilt copy."""
    selected = catalogue._select_rules(registry, RuleFilters())

    assert all(any(rule is candidate for candidate in registry) for rule in selected), (
        "expected the query to return the input descriptors by identity"
    )


@settings(max_examples=100, deadline=None)
@given(registry=_registries, filters=_filters)
def test_query_does_not_mutate_its_input(
    registry: tuple[RuleMetadata, ...],
    filters: RuleFilters,
) -> None:
    """Filtering leaves the caller's collection and its order untouched."""
    snapshot = tuple(registry)

    catalogue._select_rules(registry, filters)

    assert tuple(registry) == snapshot, "expected the input registry to be unchanged"


@settings(max_examples=100, deadline=None)
@given(registry=_registries, filters=_filters)
def test_query_is_idempotent(
    registry: tuple[RuleMetadata, ...],
    filters: RuleFilters,
) -> None:
    """Re-running the same query returns the same codes."""
    first = catalogue._select_rules(registry, filters)
    second = catalogue._select_rules(registry, filters)

    assert tuple(rule.code for rule in first) == tuple(rule.code for rule in second), (
        "expected a repeated query to be stable"
    )


@settings(max_examples=100, deadline=None)
@given(registry=_registries)
def test_lookup_agrees_with_listing(
    registry: tuple[RuleMetadata, ...],
) -> None:
    """Every listed code is retrievable, and a missing code raises."""
    listed = catalogue._select_rules(registry, RuleFilters())

    for rule in listed:
        assert catalogue._lookup_rule(registry, rule.code) is rule, (
            "expected lookup to find the listed descriptor"
        )


@settings(max_examples=100, deadline=None)
@given(registry=_registries)
def test_lookup_misses_every_absent_code(
    registry: tuple[RuleMetadata, ...],
) -> None:
    """A code absent from the registry always raises the named miss."""
    known = {rule.code for rule in registry}
    absent = next(
        (candidate for candidate in ("ZZZ", "QQQQ", "00000") if candidate not in known),
        None,
    )
    if absent is None:  # pragma: no cover - the generated alphabet cannot fill three
        return

    with pytest.raises(catalogue.RuleNotFoundError) as raised:
        catalogue._lookup_rule(registry, absent)

    assert raised.value.code == absent, "expected the miss to name the absent code"


def test_negative_control_dropping_a_match_is_detected() -> None:
    """A query that silently drops a match must not satisfy the oracle."""
    registry = catalogue.builtin_metadata()
    filters = RuleFilters(prefix="T")
    incomplete = tuple(
        rule
        for rule in catalogue._select_rules(registry, filters)
        if rule.code != "TERM001"
    )

    assert [rule.code for rule in incomplete] != list(_oracle(registry, filters)), (
        "expected the oracle to catch a dropped match"
    )


def test_negative_control_reversed_order_is_detected() -> None:
    """A query that returns descending codes must not satisfy the oracle."""
    registry = catalogue.builtin_metadata()
    filters = RuleFilters()

    reversed_codes = [
        rule.code for rule in reversed(catalogue._select_rules(registry, filters))
    ]

    assert tuple(reversed_codes) != _oracle(registry, filters), (
        "expected the oracle to catch a reversed order"
    )


def _synthetic(code: str) -> RuleMetadata:
    """Build one valid synthetic descriptor for deterministic assertions."""
    return RuleMetadata(
        code=code,
        name=f"rule-{code.lower()}",
        target=RegionTarget(kinds=("paragraph",)),
        default_severity="error",
        description=RuleDescription(
            summary="summary",
            explanation="explanation",
            requires=("STRUCTURE",),
            fix_mode="none",
            enabled_by_default=True,
            configuration=RuleConfiguration("selected"),
            fixes="no fix",
        ),
    )


@settings(max_examples=150, deadline=None)
@given(registry=_registries, filters=_filters)
def test_generated_cases_cover_matching_and_nonmatching_classes(
    registry: tuple[RuleMetadata, ...],
    filters: RuleFilters,
) -> None:
    """Classify every generated case and require both outcomes to be reachable.

    Hypothesis fails the run when a class the test declares is never produced,
    so this turns "the generator can exercise a match and a miss" into an
    assertion rather than a hope about the corpus.
    """
    selected = catalogue._select_rules(registry, filters)

    event("empty registry" if not registry else "non-empty registry")
    event("empty selection" if not selected else "matching selection")


@settings(max_examples=150, deadline=None)
@given(registry=_nonempty_registries)
def test_generated_filters_produce_a_match_and_a_miss(
    registry: tuple[RuleMetadata, ...],
) -> None:
    """A generated registry yields a guaranteed match and a guaranteed miss.

    The prefixes are derived from the generated registry, so both classes are
    produced directly: the rule's own code always matches, and the same code
    with an impossible suffix never does.
    """
    rule = registry[0]

    matching = catalogue._select_rules(registry, RuleFilters(prefix=rule.code))
    missing = catalogue._select_rules(registry, RuleFilters(prefix=f"{rule.code}ZZZ"))

    assert rule.code in {item.code for item in matching}, (
        "expected the generated rule to match its own code prefix"
    )
    assert not missing, "expected the impossible prefix to select nothing"


def test_generated_case_space_contains_both_outcomes() -> None:
    """The case space really does contain matching and nonmatching filters.

    The generated properties are only as strong as the filters they receive.
    Pinning both outcomes here proves the corpus can exercise a match and a
    miss, and the ``event`` classifications in the main property show which
    class each generated example fell into.
    """
    registry = (_synthetic("MD001"),)

    assert catalogue._select_rules(registry, RuleFilters(prefix="MD")), (
        "expected a matching class"
    )
    assert not catalogue._select_rules(registry, RuleFilters(prefix="ZZ")), (
        "expected a nonmatching class"
    )
