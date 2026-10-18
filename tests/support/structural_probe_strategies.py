"""Generated readings for the structural probe's property tests.

The example tests pin the report against readings chosen by hand. These
strategies supply the readings those examples cannot cover: arbitrary
duration sequences, repository-relative paths, and probe runs, all small
enough that 64 examples stay cheap.

Every generated fixture is a tiny file inside one per-example temporary
directory. Real repository fixtures would make the module slow and tie the
invariants to the corpus; the helpers under test read only a fixture's
resolved location and byte size, never its content.
"""

import contextlib
import pathlib
import tempfile
import typing as typ

import hypothesis.strategies as st
from stilyagi import model

from tests.performance import structural_probe

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: Largest generated fixture. A few hundred kilobytes across a whole run
#: keeps per-example temporary directories cheap to create and remove.
FILE_BYTES = st.integers(min_value=0, max_value=2048)

#: Plain ASCII segments keep the path invariant about separators rather than
#: about which Unicode code points the host filesystem happens to accept.
PATH_COMPONENT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=8,
)

#: A relative path with ordinary POSIX separators.
RELATIVE_PATH = st.lists(PATH_COMPONENT, min_size=1, max_size=4).map("/".join)

#: One of the registered extractor syntaxes.
SYNTAXES = st.sampled_from(tuple(model.Syntax))

#: Runs the probe could measure: cold or warm, at any registered syntax.
RUNS = st.lists(
    st.builds(
        structural_probe.ProbeRun,
        mode=st.sampled_from(("cold", "warm")),
        syntax=SYNTAXES,
        byte_count=FILE_BYTES,
        # Non-negative: a clock reading is never negative, and a zero-length
        # extraction is a real reading rather than an error. Non-empty:
        # ``build_report`` documents that each run has at least one duration.
        durations_ns=st.lists(
            st.integers(min_value=0, max_value=10**12),
            min_size=1,
            max_size=16,
        ).map(tuple),
    ),
    max_size=4,
)


@st.composite
def fixture_corpora(draw: st.DrawFn) -> list[tuple[pathlib.Path, int]]:
    """Draw a corpus of distinct files that cannot collide on disk.

    Every fixture gets its own top-level directory, so no generated path is
    ever a directory prefix of another. Drawing arbitrary relative paths
    instead lets Hypothesis find pairs such as ``0`` and ``0/0``, which
    cannot both be files.

    Returns
    -------
    list
        One ``(relative_path, byte_count)`` pair per fixture.
    """
    count = draw(st.integers(min_value=0, max_value=4))
    return [
        (
            pathlib.Path(f"fixture-{index}") / draw(RELATIVE_PATH),
            draw(FILE_BYTES),
        )
        for index in range(count)
    ]


def create_corpus(
    root: pathlib.Path,
    fixture_specs: cabc.Iterable[tuple[pathlib.Path, int]],
) -> tuple[structural_probe.StructuralFixture, ...]:
    """Write one file per spec beneath ``root`` and describe each as a fixture.

    Parameters
    ----------
    root:
        Directory the generated corpus is written under.
    fixture_specs:
        One ``(relative_path, byte_count)`` pair per fixture to create.

    Returns
    -------
    tuple[StructuralFixture, ...]
        One Markdown fixture per written file, in the order supplied.
    """
    fixtures = []
    for relative_path, byte_count in fixture_specs:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * byte_count)
        fixtures.append(
            structural_probe.StructuralFixture(path, model.Syntax.MARKDOWN),
        )
    return tuple(fixtures)


@contextlib.contextmanager
def built_report(
    fixture_specs: cabc.Iterable[tuple[pathlib.Path, int]],
    runs: cabc.Sequence[structural_probe.ProbeRun],
) -> cabc.Iterator[structural_probe.ReportPayload]:
    """Build a report over a temporary corpus and remove it afterwards.

    Parameters
    ----------
    fixture_specs:
        One ``(relative_path, byte_count)`` pair per fixture to create.
    runs:
        Measured runs to place in the report.

    Yields
    ------
    ReportPayload
        A report describing the temporary corpus.
    """
    with tempfile.TemporaryDirectory(prefix="structural-probe-") as root_dir:
        root = pathlib.Path(root_dir)
        yield structural_probe.build_report(
            repository_root=root,
            fixtures=create_corpus(root, fixture_specs),
            runs=tuple(runs),
        )
