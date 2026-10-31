"""Rule selection, per-file ignores, and suppression filtering.

The policy layer decides *which* rules run and *whether* a produced finding
survives. It is deliberately separate from rule behaviour so that selection
precedence can be tested as a truth table without exercising any rule.
"""

import collections.abc as cabc
import dataclasses as dc
import fnmatch
import posixpath
import typing as typ

from stilyagi.rules.suppression import (
    SuppressionPlan,
    expand_prefixes,
    resolve_suppressions,
)

if typ.TYPE_CHECKING:
    from stilyagi.config import StilyagiConfig
    from stilyagi.diagnostics import Diagnostic
    from stilyagi.engine.rule_projection import DocumentRegionView
    from stilyagi.rules.base import RuleMetadata
    from stilyagi.rules.registry import RuleRunRequest

__all__ = [
    "RulePolicy",
    "filter_diagnostics",
    "resolve_policy",
]


@dc.dataclass(frozen=True, slots=True)
class RulePolicy:
    """The resolved selection and suppression decision for one document.

    Parameters
    ----------
    enabled:
        Rule codes that may run for this file, in registry order.
    selected:
        Codes selected by ``lint.select`` before ignores are applied.
    ignored:
        Codes removed by ``lint.ignore``.
    per_file_ignored:
        Codes removed by a matching ``lint.per-file-ignores`` glob.
    plugin_enabled:
        Whether the builtin pack was named by ``plugins``.
    suppressions:
        Resolved IR suppression decisions.
    """

    enabled: tuple[str, ...]
    selected: frozenset[str]
    ignored: frozenset[str]
    per_file_ignored: frozenset[str]
    plugin_enabled: bool
    suppressions: SuppressionPlan

    def is_enabled(self, code: str) -> bool:
        """Return whether ``code`` is selected for this document.

        Parameters
        ----------
        code:
            Candidate rule code.

        Returns
        -------
        bool
            ``True`` when the rule may run.
        """
        return code in self.enabled


def resolve_policy(
    request: RuleRunRequest,
    registry: cabc.Sequence[RuleMetadata],
    *,
    document_view: DocumentRegionView | None = None,
) -> RulePolicy:
    """Resolve which rules run for one document.

    Precedence is: builtin plugin selection, then ``lint.select``, then
    ``lint.ignore``, then a matching ``lint.per-file-ignores`` glob. Ignore
    rules win regardless of prefix length. Unmatched prefixes are valid
    no-ops.

    Parameters
    ----------
    request:
        The per-document run request carrying the document, its effective
        configuration, and the paths selection is evaluated against.
    registry:
        The builtin rule inventory, in deterministic order.
    document_view:
        The document projection the caller already built, when it has one, so
        ``ignore-next`` targets are not re-derived from the regions.

    Returns
    -------
    RulePolicy
        The resolved selection decision and suppression plan.
    """
    config = request.config
    codes = tuple(metadata.code for metadata in registry)
    plugin_enabled = _plugin_enabled(config)
    selected = (
        frozenset(expand_prefixes(tuple(config.lint.select), codes))
        if plugin_enabled
        else frozenset()
    )
    ignored = frozenset(expand_prefixes(tuple(config.lint.ignore), codes))
    per_file_ignored = _per_file_ignored(
        config,
        codes,
        request.config_relative_path or request.reported_path,
    )
    enabled = tuple(
        code
        for code in codes
        if code in selected and code not in ignored and code not in per_file_ignored
    )
    return RulePolicy(
        enabled=enabled,
        selected=selected,
        ignored=ignored,
        per_file_ignored=per_file_ignored,
        plugin_enabled=plugin_enabled,
        suppressions=resolve_suppressions(
            request.document,
            concrete_codes=codes,
            source_length=len(request.source_bytes),
            prose_units=(
                document_view.prose_units if document_view is not None else None
            ),
        ),
    )


def filter_diagnostics(
    policy: RulePolicy,
    produced: cabc.Iterable[Diagnostic],
) -> list[Diagnostic]:
    """Drop findings whose rule is not selected or that a directive suppresses.

    Parameters
    ----------
    policy:
        The resolved policy for this document.
    produced:
        Diagnostics a rule runner produced, in rule order.

    Returns
    -------
    list[Diagnostic]
        Diagnostics that survive selection and suppression, order preserved.
    """
    return [
        diagnostic
        for diagnostic in produced
        if policy.is_enabled(diagnostic.code)
        and not policy.suppressions.suppresses(diagnostic.code, diagnostic.span)
    ]


def _plugin_enabled(config: StilyagiConfig) -> bool:
    """Return whether the builtin pack is named by ``plugins``."""
    plugins = getattr(config, "plugins", ())
    return isinstance(plugins, cabc.Sequence) and "builtin" in plugins


def _per_file_ignored(
    config: StilyagiConfig,
    codes: cabc.Sequence[str],
    relative_path: str,
) -> frozenset[str]:
    """Return codes ignored by matching per-file globs."""
    patterns = getattr(config.lint, "per_file_ignores", {}) or {}
    if not isinstance(patterns, cabc.Mapping):
        return frozenset()
    ignored: set[str] = set()
    for pattern, prefixes in typ.cast(
        "cabc.Mapping[str, cabc.Sequence[str]]", patterns
    ).items():
        if _glob_matches(pattern, relative_path):
            ignored.update(expand_prefixes(tuple(prefixes), codes))
    return frozenset(ignored)


def _glob_matches(pattern: str, relative_path: str) -> bool:
    """Return whether a POSIX glob matches a config-relative path.

    ``*`` may match ``/`` in this bounded contract, so ``docs/*.md`` matches a
    nested guide as well as a direct child.

    Returns
    -------
    bool
        ``True`` when ``pattern`` matches the normalised relative path.

    Examples
    --------
    >>> _glob_matches("docs/*.md", "docs/guides/intro.md")
    True
    >>> _glob_matches("docs/*.md", "src/intro.md")
    False
    """
    return fnmatch.fnmatchcase(posixpath.normpath(relative_path), pattern)
