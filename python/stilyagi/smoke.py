"""Smoke checks for installed Stilyagi packages."""

import sys
import typing as typ

from stilyagi import engine, model

SMOKE_SOURCE = "# Stilyagi smoke"
ExtractDocument = typ.Callable[[str, model.Syntax], model.Document]


class SmokeCheckError(RuntimeError):
    """Raised when the installed package does not cross the Rust bridge."""


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
    except Exception as error:
        msg = f"Stilyagi smoke check failed: {error}"
        raise SmokeCheckError(msg) from error
    if not isinstance(document, model.Document):
        error = TypeError(f"expected model.Document, got {type(document).__name__}")
        msg = f"Stilyagi smoke check failed: {error}"
        raise SmokeCheckError(msg) from error
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
