"""Rule registry and the private rule-running seam for the check pipeline.

The command pipeline calls :func:`run_rules` with a :class:`RuleRunRequest`
carrying the extracted document plus the source bytes, reported path and
effective configuration that rules need. The request also carries the
configuration-relative path used for per-file ignore globs, so policy code
performs no filesystem work.

Plugin authors must not depend on this seam while the in-process rule engine
is assembled.
"""

import dataclasses as dc
import typing as typ

from stilyagi.rules import policy as rule_policy

if typ.TYPE_CHECKING:
    from stilyagi import diagnostics, model
    from stilyagi.config import StilyagiConfig
    from stilyagi.model.source import SourceSpan
    from stilyagi.rules.base import RuleMetadata

__all__ = [
    "RuleRunRequest",
    "RuleRunner",
    "builtin_metadata",
    "run_rules",
]


@dc.dataclass(frozen=True, slots=True)
class RuleRunRequest:
    """Everything one rule run may read for a single document.

    Parameters
    ----------
    config:
        The effective global configuration for this file.
    config_path:
        Path of the effective configuration file, or ``None`` when the run had
        no configuration file.
    source_bytes:
        The original file bytes, so rules can produce byte-exact spans.
    reported_path:
        Command-line-relative POSIX path attributed to diagnostics.
    document:
        The extracted document with its canonical IR envelope.
    config_relative_path:
        POSIX path relative to the effective configuration parent, used for
        per-file ignore globs. Empty when the caller supplied no target path.
    """

    config: StilyagiConfig
    config_path: str | None
    source_bytes: bytes
    reported_path: str
    document: model.Document
    config_relative_path: str = ""

    def slice(self, span: SourceSpan) -> bytes:
        """Return the original bytes for ``span``.

        Parameters
        ----------
        span:
            Half-open byte range into :attr:`source_bytes`.

        Returns
        -------
        bytes
            The addressed slice, empty when the span falls outside the source.

        Examples
        --------
        >>> from stilyagi.model.source import SourceSpan
        >>> request = RuleRunRequest.__new__(RuleRunRequest)
        >>> object.__setattr__(request, "source_bytes", b"hello")
        >>> request.slice(SourceSpan(1, 4))
        b'ell'
        """
        return self.source_bytes[span.byte_start : span.byte_end]


class RuleRunner(typ.Protocol):
    """Private, unstable callable shape used by the check pipeline.

    Plugin authors must not depend on this seam; it exists only while the
    in-process rule engine is assembled in later roadmap work.
    """

    def __call__(
        self,
        request: RuleRunRequest,
        /,
    ) -> list[diagnostics.Diagnostic]:
        """Return diagnostics produced for one extracted document."""


def builtin_metadata() -> tuple[RuleMetadata, ...]:
    """Return the builtin rule inventory in deterministic order.

    Returns
    -------
    tuple[RuleMetadata, ...]
        Builtin rule metadata, ordered by code prefix then code.

    Examples
    --------
    >>> [metadata.code for metadata in builtin_metadata()]
    ['MD001', 'STY001', 'TERM001']
    """
    from stilyagi.rules.builtin import inventory

    return inventory()


def run_rules(request: RuleRunRequest) -> list[diagnostics.Diagnostic]:
    """Run the selected builtin rules for one document.

    Parameters
    ----------
    request:
        The per-document request carrying the document, source bytes, reported
        path and effective configuration.

    Returns
    -------
    list[diagnostics.Diagnostic]
        Diagnostics that survived rule selection and IR suppression.

    Examples
    --------
    >>> from stilyagi import config, model
    >>> request = RuleRunRequest(
    ...     config=config.StilyagiConfig(),
    ...     config_path=None,
    ...     source_bytes=b"",
    ...     reported_path="docs/example.md",
    ...     document=model.Document(syntax=model.Syntax.MARKDOWN),
    ... )
    >>> run_rules(request)
    []
    """
    from stilyagi.engine import rule_view
    from stilyagi.rules.builtin import run_selected

    registry = builtin_metadata()
    document_view = rule_view.project(
        request.document, source_bytes=request.source_bytes
    )
    request_policy = rule_policy.resolve_policy(
        request,
        registry,
        document_view=document_view,
    )
    produced = run_selected(
        request, registry, request_policy, document_view=document_view
    )
    return rule_policy.filter_diagnostics(request_policy, produced)
