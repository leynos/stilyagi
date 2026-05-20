"""Private golden IR helpers for Python tests."""

import dataclasses as dc
import json
import pathlib
import typing as typ

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SHARED_MARKDOWN_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
)


class SourceSegment(typ.TypedDict):
    """Source-backed segment snapshot shape."""

    kind: typ.Literal["source"]
    start: int
    end: int
    text: str


class SyntheticSegment(typ.TypedDict):
    """Synthetic segment snapshot shape."""

    kind: typ.Literal["synthetic"]
    text: str


Segment = SourceSegment | SyntheticSegment


@dc.dataclass(frozen=True, slots=True)
class GoldenIrDocument:
    """Minimal private golden IR document used by Python tests."""

    fixture: str
    syntax: str
    line_index: tuple[int, ...]
    regions: tuple[dict[str, object], ...]
    diagnostics: tuple[str, ...] = ()

    def as_snapshot_payload(self) -> dict[str, object]:
        """Return a deterministic JSON-compatible payload."""
        return {
            "fixture": self.fixture,
            "syntax": self.syntax,
            "line_index": list(self.line_index),
            "regions": list(self.regions),
            "diagnostics": list(self.diagnostics),
        }

    def canonical_json(self) -> str:
        """Return canonical JSON for text snapshot comparisons."""
        return (
            json.dumps(
                self.as_snapshot_payload(),
                ensure_ascii=False,
                indent=2,
                sort_keys=False,
            )
            + "\n"
        )


def read_fixture(relative_path: pathlib.Path) -> str:
    """Read a repository-relative fixture as UTF-8 text."""
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def golden_markdown_ir_fixture(
    relative_path: pathlib.Path = SHARED_MARKDOWN_FIXTURE,
) -> GoldenIrDocument:
    """Build the private golden IR snapshot shape for a Markdown fixture."""
    source = read_fixture(relative_path)
    regions: tuple[dict[str, object], ...]
    if source.strip():
        regions = (
            {
                "kind": "document",
                "text": source,
                "segments": [
                    {
                        "kind": "source",
                        "start": 0,
                        "end": len(source.encode()),
                        "text": source,
                    },
                ],
            },
        )
    else:
        regions = ()
    return GoldenIrDocument(
        fixture=relative_path.as_posix(),
        syntax="markdown",
        line_index=tuple(line_index_for(source)),
        regions=regions,
    )


def line_index_for(source: str) -> tuple[int, ...]:
    """Return byte offsets for line starts plus the end-of-document offset."""
    offsets = [0]
    current_offset = 0
    for character in source:
        current_offset += len(character.encode())
        if character == "\n":
            offsets.append(current_offset)
    if offsets[-1] != current_offset:
        offsets.append(current_offset)
    return tuple(offsets)
