"""Select diagnostics whose fixes are eligible for one planning level."""

import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics
    from stilyagi.config import LintConfig
    from stilyagi.fixes import FixLevel


def select_candidates(
    diagnostics_list: cabc.Iterable[diagnostics.Diagnostic],
    level: FixLevel,
    lint_config: LintConfig,
) -> tuple[diagnostics.Diagnostic, ...]:
    """Return eligible diagnostics in their original reporting order."""
    return tuple(
        diagnostic
        for diagnostic in diagnostics_list
        if is_candidate(diagnostic, level, lint_config)
    )


def is_candidate(
    diagnostic: diagnostics.Diagnostic,
    level: FixLevel,
    lint_config: LintConfig,
) -> bool:
    """Return whether a diagnostic can contribute edits at one fix level."""
    fix = diagnostic.fix
    return (
        fix is not None
        and fix.applicability != "manual"
        and (fix.applicability == "safe" or level == "unsafe")
        and is_fixable(diagnostic.code, lint_config)
    )


def is_fixable(code: str, lint_config: LintConfig) -> bool:
    """Return whether a code matches fixable prefixes but no unfixable prefix."""
    return _matches_any(code, lint_config.fixable) and not _matches_any(
        code, lint_config.unfixable
    )


def _matches_any(code: str, prefixes: cabc.Iterable[str]) -> bool:
    """Return whether a code matches any stable prefix or the `ALL` pseudo-prefix."""
    return any(prefix == "ALL" or code.startswith(prefix) for prefix in prefixes)
