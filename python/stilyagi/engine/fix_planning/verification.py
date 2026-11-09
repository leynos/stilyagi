"""Adapt a Markdown extractor into the planner's frontmatter verifier.

The fix planner refuses an edit it cannot prove harmless to a file's YAML
frontmatter, and the only proof is a second extraction of the repaired text.
That leaves the planner wanting a domain-shaped capability -- "give me the
document this text extracts to, or tell me you cannot" -- while the engine's
real answer arrives as bridge-specific exception types.

This module is the adapter between the two. `MarkdownVerifier` is the capability
the planner depends on, `FixVerificationError` is the one failure it reacts to,
and `markdown_verifier` translates the bridge's documented failures into that
failure. Keeping the translation here means `plan` never imports a bridge type,
and a caller that already owns an extractor can hand one over instead of paying
for another bridge call.
"""

import collections.abc as cabc
import typing as typ

from stilyagi import model
from stilyagi.engine.extraction import BridgeExtractionError

__all__ = [
    "FixVerificationError",
    "MarkdownVerifier",
    "markdown_verifier",
    "translate_verification_failure",
]

#: The failures a Markdown re-extraction may report for text it cannot read:
#: the bridge's documented recoverable errors plus the adapter's own input
#: errors. Anything else is a defect the planner must not absorb.
_REEXTRACTION_FAILURES: typ.Final = (
    BridgeExtractionError,
    RuntimeError,
    TypeError,
    ValueError,
)

type MarkdownVerifier = cabc.Callable[[str], model.Document]


class FixVerificationError(Exception):
    """One repaired document could not be re-extracted for verification.

    A verifier raises this to report a document it cannot read. The planner
    treats it as "the prefix cannot be vouched for" and refuses the plan, which
    is why the domain needs this one type rather than each caller's own.
    """


def _re_extract_markdown(source_text: str) -> model.Document:
    """Re-extract decoded Markdown through the engine's public boundary.

    Returns
    -------
    model.Document
        The document the given text extracts to.
    """
    from stilyagi.engine.api import extract_document

    return extract_document(source_text, model.Syntax.MARKDOWN)


def translate_verification_failure(failure: BaseException) -> str | None:
    """Name one re-extraction failure the frontmatter guard can account for.

    Returns
    -------
    str | None
        A short reason when the failure means "the repaired document cannot be
        verified", or ``None`` when it is a defect the planner must not absorb.

    Examples
    --------
    >>> translate_verification_failure(ValueError("bad document")) is not None
    True
    >>> translate_verification_failure(KeyError("bug")) is None
    True
    """
    match failure:
        case FixVerificationError():
            return str(failure) or "verification refused"
        case _ if isinstance(failure, _REEXTRACTION_FAILURES):
            return str(failure) or type(failure).__name__
        case _:
            return None


def markdown_verifier(
    extract: cabc.Callable[[str], model.Document] | None = None,
) -> MarkdownVerifier:
    r"""Wrap one Markdown extractor as a frontmatter verifier.

    Parameters
    ----------
    extract
        The extractor to call, or ``None`` for the engine's public boundary.

    Returns
    -------
    MarkdownVerifier
        A callable raising `FixVerificationError` for an unverifiable document.

    Examples
    --------
    >>> def refuse(_text: str) -> model.Document:
    ...     raise ValueError("no parser")
    >>> try:
    ...     markdown_verifier(refuse)("---\ntitle: x\n---\n")
    ... except FixVerificationError as error:
    ...     print(error)
    no parser
    """
    extractor = _re_extract_markdown if extract is None else extract

    def verify(source_text: str) -> model.Document:
        """Extract once, reporting only the failures the guard can act on."""
        try:
            return extractor(source_text)
        except Exception as failure:
            reason = translate_verification_failure(failure)
            if reason is None:
                raise
            raise FixVerificationError(reason) from failure

    return verify
