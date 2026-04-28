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
    """Exercise the public Python API backed by the embedded Rust extension."""
    document = extract_fn(SMOKE_SOURCE, model.Syntax.MARKDOWN)
    _validate_smoke_document(document)
    return document


def _validate_smoke_document(document: model.Document) -> None:
    """Validate the document content that proves bridge execution."""
    if not isinstance(document.syntax, model.Syntax):
        msg = f"malformed syntax from smoke extraction: {document.syntax!r}"
        raise SmokeCheckError(msg)
    if document.syntax is not model.Syntax.MARKDOWN:
        msg = f"unexpected syntax from smoke extraction: {document.syntax.value}"
        raise SmokeCheckError(msg)
    if not document.regions:
        msg = "smoke extraction must return at least one region"
        raise SmokeCheckError(msg)
    expected_region = model.Region(kind="document", text=SMOKE_SOURCE)
    if expected_region not in document.regions:
        msg = f"smoke extraction must include source-backed region: {expected_region!r}"
        raise SmokeCheckError(msg)


def main() -> int:
    """Run the installed-package smoke check as a command."""
    try:
        smoke_installed_package()
    except SmokeCheckError as error:
        print(f"Stilyagi smoke check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
