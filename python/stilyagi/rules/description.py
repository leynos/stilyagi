"""Immutable documentation records for the shipped builtin rules.

The catalogue publishes what a rule promises: its policy, typed options,
examples, limitations, and fix mode. These records are domain data. They carry
no argparse, JSON, or filesystem knowledge; a command adapter renders them.

The records deliberately model only the option types the starter pack actually
ships -- a boolean and an array of strings -- rather than a generic schema
language for plugins that do not exist yet. Fixability is derived from the
stored fix mode so the two can never disagree.
"""

import dataclasses as dc
import typing as typ

type FixMode = typ.Literal["safe", "unsafe", "manual", "none"]
type SeverityName = typ.Literal["error", "warning", "info"]
type OptionType = typ.Literal["boolean", "array[string]"]
type OptionDefault = bool | tuple[str, ...]

#: Capability vocabulary from RFC 0002. The starter pack needs structure and
#: lightweight tokens; it never needs an NLP provider.
CAPABILITY_STRUCTURE: typ.Final = "STRUCTURE"
CAPABILITY_TOKENS: typ.Final = "TOKENS"
CAPABILITY_NLP: typ.Final = "NLP"
CAPABILITIES: typ.Final[frozenset[str]] = frozenset({
    CAPABILITY_STRUCTURE,
    CAPABILITY_TOKENS,
    CAPABILITY_NLP,
})
FIX_MODES: typ.Final[frozenset[str]] = frozenset({"safe", "unsafe", "manual", "none"})
EDIT_CAPABLE_FIX_MODES: typ.Final[frozenset[str]] = frozenset({"safe", "unsafe"})
SEVERITY_NAMES: typ.Final[frozenset[str]] = frozenset({"error", "warning", "info"})


@dc.dataclass(frozen=True, slots=True)
class OptionVariant:
    """One documented boolean variant of a rule option.

    Parameters
    ----------
    value:
        The boolean value the variant selects.
    description:
        What the rule does when the option holds ``value``.
    """

    value: bool
    description: str

    def __post_init__(self) -> None:
        """Reject a variant that does not model a boolean choice."""
        if not isinstance(self.value, bool):
            message = "option variant value must be a boolean"
            raise TypeError(message)


@dc.dataclass(frozen=True, slots=True)
class RuleOption:
    """One typed configuration option a rule understands.

    Parameters
    ----------
    name:
        TOML key under ``[tool.stilyagi.rule.CODE]``.
    type:
        The documented value shape. Only the shapes the starter pack ships are
        modelled.
    default:
        The value used when the option is absent, matching :attr:`type`.
    description:
        What the option controls.
    constraints:
        Validation rules enforced by the real parser, in authored order.
    variants:
        Boolean variants in ``false`` then ``true`` order, or empty for an
        array option.
    """

    name: str
    type: OptionType
    default: OptionDefault
    description: str
    constraints: tuple[str, ...] = ()
    variants: tuple[OptionVariant, ...] = ()

    def __post_init__(self) -> None:
        """Reject an option whose default or variants contradict its type."""
        if not self.name:
            message = "option name must be non-empty"
            raise ValueError(message)
        validator = _OPTION_VALIDATORS.get(self.type)
        if validator is None:  # pragma: no cover - the literal type exhausts it
            message = f"unsupported option type: {self.type}"
            raise ValueError(message)
        validator(self)


def _require_boolean_option(option: RuleOption) -> None:
    """Validate a boolean option's default and two ordered variants."""
    if not isinstance(option.default, bool):
        message = f"boolean option {option.name!r} needs a boolean default"
        raise TypeError(message)
    values = tuple(variant.value for variant in option.variants)
    if values != (False, True):
        message = f"boolean option {option.name!r} needs false then true variants"
        raise ValueError(message)


def _require_array_option(option: RuleOption) -> None:
    """Validate an array option's tuple default and absent variants."""
    if not isinstance(option.default, tuple):
        message = f"array option {option.name!r} needs a tuple default"
        raise TypeError(message)
    if any(not isinstance(item, str) for item in option.default):
        message = f"array option {option.name!r} needs only string elements"
        raise TypeError(message)
    if option.variants:
        message = f"array option {option.name!r} cannot declare variants"
        raise ValueError(message)


_OPTION_VALIDATORS = {
    "boolean": _require_boolean_option,
    "array[string]": _require_array_option,
}


@dc.dataclass(frozen=True, slots=True)
class RuleConfiguration:
    """How a rule is enabled and configured.

    Parameters
    ----------
    enablement:
        Prose explaining selection, plugin, ignore, and suppression effects.
    toml:
        A complete TOML example, or an empty string when the defaults need no
        configuration.
    options:
        Typed option records in authored order.
    """

    enablement: str
    toml: str = ""
    options: tuple[RuleOption, ...] = ()

    def __post_init__(self) -> None:
        """Reject duplicate option names, which would make documentation lie."""
        names = [option.name for option in self.options]
        if len(names) != len(set(names)):
            message = "rule options must have unique names"
            raise ValueError(message)


@dc.dataclass(frozen=True, slots=True)
class RuleExample:
    """One executable example of a rule's behaviour.

    Parameters
    ----------
    title:
        What the example demonstrates.
    source:
        The Markdown source to lint.
    configuration:
        Complete TOML that selects and configures the rule, or an empty string
        when the default configuration demonstrates the behaviour.
    expected_codes:
        Diagnostic codes the example produces, in observed order.
    """

    title: str
    source: str
    configuration: str = ""
    expected_codes: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        r"""The check exit status this example documents.

        Returns
        -------
        int
            ``1`` when the example reports at least one finding, otherwise
            ``0``. The example contract assumes a check over a document whose
            only findings are the documented ones.

        Examples
        --------
        >>> RuleExample(title="clean", source="x\n").exit_code
        0
        >>> RuleExample(
        ...     title="finding", source="x\n", expected_codes=("MD001",)
        ... ).exit_code
        1
        """
        return 1 if self.expected_codes else 0


def _require_capabilities(requires: tuple[str, ...]) -> None:
    """Reject capabilities that are unsorted, duplicated, or unknown."""
    if requires != tuple(sorted(set(requires))):
        message = "requires must be sorted and unique"
        raise ValueError(message)
    unknown = set(requires) - CAPABILITIES
    if unknown:
        message = f"unsupported capability: {min(unknown)}"
        raise ValueError(message)


def _require_fix_mode(fix_mode: str) -> None:
    """Reject a fix mode outside the published vocabulary."""
    if fix_mode not in FIX_MODES:
        message = f"unsupported fix mode: {fix_mode}"
        raise ValueError(message)


def _require_preview(*, preview: bool) -> None:
    """Reject a preview flag that is not a boolean."""
    if not isinstance(preview, bool):
        message = "preview must be a boolean"
        raise TypeError(message)


@dc.dataclass(frozen=True, slots=True)
class RuleDescription:
    """The policy and documentation a builtin rule publishes.

    Parameters
    ----------
    summary:
        One-sentence statement of what the rule reports.
    explanation:
        The matching or structural rule in full.
    requires:
        Capability names from RFC 0002, sorted and unique.
    fix_mode:
        ``safe``, ``unsafe``, ``manual``, or ``none``. Fixability is derived
        from this value rather than stored separately.
    enabled_by_default:
        Whether the shipped default selection enables the rule.
    configuration:
        Enablement guidance, TOML example, and typed options.
    fixes:
        What a fix can and cannot do, including any opt-in it requires.
    preview:
        Whether the rule is preview-only.
    examples:
        Executable examples in authored order.
    limitations:
        Known false-positive, coverage, or unsupported-policy limits.
    references:
        Stable repository paths or URLs.
    """

    summary: str
    explanation: str
    requires: tuple[str, ...]
    fix_mode: FixMode
    enabled_by_default: bool
    configuration: RuleConfiguration
    fixes: str
    preview: bool = False
    examples: tuple[RuleExample, ...] = ()
    limitations: tuple[str, ...] = ()
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject capability or fix-mode metadata the catalogue cannot honour."""
        _require_capabilities(self.requires)
        _require_fix_mode(self.fix_mode)
        _require_preview(preview=self.preview)

    @property
    def fixable(self) -> bool:
        """Whether the rule can propose an actual edit.

        Returns
        -------
        bool
            ``True`` for ``safe`` and ``unsafe`` modes, ``False`` for
            ``manual`` and ``none``. A manual fix describes a repair but never
            edits source, so it is not fixable.

        Examples
        --------
        >>> from stilyagi.rules.description import RuleConfiguration
        >>> description = RuleDescription(
        ...     summary="s",
        ...     explanation="e",
        ...     requires=("STRUCTURE",),
        ...     fix_mode="manual",
        ...     enabled_by_default=True,
        ...     configuration=RuleConfiguration("enable"),
        ...     fixes="manual guidance",
        ... )
        >>> description.fixable
        False
        """
        return self.fix_mode in EDIT_CAPABLE_FIX_MODES


__all__ = [
    "CAPABILITIES",
    "CAPABILITY_NLP",
    "CAPABILITY_STRUCTURE",
    "CAPABILITY_TOKENS",
    "EDIT_CAPABLE_FIX_MODES",
    "FIX_MODES",
    "SEVERITY_NAMES",
    "FixMode",
    "OptionDefault",
    "OptionType",
    "OptionVariant",
    "RuleConfiguration",
    "RuleDescription",
    "RuleExample",
    "RuleOption",
    "SeverityName",
]
