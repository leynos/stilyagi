"""Partition diagnostics by why their fixes can or cannot contribute edits."""

import dataclasses as dc
import enum
import typing as typ

from stilyagi.fixes import Applicability, FixLevel

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi import diagnostics
    from stilyagi.config import LintConfig


class _Reason(enum.Enum):
    """Why one diagnostic will or will not contribute an edit to a plan."""

    ELIGIBLE = enum.auto()
    UNFIXABLE_CODE = enum.auto()
    MANUAL = enum.auto()
    WITHHELD_UNSAFE = enum.auto()


@dc.dataclass(frozen=True, slots=True)
class CandidatePartition:
    """One file's diagnostics, split by why each cannot contribute an edit.

    A single classification pass produces every count the fix summary logs, so
    the counters cannot drift from the decision they describe: ``eligible`` is
    the sequence actually planned over, and the other three are exactly the
    diagnostics left out of it, each for one named reason.

    ``unfixable`` and ``withheld_unsafe`` are kept apart because they call for
    opposite advice -- one says the configuration refuses to fix this code, the
    other says ``--unsafe-fixes`` would allow it (D-15).
    """

    eligible: tuple[diagnostics.Diagnostic, ...]
    unfixable: tuple[diagnostics.Diagnostic, ...]
    manual: tuple[diagnostics.Diagnostic, ...]
    withheld_unsafe: tuple[diagnostics.Diagnostic, ...]


def partition_candidates(
    diagnostics_list: cabc.Iterable[diagnostics.Diagnostic],
    level: FixLevel,
    lint_config: LintConfig,
) -> CandidatePartition:
    """Split diagnostics into the eligible fixes and the three reasons against.

    Parameters
    ----------
    diagnostics_list:
        The diagnostics reported for one file.
    level:
        The applicability ceiling this run may apply. At ``FixLevel.SAFE`` an
        ``unsafe`` fix is withheld rather than refused, which the caller
        reports as a discoverability hint rather than as an error.
    lint_config:
        Resolved lint configuration carrying the ``fixable`` and ``unfixable``
        prefix lists.

    Returns
    -------
    CandidatePartition
        The eligible diagnostics, in their original reporting order, and the
        three excluded groups in the same order.

    Examples
    --------
    >>> from stilyagi.config import LintConfig
    >>> partition_candidates([], FixLevel.SAFE, LintConfig()).eligible
    ()
    """
    eligible: list[diagnostics.Diagnostic] = []
    unfixable: list[diagnostics.Diagnostic] = []
    manual: list[diagnostics.Diagnostic] = []
    withheld_unsafe: list[diagnostics.Diagnostic] = []
    groups: dict[_Reason, list[diagnostics.Diagnostic]] = {
        _Reason.ELIGIBLE: eligible,
        _Reason.UNFIXABLE_CODE: unfixable,
        _Reason.MANUAL: manual,
        _Reason.WITHHELD_UNSAFE: withheld_unsafe,
    }
    for diagnostic in diagnostics_list:
        groups[_classify(diagnostic, level, lint_config)].append(diagnostic)
    return CandidatePartition(
        eligible=tuple(eligible),
        unfixable=tuple(unfixable),
        manual=tuple(manual),
        withheld_unsafe=tuple(withheld_unsafe),
    )


def select_candidates(
    diagnostics_list: cabc.Iterable[diagnostics.Diagnostic],
    level: FixLevel,
    lint_config: LintConfig,
) -> tuple[diagnostics.Diagnostic, ...]:
    """Return only the diagnostics eligible to contribute edits."""
    return partition_candidates(diagnostics_list, level, lint_config).eligible


def is_fixable(code: str, lint_config: LintConfig) -> bool:
    """Return whether a code matches fixable prefixes but no unfixable prefix."""
    return _matches_any(code, lint_config.fixable) and not _matches_any(
        code, lint_config.unfixable
    )


def _classify(
    diagnostic: diagnostics.Diagnostic,
    level: FixLevel,
    lint_config: LintConfig,
) -> _Reason:
    """Return why one diagnostic either contributes an edit or does not."""
    fix = diagnostic.fix
    if fix is None or fix.applicability == Applicability.MANUAL:
        # A diagnostic with no fix and one the design forbids applying are the
        # same outcome for an execution: neither can ever change a byte, at any
        # level, under any configuration.
        return _Reason.MANUAL
    if not is_fixable(diagnostic.code, lint_config):
        return _Reason.UNFIXABLE_CODE
    if fix.applicability == Applicability.SAFE or level == FixLevel.UNSAFE:
        return _Reason.ELIGIBLE
    return _Reason.WITHHELD_UNSAFE


def _matches_any(code: str, prefixes: cabc.Iterable[str]) -> bool:
    """Return whether a code matches any stable prefix or the `ALL` pseudo-prefix."""
    return any(prefix == "ALL" or code.startswith(prefix) for prefix in prefixes)
