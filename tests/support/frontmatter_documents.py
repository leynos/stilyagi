"""Build the documents and IR envelopes the frontmatter guards are given.

Recognition tests and guard tests disagree about exactly one thing: whether a
frontmatter region is recognized. They agree about everything else, so the
source, the expected prefix and the three builders that assemble an envelope
live here rather than being restated in each module with a different name.
"""

import typing as typ

from stilyagi import model

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: A Markdown source whose frontmatter closes before the body begins.
SOURCE = "---\ntitle: Café\n---\n\nHello world\n"

#: The protected prefix, ending after the closing fence's line ending.
#:
#: Kept as text and encoded where it is asserted: a byte-literal escape for the
#: accented letter splits the word, and the spelling gate then reads a
#: fragment of it.
PREFIX = "---\ntitle: Café\n---\n"


def document(ir: cabc.Mapping[str, object] | None) -> model.Document:
    """Build a Markdown document carrying one chosen IR envelope."""
    return model.Document(syntax=model.Syntax.MARKDOWN, ir=ir)


def region(**overrides: object) -> dict[str, object]:
    """Return one YAML frontmatter region with the requested fields replaced."""
    frontmatter_region: dict[str, object] = {
        "kind": "frontmatter",
        "attrs": {"format": "yaml"},
        "segments": [
            {
                "text": "---\ntitle: Café\n---",
                "source": {"byte_start": 0, "byte_end": 20},
            }
        ],
    }
    frontmatter_region.update(overrides)
    return frontmatter_region


def envelope(*regions: object) -> dict[str, object]:
    """Return an IR envelope carrying exactly the supplied regions."""
    return {"regions": list(regions)}
