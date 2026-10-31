"""The typed rule boundary: target, metadata, context, and hook shape.

Rules receive only validated, frozen facts. They never read the filesystem,
resolve configuration, or render output. The check runner is the driving
adapter that builds the per-document request and projects the document into
eligible regions before invoking a hook.
"""

import collections.abc as cabc
import dataclasses as dc
import typing as typ

from stilyagi.model.source import SourceSpan

if typ.TYPE_CHECKING:
    from stilyagi import model
    from stilyagi.model.region import RegionView
    from stilyagi.rules.registry import RuleRunRequest
    from stilyagi.rules.tokens import TokenizedSegment


@dc.dataclass(frozen=True, slots=True)
class RegionTarget:
    """Declare which IR regions a rule claims.

    Parameters
    ----------
    kinds:
        Canonical region kinds the rule reads, for example ``heading``.
    syntax:
        Source syntax the target applies to. Builtin Markdown rules use the
        default; other syntaxes' regions are never handed to them.
    scope_has:
        Scope tokens that must all be present in a region's scope path. The
        IR serializes scope as a ``Vec<String>``, so this is interpreted in
        Python rather than by the extractor.

    Examples
    --------
    >>> RegionTarget(kinds=("heading",)).matches_kind("heading")
    True
    >>> RegionTarget(kinds=("heading",)).matches_kind("paragraph")
    False
    """

    kinds: tuple[str, ...]
    syntax: str = "markdown"
    scope_has: tuple[str, ...] = ()

    def matches_kind(self, kind: str) -> bool:
        """Return whether ``kind`` is one of the declared region kinds.

        Parameters
        ----------
        kind:
            Canonical IR region kind.

        Returns
        -------
        bool
            ``True`` when the target claims this kind.
        """
        return kind in self.kinds

    def matches_scope(self, scope: tuple[str, ...]) -> bool:
        """Return whether every required scope token is present.

        Parameters
        ----------
        scope:
            The region's serialized scope path.

        Returns
        -------
        bool
            ``True`` when all required tokens appear in ``scope``.

        Examples
        --------
        >>> RegionTarget(("heading",), scope_has=("h2",)).matches_scope(
        ...     ("markdown", "heading", "h2")
        ... )
        True
        """
        return all(token in scope for token in self.scope_has)

    def matches_region(self, region: RegionView) -> bool:
        """Return whether a region satisfies this target.

        Parameters
        ----------
        region:
            Candidate region from the canonical IR.

        Returns
        -------
        bool
            ``True`` when syntax, kind, and every scope token match.

        Examples
        --------
        >>> from stilyagi.model.region import RegionView
        >>> region = RegionView("r0", "heading", "markdown", ("h1",), {}, ())
        >>> RegionTarget(("heading",)).matches_region(region)
        True
        >>> RegionTarget(("paragraph",)).matches_region(region)
        False
        """
        return (
            region.syntax == self.syntax
            and self.matches_kind(region.kind)
            and self.matches_scope(region.scope)
        )


@dc.dataclass(frozen=True, slots=True)
class RuleMetadata:
    """Stable public metadata for one builtin rule.

    Parameters
    ----------
    code:
        Stable rule code, for example ``MD001``.
    name:
        Human-readable rule name used in documentation and messages.
    target:
        The IR regions this rule reads.
    default_severity:
        Severity applied when the rule reports.
    requires_nlp:
        Whether the rule needs NLP services. The starter pack never does.
    """

    code: str
    name: str
    target: RegionTarget
    default_severity: str
    requires_nlp: bool = False


@dc.dataclass(frozen=True, slots=True)
class RuleContext[T]:
    """The validated, read-only view a rule hook receives.

    Parameters
    ----------
    request:
        The per-document run request.
    rule_config:
        Frozen per-rule configuration validated for this rule.
    regions:
        The regions the rule's target claims, in document order.
    inline_code_spans:
        Canonical inline-code spans whose text must not be matched. Text rules
        exclude any segment contained in one of these spans.
    tokenized_segments:
        The target's eligible segments, tokenized once per document. Text
        rules read this instead of tokenizing a segment again, so a document
        with two selected text rules pays for tokenization only once.
    """

    request: RuleRunRequest
    rule_config: T
    regions: tuple[RegionView, ...] = ()
    inline_code_spans: tuple[SourceSpan, ...] = ()
    tokenized_segments: tuple[TokenizedSegment, ...] = ()

    @property
    def source_bytes(self) -> bytes:
        """The immutable original file bytes."""
        return self.request.source_bytes

    @property
    def reported_path(self) -> str:
        """The command-line-relative path for diagnostics."""
        return self.request.reported_path

    @property
    def document(self) -> model.Document:
        """The extracted document with its canonical IR envelope."""
        return self.request.document


type RuleHook = cabc.Callable[[RuleContext[typ.Any]], cabc.Iterable[typ.Any]]

__all__ = [
    "RegionTarget",
    "RuleContext",
    "RuleHook",
    "RuleMetadata",
    "SourceSpan",
]
