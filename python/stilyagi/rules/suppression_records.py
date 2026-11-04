"""The byte-range record produced while resolving suppression directives.

The record is separate from :mod:`stilyagi.rules.suppression` so the resolved
plan can hold intervals without their field-level documentation crowding the
resolution logic. It is frozen and slotted: a plan is built once per document
and never mutated.
"""

import dataclasses as dc

__all__ = ["RuleInterval"]


@dc.dataclass(frozen=True, slots=True)
class RuleInterval:
    """A half-open byte range over which one code is suppressed.

    Attributes
    ----------
    code:
        The concrete builtin rule code the interval applies to.
    byte_start:
        Inclusive start offset of the suppressed range.
    byte_end:
        Exclusive end offset of the suppressed range.

    Examples
    --------
    >>> RuleInterval("STY001", 10, 20).covers(19)
    True
    >>> RuleInterval("STY001", 10, 20).covers(20)
    False
    """

    code: str
    byte_start: int
    byte_end: int

    def covers(self, byte_start: int) -> bool:
        """Return whether the interval covers a finding start.

        Parameters
        ----------
        byte_start:
            The finding's primary span start.

        Returns
        -------
        bool
            ``True`` when the start falls inside the interval.

        Examples
        --------
        >>> RuleInterval("STY001", 10, 20).covers(10)
        True
        >>> RuleInterval("STY001", 10, 20).covers(9)
        False
        """
        return self.byte_start <= byte_start < self.byte_end
