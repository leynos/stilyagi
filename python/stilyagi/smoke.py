"""Smoke checks for installed Stilyagi packages.

This module provides lightweight runtime checks that verify the Python package
can call through the embedded Rust extension. Use it from the command line as
``python -m stilyagi.smoke`` in continuous integration (CI), packaging jobs, or
local release checks. Use :func:`smoke_installed_package` directly when Python
code needs the same proof.

The public smoke contract is deliberately small: :data:`SMOKE_SOURCE` defines
the canonical Markdown payload, :data:`ExtractDocument` describes compatible
extractor callables, and :class:`SmokeCheckError` reports any bridge, type, or
document-validation failure. Successful checks return the validated
:class:`stilyagi.model.Document`; failed checks raise ``SmokeCheckError`` or
return process status ``1`` from :func:`main`.

Examples
--------
Run the installed-package smoke check as a module:

>>> import subprocess
>>> subprocess.run(["python", "-m", "stilyagi.smoke"], check=False).returncode in (0, 1)
True

Call the same check programmatically with a test extractor:

>>> from stilyagi import model
>>> def extract_document(source: str, syntax: model.Syntax) -> model.Document:
...     return model.Document(
...         syntax=syntax,
...         regions=(model.Region(kind="document", text=source),),
...     )
>>> smoke_installed_package(extract_fn=extract_document).syntax is model.Syntax.MARKDOWN
True
"""

import collections.abc as cabc
import sys

from stilyagi import engine, model

#: Canonical Markdown source used to prove the Rust-backed extraction path.
SMOKE_SOURCE = "# Stilyagi smoke"
#: Callable contract for smoke-compatible document extraction functions.
ExtractDocument = cabc.Callable[[str, model.Syntax], model.Document]


class SmokeCheckError(RuntimeError):
    """Report a failed installed-package smoke check.

    Raised when the extractor cannot cross the Python-to-Rust bridge, returns
    an object that is not a :class:`stilyagi.model.Document`, or returns a
    document that violates the smoke contract.

    Attributes
    ----------
    args : tuple[object, ...]
        Positional exception arguments inherited from :class:`RuntimeError`.

    Examples
    --------
    >>> try:
    ...     smoke_installed_package()
    ... except SmokeCheckError as err:
    ...     str(err) != ""
    ... else:
    ...     True
    True
    """


def smoke_installed_package(
    *,
    extract_fn: ExtractDocument = engine.extract_document,
) -> model.Document:
    """Exercise the public Python API backed by the embedded Rust extension.

    Calls *extract_fn* with the canonical smoke source and validates the
    returned document to confirm the Rust bridge is reachable and functioning.

    Parameters
    ----------
    extract_fn : ExtractDocument, optional
        Callable with the same signature as ``engine.extract_document``.
        Defaults to ``engine.extract_document``.  Pass an alternative to
        isolate unit tests from the live Rust bridge.

    Returns
    -------
    model.Document
        The validated document returned by the extraction engine.

    Raises
    ------
    SmokeCheckError
        If the extraction call raises, returns a non-Document type, or
        returns a document that does not satisfy the smoke contract.
    """
    try:
        document = extract_fn(SMOKE_SOURCE, model.Syntax.MARKDOWN)
    except Exception as exc:
        msg = f"smoke extraction raised an unexpected error: {exc}"
        raise SmokeCheckError(msg) from exc
    if not isinstance(document, model.Document):
        msg = f"smoke extraction returned unexpected type: {type(document)!r}"
        raise SmokeCheckError(msg)
    _validate_smoke_document(document)
    return document


def _assert_syntax_is_model_syntax(document: model.Document) -> None:
    """Raise SmokeCheckError if syntax is not a model.Syntax instance."""
    if isinstance(document.syntax, model.Syntax):
        return
    msg = f"malformed syntax from smoke extraction: {document.syntax!r}"
    raise SmokeCheckError(msg)


def _assert_syntax_is_markdown(document: model.Document) -> None:
    """Raise SmokeCheckError if syntax is not MARKDOWN."""
    if document.syntax is model.Syntax.MARKDOWN:
        return
    msg = f"unexpected syntax from smoke extraction: {document.syntax.value}"
    raise SmokeCheckError(msg)


def _assert_has_regions(document: model.Document) -> None:
    """Raise SmokeCheckError if the document has no regions."""
    if document.regions:
        return
    msg = "smoke extraction must return at least one region"
    raise SmokeCheckError(msg)


def _assert_has_expected_smoke_region(document: model.Document) -> None:
    """Raise SmokeCheckError if the expected smoke region is absent."""
    expected_region = model.Region(kind="document", text=SMOKE_SOURCE)
    if expected_region in document.regions:
        return
    msg = f"smoke extraction must include source-backed region: {expected_region!r}"
    raise SmokeCheckError(msg)


def _validate_smoke_document(document: model.Document) -> None:
    """Validate the document content that proves bridge execution."""
    _assert_syntax_is_model_syntax(document)
    _assert_syntax_is_markdown(document)
    _assert_has_regions(document)
    _assert_has_expected_smoke_region(document)


def main() -> int:
    """Run the installed-package smoke check as a command.

    Invokes :func:`smoke_installed_package` and reports the outcome to
    *stderr* on failure.  Intended for use as ``python -m stilyagi.smoke``
    or as a Makefile target recipe step.

    Returns
    -------
    int
        ``0`` on success, ``1`` if :exc:`SmokeCheckError` is raised.
    """
    try:
        smoke_installed_package()
    except SmokeCheckError as error:
        print(f"Stilyagi smoke check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
