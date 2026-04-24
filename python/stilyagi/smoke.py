"""Smoke checks for installed Stilyagi packages."""

import sys

from stilyagi import engine, model

SMOKE_SOURCE = "# Stilyagi smoke"


class SmokeCheckError(RuntimeError):
    """Raised when the installed package does not cross the Rust bridge."""


def smoke_installed_package() -> model.Document:
    """Exercise the public Python API backed by the embedded Rust extension."""
    document = engine.extract_document(SMOKE_SOURCE, model.Syntax.MARKDOWN)
    _validate_smoke_document(document)
    return document


def _validate_smoke_document(document: model.Document) -> None:
    """Validate the narrow document shape that proves bridge execution."""
    if document.syntax is not model.Syntax.MARKDOWN:
        msg = f"unexpected syntax from smoke extraction: {document.syntax.value}"
        raise SmokeCheckError(msg)
    if not document.regions:
        msg = "smoke extraction must return at least one region"
        raise SmokeCheckError(msg)
    if document.regions[0] != model.Region(kind="document", text=SMOKE_SOURCE):
        msg = f"unexpected first smoke region: {document.regions[0]!r}"
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
