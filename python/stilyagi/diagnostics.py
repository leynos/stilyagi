"""Internal diagnostic model for Stilyagi renderers."""

import dataclasses as dc
import enum
import typing as typ

if typ.TYPE_CHECKING:
    from stilyagi.fixes import Fix


class Severity(enum.StrEnum):
    """Severity labels carried by diagnostics."""

    ERROR = "error"
    WARNING = "warning"


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
        Diagnostic severity label.
    line:
        1-based source line, when known.
    column:
        1-based source column, when known.
    fix:
        Optional rule-authored repair for this diagnostic.
    """

    path: str
    code: str
    message: str
    severity: Severity = Severity.ERROR
    line: int | None = None
    column: int | None = None
    fix: Fix | None = None


@dc.dataclass(frozen=True, slots=True)
class FixError:
    """One engine-level reason a file's proposed fixes were refused.

    Parameters
    ----------
    path:
        Command-line-relative POSIX path of the untouched source file.
    identifier:
        Stable engine identifier for the refused edit class.
    rule_codes:
        Rule codes whose proposed edits caused the refusal.
    message:
        Human-readable description of the refusal and non-mutation result.
    """

    path: str
    identifier: str
    rule_codes: tuple[str, ...]
    message: str
