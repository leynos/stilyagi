"""Helpers for materialising the malformed Markdown corpus in tests.

Every malformed Markdown fixture is stored with a ``.md.fixture`` suffix so
repository-wide Markdown formatting and lint sweeps skip it. Because
``stilyagi check`` only discovers ``.md`` and ``.markdown`` files, tests that
exercise discovery must strip the trailing ``.fixture`` suffix when copying
fixtures into a temporary tree; otherwise the fixtures are silently invisible to
discovery and the test passes vacuously. These helpers centralise that
suffix-stripping copy so every discovery-facing test exercises the whole corpus.
"""

import pathlib
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

MALFORMED_MARKDOWN_CORPUS = pathlib.Path("tests/fixtures/corpus/markdown/malformed")
_FIXTURE_SUFFIX = ".fixture"


def _discoverable_name(fixture_path: pathlib.Path) -> str:
    """Return the discoverable filename for one corpus fixture."""
    name = fixture_path.name
    if name.endswith(_FIXTURE_SUFFIX):
        return name[: -len(_FIXTURE_SUFFIX)]
    return name


def iter_malformed_fixtures(
    corpus_root: pathlib.Path = MALFORMED_MARKDOWN_CORPUS,
) -> cabc.Iterator[pathlib.Path]:
    """Yield each malformed corpus fixture file in deterministic order."""
    for fixture_path in sorted(corpus_root.iterdir()):
        if fixture_path.is_file():
            yield fixture_path


def materialize_malformed_corpus(
    destination: pathlib.Path,
    *,
    corpus_root: pathlib.Path = MALFORMED_MARKDOWN_CORPUS,
) -> tuple[str, ...]:
    """Copy every malformed fixture into ``destination`` as a discoverable file.

    Parameters
    ----------
    destination:
        Directory that receives the discoverable copies. Created if absent.
    corpus_root:
        Root of the malformed corpus. Defaults to the shared corpus path.

    Returns
    -------
    tuple[str, ...]
        The discoverable filenames written, sorted, so callers can assert that
        the whole malformed corpus reaches discovery.
    """
    destination.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for fixture_path in iter_malformed_fixtures(corpus_root):
        discoverable_name = _discoverable_name(fixture_path)
        (destination / discoverable_name).write_text(
            fixture_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        names.append(discoverable_name)
    return tuple(sorted(names))
