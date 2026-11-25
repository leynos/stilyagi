"""Render builtin rule descriptions as stable text or JSON.

Rendering is an adapter over the domain records: it reads them and writes
strings. It never resolves configuration, extracts a document, or runs a rule.

Text output uses fixed columns computed from the values themselves, so it is
independent of the terminal width and carries no colour. JSON output uses an
explicit key order and a schema version, so a consumer can parse it without
guessing. Every successful rendering ends in exactly one newline.
"""

import json
import typing as typ

from stilyagi import rule_rendering_json
from stilyagi.check_outcome import compute_exit_code
from stilyagi.diagnostics import Diagnostic, Severity
from stilyagi.rule_rendering_json import SCHEMA_VERSION

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.rules.base import RegionTarget, RuleMetadata
    from stilyagi.rules.description import (
        OptionDefault,
        RuleConfiguration,
        RuleExample,
        RuleOption,
    )

_OUTPUT_FORMATS: typ.Final[frozenset[str]] = frozenset({"text", "json"})
_LIST_COLUMNS = ("CODE", "NAME", "SEVERITY", "FIX-MODE", "DEFAULT", "PREVIEW")
_COLUMN_GAP = "  "

__all__ = [
    "SCHEMA_VERSION",
    "example_exit_code",
    "render_rule_detail",
    "render_rule_list",
]


def render_rule_list(
    rules: cabc.Sequence[RuleMetadata],
    output_format: str = "text",
) -> str:
    """Render a catalogue list in the requested format.

    Parameters
    ----------
    rules:
        Descriptors in the order they should be presented. The catalogue query
        already sorts them by code.
    output_format:
        ``text`` or ``json``.

    Returns
    -------
    str
        The complete result, ending in one newline.

    Examples
    --------
    >>> from stilyagi.rules.catalogue import list_rules
    >>> text = render_rule_list(list_rules())
    >>> text.splitlines()[0].split()
    ['CODE', 'NAME', 'SEVERITY', 'FIX-MODE', 'DEFAULT', 'PREVIEW']
    """
    _require_output_format(output_format)
    if output_format == "json":
        return rule_rendering_json.envelope(
            "rules",
            rule_rendering_json.descriptors(rules, exit_code=example_exit_code),
        )
    return _render_list_text(rules)


def render_rule_detail(
    rule: RuleMetadata,
    output_format: str = "text",
) -> str:
    """Render one rule's complete documentation in the requested format.

    Parameters
    ----------
    rule:
        The descriptor to render.
    output_format:
        ``text`` or ``json``.

    Returns
    -------
    str
        The complete result, ending in one newline.

    Examples
    --------
    >>> from stilyagi.rules.catalogue import get_rule
    >>> render_rule_detail(get_rule("MD001")).splitlines()[0]
    'MD001 heading-depth'
    """
    _require_output_format(output_format)
    if output_format == "json":
        return rule_rendering_json.envelope(
            "rule",
            rule_rendering_json.descriptor(rule, exit_code=example_exit_code),
        )
    return _render_detail_text(rule)


def _require_output_format(output_format: str) -> None:
    """Reject a rendering format this adapter does not implement."""
    if output_format not in _OUTPUT_FORMATS:
        message = f"unsupported output format: {output_format}"
        raise ValueError(message)


def _render_list_text(rules: cabc.Sequence[RuleMetadata]) -> str:
    """Render the fixed-column list or its documented no-match sentence."""
    if not rules:
        return "No builtin rules match the supplied filters.\n"
    rows = [_LIST_COLUMNS, *(_list_row(rule) for rule in rules)]
    widths = [
        max(len(row[index]) for row in rows) for index in range(len(_LIST_COLUMNS))
    ]
    return "\n".join(_format_row(row, widths) for row in rows) + "\n"


def _list_row(rule: RuleMetadata) -> tuple[str, ...]:
    """Return one rule's list cells in column order."""
    description = rule.description
    return (
        rule.code,
        rule.name,
        rule.default_severity,
        description.fix_mode,
        _yes_no(value=description.enabled_by_default),
        _yes_no(value=description.preview),
    )


def _format_row(row: cabc.Sequence[str], widths: cabc.Sequence[int]) -> str:
    """Join one row, padding every cell except the last."""
    cells = (value.ljust(widths[index]) for index, value in enumerate(row[:-1]))
    return _COLUMN_GAP.join((*cells, row[-1]))


def _render_detail_text(rule: RuleMetadata) -> str:
    """Render one descriptor as the labelled text document."""
    description = rule.description
    lines = [
        f"{rule.code} {rule.name}",
        f"Default severity: {rule.default_severity}",
        f"Pack: {rule.pack}",
        f"Enabled by default: {_yes_no(value=description.enabled_by_default)}",
        f"Preview: {_yes_no(value=description.preview)}",
        f"Fixable: {_yes_no(value=description.fixable)}",
        f"Fix mode: {description.fix_mode}",
    ]
    _append_section(lines, "Summary", [description.summary])
    _append_section(lines, "Explanation", [description.explanation])
    _append_section(lines, "Targets", _target_lines(rule.target))
    _append_section(lines, "Capabilities", list(description.requires))
    _append_section(
        lines, "Policy/enablement", _configuration_lines(description.configuration)
    )
    _append_section(lines, "Fixes", [description.fixes])
    _append_section(lines, "Options", _option_lines(description.configuration.options))
    _append_section(lines, "Examples", _example_lines(description.examples))
    _append_section(lines, "Limitations", list(description.limitations))
    _append_section(lines, "References", list(description.references))
    return "\n".join(lines) + "\n"


def _append_section(
    lines: list[str],
    heading: str,
    body: cabc.Sequence[str],
) -> None:
    """Append one labelled section, rendering an empty body as ``None``.

    A body is a sequence of entries, and an entry may itself be several lines
    (a source snippet, a TOML table). Each entry's lines are indented and kept
    as they are, including a blank line *inside* an entry. Splitting an empty
    entry with `str.splitlines` would yield no lines at all and silently drop
    a separator the entry deliberately contains, so the split is only applied
    to a non-empty entry.
    """
    lines.extend(("", f"{heading}:"))
    entries = body or ["None"]
    for entry in entries:
        entry_lines = entry.splitlines() if entry else [""]
        lines.extend(_indented(entry_lines, "  "))


def _target_lines(target: RegionTarget) -> list[str]:
    """Render one target's syntaxes, kinds, and required scope tags."""
    scope = ", ".join(target.scope_has) if target.scope_has else "None"
    return [
        f"syntaxes: {', '.join(target.syntaxes)}",
        f"kinds: {', '.join(target.kinds)}",
        f"scope requires: {scope}",
    ]


def _configuration_lines(configuration: RuleConfiguration) -> list[str]:
    """Render enablement guidance followed by its complete TOML example."""
    lines = [configuration.enablement, "TOML:"]
    lines.extend(configuration.toml.splitlines() or ["None"])
    return lines


def _option_lines(options: cabc.Sequence[RuleOption]) -> list[str]:
    """Render every option with its type, default, constraints, and variants."""
    return _joined_blocks(options, _one_option_lines)


def _one_option_lines(option: RuleOption) -> list[str]:
    """Render one option block."""
    lines = [
        option.name,
        f"  type: {option.type}",
        f"  default: {_render_default(option.default)}",
        f"  description: {option.description}",
        "  constraints:",
    ]
    lines.extend(
        [f"    - {constraint}" for constraint in option.constraints] or ["    None"]
    )
    lines.append("  variants:")
    lines.extend(
        [
            f"    {str(variant.value).lower()}: {variant.description}"
            for variant in option.variants
        ]
        or ["    None"]
    )
    return lines


def _example_lines(examples: cabc.Sequence[RuleExample]) -> list[str]:
    """Render every example's source, configuration, and expected codes."""
    return _joined_blocks(examples, _one_example_lines)


def _joined_blocks[BlockT](
    items: cabc.Sequence[BlockT],
    render_one: cabc.Callable[[BlockT], list[str]],
) -> list[str]:
    """Render one block per item, separated by a blank line."""
    lines: list[str] = []
    for item in items:
        if lines:
            lines.append("")
        lines.extend(render_one(item))
    return lines


def _one_example_lines(example: RuleExample) -> list[str]:
    """Render one executable example block."""
    codes = ", ".join(example.expected_codes) if example.expected_codes else "None"
    configuration = example.configuration.splitlines() or ["defaults"]
    lines = [example.title, "  source:"]
    lines.extend(_indented(example.source.splitlines() or [""], "    "))
    lines.append("  configuration:")
    lines.extend(_indented(configuration, "    "))
    lines.extend((
        f"  expected codes: {codes}",
        f"  expected exit status: {example_exit_code(example)}",
    ))
    return lines


def example_exit_code(example: RuleExample) -> int:
    r"""Derive an example's documented check status from the catalogue policy.

    The status is what `stilyagi check` would return for the diagnostics the
    example reports, so it comes from the same exit policy rather than a value
    authored alongside the domain record. An example that reports no codes
    produces no diagnostics, and one that reports codes produces diagnostics
    whose severities the catalogue already declares.

    Parameters
    ----------
    example:
        The example whose status is derived.

    Returns
    -------
    int
        ``1`` when an error-severity diagnostic is produced, otherwise ``0``.

    Examples
    --------
    >>> from stilyagi.rules.description import RuleExample
    >>> example_exit_code(RuleExample(title="clean", source="text\n"))
    0
    >>> example_exit_code(
    ...     RuleExample(
    ...         title="finding",
    ...         source="# A\n### B\n",
    ...         expected_codes=("MD001",),
    ...     )
    ... )
    1
    """
    return compute_exit_code(_example_diagnostics(example))


def _example_diagnostics(example: RuleExample) -> tuple[Diagnostic, ...]:
    """Build the diagnostics an example's expected codes stand for.

    A code's severity is looked up in the shipped inventory, so the derived
    status follows the same metadata the contract tests assert. A code the
    inventory does not declare is treated as an error, which is the policy's
    own default for an unclassified diagnostic.

    Returns
    -------
    tuple[Diagnostic, ...]
        One diagnostic per expected code, in the example's authored order.
    """
    from stilyagi.rules.catalogue import list_rules

    severity_of = {rule.code: Severity(rule.default_severity) for rule in list_rules()}
    return tuple(
        Diagnostic(
            path="example.md",
            code=code,
            message="",
            severity=severity_of.get(code, Severity.ERROR),
        )
        for code in example.expected_codes
    )


def _indented(lines: cabc.Sequence[str], prefix: str) -> list[str]:
    """Indent non-empty lines, leaving blank lines without trailing spaces."""
    return [f"{prefix}{line}" if line else "" for line in lines]


def _render_default(default: OptionDefault) -> str:
    """Render an option default as JSON-compatible text."""
    if isinstance(default, bool):
        return str(default).lower()
    return json.dumps(list(default), ensure_ascii=False)


def _yes_no(*, value: bool) -> str:
    """Render a boolean as the stable ``yes`` or ``no`` vocabulary."""
    return "yes" if value else "no"
