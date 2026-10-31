"""Immutable, rule-facing views over one canonical IR region.

The extractor's IR is a plain mapping whose shape is owned by Rust. Rules read
the small, typed projection defined here so that no rule depends on mapping
keys, optional fields, or JSON quirks. The projection is inert: it never reads
a file and never resolves configuration.
"""

import dataclasses as dc
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from stilyagi.model.source import SourceSpan


@dc.dataclass(frozen=True, slots=True)
class Region:
    """Placeholder region model for the package skeleton.

    Parameters
    ----------
    kind:
        Future region kind name.
    text:
        Region text carried into the future rule engine.
    """

    kind: str
    text: str


@dc.dataclass(frozen=True, slots=True)
class RegionSegment:
    """One source-backed or synthetic segment inside a region.

    Parameters
    ----------
    span:
        Byte range in the original source, or ``None`` for synthetic text.
    text:
        Segment text exactly as the extractor reported it.
    node:
        Canonical node id that owns this segment, when the IR supplies one.
    synthetic_reason:
        Why the segment has no source backing, when it is synthetic.
    """

    span: SourceSpan | None
    text: str
    node: str | None = None
    synthetic_reason: str | None = None


@dc.dataclass(frozen=True, slots=True)
class RegionView:
    """One IR region with the structural facts the builtin rules consume.

    Parameters
    ----------
    region_id:
        Stable IR region identifier.
    kind:
        Canonical region kind, for example ``heading`` or ``table_cell``.
    syntax:
        Source syntax that produced the region, for example ``markdown``.
    scope:
        Ordered scope path emitted by the extractor.
    attrs:
        Region attributes; heading depth is stored under ``depth``.
    segments:
        Segments belonging to the region, in document order.
    span:
        Canonical region span, taken from the origin nodes so it includes
        structural markers such as a heading's ``#`` prefix. ``None`` when the
        IR supplied neither origins nor source-backed segments.
    """

    region_id: str
    kind: str
    syntax: str
    scope: tuple[str, ...]
    attrs: cabc.Mapping[str, object]
    segments: tuple[RegionSegment, ...]
    span: SourceSpan | None = None

    @property
    def depth(self) -> int | None:
        """The heading depth when the region attribute carries one.

        Returns
        -------
        int | None
            The ``attrs["depth"]`` value as an ``int``, or ``None`` when the
            attribute is absent or not an integer.

        Examples
        --------
        >>> view = RegionView("r0", "heading", "markdown", (), {"depth": 2}, ())
        >>> view.depth
        2
        >>> RegionView("r1", "paragraph", "markdown", (), {}, ()).depth is None
        True
        """
        value = self.attrs.get("depth")
        return value if isinstance(value, int) else None

    @property
    def is_empty(self) -> bool:
        """Whether every segment is blank.

        An empty region still has a diagnostic span; it simply cannot be the
        target of an ``ignore-next`` directive, which consumes the next unit
        that actually carries prose.

        Returns
        -------
        bool
            ``True`` when no segment contains non-whitespace text.

        Examples
        --------
        >>> RegionView("r0", "heading", "markdown", (), {}, ()).is_empty
        True
        """
        return not any(segment.text.strip() for segment in self.segments)
