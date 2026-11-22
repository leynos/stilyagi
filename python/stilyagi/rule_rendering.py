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

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    import collections.abc as cabc

    from stilyagi.rules.base import RegionTarget, RuleMetadata
    from stilyagi.rules.description import (
        OptionDefault,
        RuleConfiguration,
        RuleExample,
        RuleOption,
    )

#: Version of the JSON envelope and descriptor shape.
SCHEMA_VERSION = 1

_OUTPUT_FORMATS: typ.Final[frozenset[str]] = frozenset({"text", "json"})
_LIST_COLUMNS = ("CODE", "NAME", "SEVERITY", "FIX-MODE", "DEFAULT", "PREVIEW")
_COLUMN_GAP = "  "

__all__ = ["SCHEMA_VERSION", "render_rule_detail", "render_rule_list"]


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
        return _dump_json({
            "schema_version": SCHEMA_VERSION,
            "rules": _descriptors(rules),
        })
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
        return _dump_json({"schema_version": SCHEMA_VERSION, "rule": _descriptor(rule)})
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
    """Append one labelled section, rendering an empty body as ``None``."""
    lines.extend(("", f"{heading}:"))
    entries = body or ["None"]
    for entry in entries:
        lines.extend(_indented(entry.splitlines(), "  "))


def _target_lines(target: RegionTarget) -> list[str]:
    """Render one target's syntax, kinds, and required scope tags."""
    scope = ", ".join(target.scope_has) if target.scope_has else "None"
    return [
        f"syntax: {target.syntax}",
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
        f"  expected exit status: {example.exit_code}",
    ))
    return lines


def _indented(lines: cabc.Sequence[str], prefix: str) -> list[str]:
    """Indent non-empty lines, leaving blank lines without trailing spaces."""
    return [f"{prefix}{line}" if line else "" for line in lines]


def _render_default(default: OptionDefault) -> str:
    """Render an option default as JSON-compatible text."""
    if isinstance(default, bool):
        return str(default).lower()
    return json.dumps(list(default), ensure_ascii=False)


def _descriptors(rules: cabc.Iterable[RuleMetadata]) -> list[dict[str, object]]:
    """Render every descriptor in the caller's order."""
    return [_descriptor(rule) for rule in rules]


def _descriptor(rule: RuleMetadata) -> dict[str, object]:
    """Render one descriptor with the fixed schema-version-1 key order."""
    description = rule.description
    return {
        "code": rule.code,
        "name": rule.name,
        "pack": rule.pack,
        "summary": description.summary,
        "explanation": description.explanation,
        "default_severity": rule.default_severity,
        "targets": [_target_descriptor(rule.target)],
        "requires": sorted(description.requires),
        "requires_nlp": rule.requires_nlp,
        "fixable": description.fixable,
        "fix_mode": description.fix_mode,
        "fixes": description.fixes,
        "enabled_by_default": description.enabled_by_default,
        "preview": description.preview,
        "configuration": _configuration_descriptor(description.configuration),
        "examples": [
            {
                "title": example.title,
                "source": example.source,
                "configuration": example.configuration,
                "expected_codes": list(example.expected_codes),
            }
            for example in description.examples
        ],
        "limitations": list(description.limitations),
        "references": list(description.references),
    }


def _target_descriptor(target: RegionTarget) -> dict[str, object]:
    """Render one target with its set-like arrays sorted lexically."""
    return {
        "syntax": target.syntax,
        "kinds": sorted(target.kinds),
        "scope_has": sorted(target.scope_has),
    }


def _configuration_descriptor(configuration: RuleConfiguration) -> dict[str, object]:
    """Render a configuration record and its typed options."""
    return {
        "enablement": configuration.enablement,
        "toml": configuration.toml,
        "options": [_option_descriptor(option) for option in configuration.options],
    }


def _option_descriptor(option: RuleOption) -> dict[str, object]:
    """Render one typed option in the fixed schema-version-1 shape."""
    return {
        "name": option.name,
        "type": option.type,
        "default": (
            option.default if isinstance(option.default, bool) else list(option.default)
        ),
        "description": option.description,
        "constraints": list(option.constraints),
        "variants": [
            {"value": variant.value, "description": variant.description}
            for variant in option.variants
        ],
    }


def _dump_json(payload: dict[str, object]) -> str:
    """Serialize one explicit payload in its constructed key order."""
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _yes_no(*, value: bool) -> str:
    """Render a boolean as the stable ``yes`` or ``no`` vocabulary."""
    return "yes" if value else "no"
