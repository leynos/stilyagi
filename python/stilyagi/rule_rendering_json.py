"""Encode builtin rule descriptors as the schema-version-1 JSON shape.

The machine-readable half of the rule-presentation adapter. It reads the domain
records and returns plain dictionaries or a serialized envelope; it never
decides which rules exist, resolves configuration, or writes to a stream. It
sits apart from the text renderer so each format can change for its own reason
and a text-only edit cannot perturb the JSON contract.

The schema is version 1. Keys are written in a fixed order so a diff between two
envelopes shows semantic change rather than incidental reordering, and set-like
arrays are sorted so their order is stable.
"""

import collections.abc as cabc
import json
import typing as typ

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from stilyagi.rules.base import RegionTarget, RuleMetadata
    from stilyagi.rules.description import (
        RuleConfiguration,
        RuleExample,
        RuleOption,
    )

__all__ = [
    "SCHEMA_VERSION",
    "descriptor",
    "descriptors",
    "envelope",
]

#: Version of the JSON envelope and descriptor shape.
SCHEMA_VERSION = 1

#: How an example's documented exit status is derived. Injected rather than
#: imported so this encoder stays independent of the text renderer.
type ExitCode = cabc.Callable[[RuleExample], int]


def envelope(payload_key: str, payload: object) -> str:
    """Wrap one payload in the schema-version-1 envelope and serialize it.

    Both commands publish the same envelope with a single payload key, so the
    wrapper is written once; only the key and payload differ. The caller names
    the key because it also owns the payload's shape.

    Parameters
    ----------
    payload_key:
        The envelope key the payload sits under, ``rules`` or ``rule``.
    payload:
        The already-encoded descriptor or descriptor list.

    Returns
    -------
    str
        The complete envelope, ending in one newline.
    """
    return _dump_json({
        "schema_version": SCHEMA_VERSION,
        payload_key: payload,
    })


def descriptors(
    rules: cabc.Iterable[RuleMetadata],
    *,
    exit_code: ExitCode,
) -> list[dict[str, object]]:
    """Encode every descriptor in the caller's order.

    Returns
    -------
    list[dict[str, object]]
        One JSON-ready mapping per rule.
    """
    return [descriptor(rule, exit_code=exit_code) for rule in rules]


def descriptor(
    rule: RuleMetadata,
    *,
    exit_code: ExitCode,
) -> dict[str, object]:
    """Encode one descriptor with the fixed schema-version-1 key order.

    Returns
    -------
    dict[str, object]
        The rule as a JSON-ready mapping.
    """
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
                "exit_code": exit_code(example),
            }
            for example in description.examples
        ],
        "limitations": list(description.limitations),
        "references": list(description.references),
    }


def _target_descriptor(target: RegionTarget) -> dict[str, object]:
    """Encode one target with its set-like arrays sorted lexically.

    The schema-version-1 `syntax` key stays a single string for consumers that
    already parse it, and repeats the target's declared syntaxes joined by a
    comma when a rule reads more than one language. `kinds`, `scope_has`, and
    `owner_kinds` are sorted arrays so their order is stable. An empty
    `owner_kinds` array places no requirement on the region's owner, which
    includes a region that records none.

    Returns
    -------
    dict[str, object]
        The target as a JSON-ready mapping.
    """
    return {
        "syntax": ",".join(target.syntaxes),
        "kinds": sorted(target.kinds),
        "scope_has": sorted(target.scope_has),
        "owner_kinds": sorted(target.owner_kinds),
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
