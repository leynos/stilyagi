"""Internal diagnostic model for Stilyagi renderers."""

import dataclasses as dc
import enum


class Severity(enum.StrEnum):
    """Severity labels carried by diagnostics."""

    ERROR = "error"
    WARNING = "warning"


_FAILING_SEVERITIES: frozenset[Severity] = frozenset({Severity.ERROR})


def is_failing_severity(severity: Severity) -> bool:
    """Return whether ``severity`` makes the check command fail."""
    return severity in _FAILING_SEVERITIES


@dc.dataclass(frozen=True, slots=True)
class Diagnostic:
    """Diagnostic entry shared by the renderers.

    Parameters
    ----------
    path:
        Command-line-relative POSIX path reported to the user.
    code:
        Stable diagnostic identifier.
    message:
        Human-readable explanation.
    severity:
        Diagnostic severity label. ``WARNING`` is informational for this
        milestone and does not affect the command exit code.
    line:
        1-based source line, when known.
    column:
        1-based source column, when known.
    fix:
        Placeholder fix payload for the future edit model.
    """

    path: str
    code: str
    message: str
    severity: Severity = Severity.ERROR
    line: int | None = None
    column: int | None = None
    fix: object | None = None
