"""Define pure, rule-authored fix values without importing the engine."""

import dataclasses as dc
import enum
import typing as typ

if typ.TYPE_CHECKING:
    from stilyagi.engine import ir_view


class Applicability(enum.StrEnum):
    """Describe how safely Stilyagi can apply a fix automatically."""

    SAFE = "safe"
    UNSAFE = "unsafe"
    MANUAL = "manual"


class FixLevel(enum.StrEnum):
    """Describe the applicability ceiling an execution may apply."""

    SAFE = "safe"
    UNSAFE = "unsafe"


@dc.dataclass(frozen=True, slots=True, order=True)
class TextEdit:
    """Replace one half-open UTF-8 byte range.

    Examples
    --------
    >>> TextEdit(2, 2, ",")
    TextEdit(byte_start=2, byte_end=2, replacement=',')
    """

    byte_start: int
    byte_end: int
    replacement: str

    @classmethod
    def insert_before(cls, span: ir_view.SourceSpan, text: str) -> TextEdit:
        """Insert text immediately before a source span."""
        return cls(span.byte_start, span.byte_start, text)

    @classmethod
    def insert_after(cls, span: ir_view.SourceSpan, text: str) -> TextEdit:
        """Insert text immediately after a source span."""
        return cls(span.byte_end, span.byte_end, text)

    @classmethod
    def replace(cls, span: ir_view.SourceSpan, text: str) -> TextEdit:
        """Replace the complete source span with text."""
        return cls(span.byte_start, span.byte_end, text)

    @classmethod
    def delete(cls, span: ir_view.SourceSpan) -> TextEdit:
        """Delete the complete source span."""
        return cls.replace(span, "")


@dc.dataclass(frozen=True, slots=True)
class Fix:
    """Bundle titled edits with their automatic-application classification.

    Examples
    --------
    >>> Fix("Insert comma", "safe", [TextEdit(2, 2, ",")]).applicability
    <Applicability.SAFE: 'safe'>
    """

    title: str
    applicability: Applicability
    edits: tuple[TextEdit, ...]

    def __post_init__(self) -> None:
        """Coerce loosely typed, rule-authored values into strict immutable data."""
        object.__setattr__(self, "applicability", Applicability(self.applicability))
        object.__setattr__(self, "edits", tuple(self.edits))
