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
from stilyagi.rules.description import (
    CAPABILITY_NLP,
    SEVERITY_NAMES,
    RuleDescription,
)
from stilyagi.rules.inline_code import InlineCodeIndex

if typ.TYPE_CHECKING:  # pragma: no cover - typing only
    from stilyagi import model
    from stilyagi.model.region import RegionOwner, RegionView
    from stilyagi.rules.tokens import TokenizedSegment


@dc.dataclass(frozen=True, slots=True)
class RegionTarget:
    """Declare which IR regions a rule claims.

    Parameters
    ----------
    kinds:
        Canonical region kinds the rule reads, for example ``heading``.
    syntaxes:
        Source syntaxes the target applies to. Builtin Markdown rules use the
        default; a region from any other syntax is never handed to them. A
        rule that spans languages names each syntax it reads.
    scope_has:
        Scope tokens that must all be present in a region's scope path. The
        IR serializes scope as a ``Vec<String>``, so this is interpreted in
        Python rather than by the extractor.
    owner_kinds:
        Owner kinds the target accepts. An empty tuple is unrestricted,
        including regions that record no owner at all. A nonempty tuple
        requires a present owner whose kind is one of these values.

    Examples
    --------
    >>> RegionTarget(kinds=("heading",)).matches_kind("heading")
    True
    >>> RegionTarget(kinds=("heading",)).matches_kind("paragraph")
    False
    >>> from stilyagi.model.region import RegionOwner
    >>> RegionTarget(
    ...     kinds=("python_docstring",), syntaxes=("python",), owner_kinds=("class",)
    ... ).matches_owner(RegionOwner("class"))
    True
    """

    kinds: tuple[str, ...]
    syntaxes: tuple[str, ...] = ("markdown",)
    scope_has: tuple[str, ...] = ()
    owner_kinds: tuple[str, ...] = ()

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

    def matches_syntax(self, syntax: str) -> bool:
        """Return whether ``syntax`` is one of the declared source syntaxes.

        Parameters
        ----------
        syntax:
            Source syntax that produced a region, for example ``python``.

        Returns
        -------
        bool
            ``True`` when the target claims this syntax.

        Examples
        --------
        >>> RegionTarget(("heading",)).matches_syntax("markdown")
        True
        >>> RegionTarget(("heading",)).matches_syntax("python")
        False
        """
        return syntax in self.syntaxes

    def matches_owner(self, owner: RegionOwner | None) -> bool:
        """Return whether a region's owner satisfies the kind requirement.

        Parameters
        ----------
        owner:
            The region's projected owner, or ``None`` when it has none.

        Returns
        -------
        bool
            ``True`` when no owner kind was required, or when ``owner`` is
            present and its kind is one the target declares.

        Examples
        --------
        >>> RegionTarget(("heading",)).matches_owner(None)
        True
        >>> RegionTarget(("heading",), owner_kinds=("class",)).matches_owner(None)
        False
        """
        if not self.owner_kinds:
            return True
        return owner is not None and owner.kind in self.owner_kinds

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
            ``True`` when syntax, kind, owner kind, and every scope token
            match.

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
            self.matches_syntax(region.syntax)
            and self.matches_kind(region.kind)
            and self.matches_owner(region.owner)
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
    description:
        The policy, typed options, examples, and limits the catalogue
        publishes.
    requires_nlp:
        Whether the rule needs NLP services. The starter pack never does. It
        must agree with the description's capability declaration.
    pack:
        The owning rule pack. Builtin rules all belong to ``builtin``.
    """

    code: str
    name: str
    target: RegionTarget
    default_severity: str
    description: RuleDescription
    requires_nlp: bool = False
    pack: str = "builtin"

    def __post_init__(self) -> None:
        """Reject contradictory identity, severity, or capability metadata."""
        for field_name, value in (
            ("code", self.code),
            ("name", self.name),
            ("pack", self.pack),
        ):
            if not value:
                message = f"{field_name} must be non-empty"
                raise ValueError(message)
        if self.default_severity not in SEVERITY_NAMES:
            message = f"unsupported default severity: {self.default_severity}"
            raise ValueError(message)
        if (CAPABILITY_NLP in self.description.requires) is not self.requires_nlp:
            message = "requires_nlp must match the NLP capability declaration"
            raise ValueError(message)


@dc.dataclass(frozen=True, slots=True)
class RuleContext[T]:
    """The validated, read-only view a rule hook receives.

    The context carries only per-document facts and the rule's own validated
    configuration. The application-level run request, which also holds global
    configuration and the paths used for selection, is deliberately absent: a
    rule cannot read policy it does not own.

    Parameters
    ----------
    rule_config:
        Frozen per-rule configuration validated for this rule.
    document:
        The extracted document with its canonical IR envelope.
    source_bytes:
        The immutable original file bytes.
    reported_path:
        Command-line-relative path attributed to diagnostics.
    line_starts:
        Validated IR line starts, computed once per document, or ``None`` when
        the IR omitted line metadata. Location mapping reuses this index.
    inline_code:
        Index over the canonical inline-code spans, built once per document.
        Text rules exclude any segment contained in one of those spans.
    regions:
        The regions the rule's target claims, in document order.
    tokenized_segments:
        The target's eligible segments, tokenized once per document. Text
        rules read this instead of tokenizing a segment again, so a document
        with two selected text rules pays for tokenization only once.
    """

    rule_config: T
    document: model.Document
    source_bytes: bytes
    reported_path: str
    line_starts: tuple[int, ...] | None = None
    inline_code: InlineCodeIndex = dc.field(default_factory=InlineCodeIndex)
    regions: tuple[RegionView, ...] = ()
    tokenized_segments: tuple[TokenizedSegment, ...] = ()


type RuleHook = cabc.Callable[[RuleContext[typ.Any]], cabc.Iterable[typ.Any]]

__all__ = [
    "RegionTarget",
    "RuleContext",
    "RuleHook",
    "RuleMetadata",
    "SourceSpan",
]
