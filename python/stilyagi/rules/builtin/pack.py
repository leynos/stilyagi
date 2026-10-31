"""Inventory and runner for the starter builtin rule pack.

The starter pack declares three deterministic rules. ``MD`` structural rules
come first, then ``STY`` style rules, then opt-in ``TERM`` rules, which is the
documented code-prefix scheme.

Each rule runs once per document against only the regions its
:class:`~stilyagi.rules.base.RegionTarget` claims. Rules run in inventory order
so diagnostics are deterministic, and a rule still evaluates its full state
when its findings are later suppressed.
"""

import dataclasses as dc
import functools
import pathlib
import typing as typ

from stilyagi import diagnostics_location
from stilyagi.config import rules as rule_options
from stilyagi.engine import ir_view, rule_view
from stilyagi.rules.base import RegionTarget, RuleContext, RuleMetadata
from stilyagi.rules.builtin import banned_term, heading_depth, repeated_word, text
from stilyagi.rules.inline_code import InlineCodeIndex

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics
    from stilyagi.rules.policy import RulePolicy
    from stilyagi.rules.registry import RuleRunRequest

__all__ = [
    "BuiltinRule",
    "enabled_codes",
    "inventory",
    "registry_codes",
    "run_selected",
]

_TEXT_TARGET = RegionTarget(kinds=("heading", "paragraph", "table_cell"))


@dc.dataclass(frozen=True, slots=True)
class BuiltinRule:
    """One builtin rule: metadata plus its validated hook.

    Parameters
    ----------
    metadata:
        Stable public metadata for the rule.
    parser:
        Validator that turns the rule's raw config table into a frozen config.
    hook:
        The rule implementation, receiving only a ``RuleContext``.
    textual:
        Whether the rule reads tokenized segment text. Structural rules say
        ``False`` so the document's tokenization is not attached to them.
    """

    metadata: RuleMetadata
    parser: rule_options.RuleOptionParser
    hook: cabc.Callable[[RuleContext[typ.Any]], cabc.Iterable[diagnostics.Diagnostic]]
    textual: bool = False


_BUILTIN_RULES: tuple[BuiltinRule, ...] = (
    BuiltinRule(
        metadata=RuleMetadata(
            code="MD001",
            name="heading-depth",
            target=RegionTarget(kinds=("heading",)),
            default_severity="error",
        ),
        parser=functools.partial(
            rule_options.parse_optionless, config_type=rule_options.Md001Config
        ),
        hook=heading_depth.check_heading_depth,
    ),
    BuiltinRule(
        metadata=RuleMetadata(
            code="STY001",
            name="repeated-word",
            target=_TEXT_TARGET,
            default_severity="warning",
        ),
        parser=functools.partial(
            rule_options.parse_optionless, config_type=rule_options.Sty001Config
        ),
        hook=repeated_word.check_repeated_word,
        textual=True,
    ),
    BuiltinRule(
        metadata=RuleMetadata(
            code="TERM001",
            name="banned-term",
            target=_TEXT_TARGET,
            default_severity="error",
        ),
        parser=rule_options.parse_term001,
        hook=banned_term.check_banned_term,
        textual=True,
    ),
)


def inventory() -> tuple[RuleMetadata, ...]:
    """Return the builtin rule metadata in deterministic order.

    Returns
    -------
    tuple[RuleMetadata, ...]
        Builtin metadata, ordered by code prefix then code.

    Examples
    --------
    >>> [metadata.code for metadata in inventory()]
    ['MD001', 'STY001', 'TERM001']
    """
    return tuple(rule.metadata for rule in _BUILTIN_RULES)


def enabled_codes() -> tuple[str, ...]:
    """Return the builtin rule codes in execution order.

    Returns
    -------
    tuple[str, ...]
        Builtin codes.

    Examples
    --------
    >>> enabled_codes()
    ('MD001', 'STY001', 'TERM001')
    """
    return tuple(rule.metadata.code for rule in _BUILTIN_RULES)


def registry_codes(registry: cabc.Sequence[RuleMetadata]) -> frozenset[str]:
    """Return the set of codes present in ``registry``.

    Parameters
    ----------
    registry:
        Metadata inventory to read codes from.

    Returns
    -------
    frozenset[str]
        Every code declared by ``registry``.

    Examples
    --------
    >>> registry_codes(inventory()) == frozenset({'MD001','STY001','TERM001'})
    True
    """
    return frozenset(metadata.code for metadata in registry)


def run_selected(
    request: RuleRunRequest,
    registry: cabc.Sequence[RuleMetadata],
    request_policy: RulePolicy,
    *,
    document_view: rule_view.DocumentRegionView | None = None,
) -> tuple[diagnostics.Diagnostic, ...]:
    """Run every selected builtin rule for one document.

    Every recognized builtin table is validated, including a disabled rule's
    table, so an option error cannot hide behind selection. A disabled rule's
    hook is never called.

    The document's regions, line starts, inline-code index, and tokenized text
    segments are built once here and shared by every rule, so selecting a
    second text rule does not tokenize the document again and a document with
    many findings does not re-validate its line index for each one.

    Parameters
    ----------
    request:
        The per-document run request.
    registry:
        The builtin metadata inventory.
    request_policy:
        The resolved selection and suppression policy.
    document_view:
        The document projection the caller already built, when it has one.

    Returns
    -------
    tuple[diagnostics.Diagnostic, ...]
        Diagnostics in rule order, before suppression filtering.
    """
    codes = registry_codes(registry)
    view = document_view or rule_view.project(
        request.document, source_bytes=request.source_bytes
    )
    line_starts = diagnostics_location.validated_line_starts(
        ir_view.line_index(request.document)
    )
    inline_code = InlineCodeIndex.from_spans(view.inline_code_spans)
    tokenized = text.tokenize_segments(view.for_target(_TEXT_TARGET), inline_code)
    config_path = pathlib.Path(request.config_path or request.reported_path)
    produced: list[diagnostics.Diagnostic] = []
    for rule in _BUILTIN_RULES:
        if rule.metadata.code not in codes:
            continue
        parsed = rule.parser(
            rule_options.rule_table(request.config, rule.metadata.code),
            rule.metadata.code,
            config_path,
        )
        if not request_policy.is_enabled(rule.metadata.code):
            continue
        context = RuleContext(
            rule_config=parsed,
            document=request.document,
            source_bytes=request.source_bytes,
            reported_path=request.reported_path,
            line_starts=line_starts,
            inline_code=inline_code,
            regions=view.for_target(rule.metadata.target),
            tokenized_segments=tokenized if rule.textual else (),
        )
        produced.extend(rule.hook(context))
    return tuple(produced)
