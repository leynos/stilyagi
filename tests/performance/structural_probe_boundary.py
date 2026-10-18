"""Boundary between the structural probe and the outside world.

The probe reads a monotonic clock, spawns a fresh interpreter for every cold
iteration, records the platform it ran on, and reads fixtures from disk. Each
is an outbound dependency, so each is expressed here as a callable port beside
the production default it stands in for. Tests substitute a port rather than
patch a module attribute, which leaves the real command-line path covered by
its own behaviour test.

Everything a measurement needs travels in two small bundles.
:class:`ProbeDependencies` holds the ports: the adapters through which the probe
reaches the clock, the process table, and the platform. :class:`ProbeCorpus`
holds the inputs: fixtures already read into memory, plus the root their report
paths are normalised against. Bundling keeps every measurement function inside
the repository's four-argument ceiling, which counts keyword-only parameters.
"""

import dataclasses as dc
import pathlib
import platform
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: naming the injectable cold-run runner whose production default is subprocess.run
import time
import typing as typ

from stilyagi import model

from tests.performance.structural_probe_reporting import EnvironmentPayload

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: Identifier recorded in every report.
PROBE_NAME = "structural-syntax"
#: The public adapter the probe measures.
ENTRYPOINT = "stilyagi.engine.extract_document"
#: Report schema version; bump only when the JSON contract changes.
SCHEMA_VERSION = 1
#: Measured iterations per mode when the command line names none.
DEFAULT_ITERATIONS = 5
MARKDOWN_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
)
PYTHON_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/python/valid/module-class-function-docstrings.py",
)
RUST_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/rust/valid/item-doc-comments.rs",
)

type ProbeMode = typ.Literal["cold", "warm"]
#: Reads a monotonic nanosecond counter.
type ClockFn = cabc.Callable[[], int]
#: Runs one child command and reports its captured output.
type SubprocessRunner = cabc.Callable[..., subprocess.CompletedProcess[str]]
#: Reports the platform metadata recorded beside every measurement.
type EnvironmentProvider = cabc.Callable[[], EnvironmentPayload]


def default_environment() -> EnvironmentPayload:
    """Return the platform and interpreter that produced a measurement.

    This is the production environment provider. A test substitutes its own to
    pin the report's environment section to deterministic values.

    Returns
    -------
    EnvironmentPayload
        The running platform description and Python version.

    Examples
    --------
    >>> sorted(default_environment())
    ['platform', 'python']
    """
    return EnvironmentPayload(
        platform=platform.platform(),
        python=platform.python_version(),
    )


@dc.dataclass(frozen=True, slots=True)
class ProbeDependencies:
    """The ports through which one probe run reaches the outside world.

    Parameters
    ----------
    clock:
        Reads the nanosecond counter that times an extraction.
    subprocess_runner:
        Runs the child interpreter that measures one cold iteration.
    environment_provider:
        Reports the platform metadata recorded in the report.

    Examples
    --------
    >>> ProbeDependencies().clock is time.perf_counter_ns
    True
    """

    clock: ClockFn = time.perf_counter_ns
    subprocess_runner: SubprocessRunner = subprocess.run
    environment_provider: EnvironmentProvider = default_environment


#: Production wiring, and the default for every injectable probe parameter.
DEFAULT_DEPENDENCIES = ProbeDependencies()


class StructuralFixture(typ.NamedTuple):
    """One representative source fixture for a supported extractor syntax.

    Parameters
    ----------
    path:
        Repository-relative fixture file path.
    syntax:
        The registered extractor syntax applied to the fixture.

    Examples
    --------
    >>> StructuralFixture(
    ...     path=MARKDOWN_FIXTURE,
    ...     syntax=model.Syntax.MARKDOWN,
    ... ).syntax.value
    'markdown'
    """

    path: pathlib.Path
    syntax: model.Syntax


def repository_root() -> pathlib.Path:
    """Return the repository root, derived from this module's location.

    Returns
    -------
    pathlib.Path
        The resolved repository root two parent directories above this file.

    Examples
    --------
    >>> repository_root().is_dir()
    True
    """
    return pathlib.Path(__file__).resolve().parents[2]


def discover_structural_fixtures(
    root: pathlib.Path,
) -> tuple[StructuralFixture, ...]:
    """Return representative fixtures for each registered extractor syntax.

    Parameters
    ----------
    root:
        The repository root containing the shared fixture corpus.

    Returns
    -------
    tuple[StructuralFixture, ...]
        One Markdown, Python, and Rust fixture in a fixed, deterministic
        order.

    Raises
    ------
    FileNotFoundError
        A representative fixture is missing from the corpus.

    Examples
    --------
    >>> fixtures = discover_structural_fixtures(repository_root())
    >>> tuple(fixture.syntax.value for fixture in fixtures)
    ('markdown', 'python_docstring', 'rust_doc_comment')
    """
    fixtures = (
        StructuralFixture(root / MARKDOWN_FIXTURE, model.Syntax.MARKDOWN),
        StructuralFixture(root / PYTHON_FIXTURE, model.Syntax.PYTHON_DOCSTRING),
        StructuralFixture(root / RUST_FIXTURE, model.Syntax.RUST_DOC_COMMENT),
    )
    for fixture in fixtures:
        if not fixture.path.is_file():
            msg = f"structural fixture is missing: {fixture.path.as_posix()}"
            raise FileNotFoundError(msg)
    return fixtures


@dc.dataclass(frozen=True, slots=True)
class ProbeRequest:
    """One fixture read into memory, ready to be measured.

    Reading happens once, when the request is built, so the measurement path
    performs no file access of its own. Supplying ``source`` directly lets a
    test measure text that was never written to disk.

    Parameters
    ----------
    path:
        Fixture path, kept so reports can normalise it repository-relative.
    source:
        Source text measured for this fixture.
    syntax:
        The extractor syntax applied to ``source``.
    byte_count:
        Size reported for ``source`` in the run payload.

    Examples
    --------
    >>> request = ProbeRequest(
    ...     path=MARKDOWN_FIXTURE,
    ...     source="# Title",
    ...     syntax=model.Syntax.MARKDOWN,
    ...     byte_count=7,
    ... )
    >>> request.byte_count
    7
    """

    path: pathlib.Path
    source: str
    syntax: model.Syntax
    byte_count: int

    @classmethod
    def from_fixture(cls, fixture: StructuralFixture) -> ProbeRequest:
        """Read one fixture into a request that repeats no file access.

        Parameters
        ----------
        fixture:
            The fixture whose text, syntax, and size the request carries.

        Returns
        -------
        ProbeRequest
            A request whose source is the fixture's decoded text.

        Examples
        --------
        >>> ProbeRequest.from_fixture(
        ...     StructuralFixture(
        ...         path=MARKDOWN_FIXTURE,
        ...         syntax=model.Syntax.MARKDOWN,
        ...     ),
        ... ).byte_count
        273
        """
        return cls(
            path=fixture.path,
            source=fixture.path.read_text(encoding="utf-8"),
            syntax=fixture.syntax,
            byte_count=fixture.path.stat().st_size,
        )

    def as_fixture(self) -> StructuralFixture:
        """Return the fixture descriptor this request was read from.

        Returns
        -------
        StructuralFixture
            The request's path and syntax, without its source text.

        Examples
        --------
        >>> ProbeRequest(
        ...     path=MARKDOWN_FIXTURE,
        ...     source="# Title",
        ...     syntax=model.Syntax.MARKDOWN,
        ...     byte_count=7,
        ... ).as_fixture().syntax is model.Syntax.MARKDOWN
        True
        """
        return StructuralFixture(self.path, self.syntax)


@dc.dataclass(frozen=True, slots=True)
class ProbeCorpus:
    """The fixtures to measure, already read, and the root they came from.

    Parameters
    ----------
    root:
        The repository root that fixture paths are normalised against.
    requests:
        Fixtures read into memory, in the order they should be measured.

    Examples
    --------
    >>> corpus = read_probe_corpus(repository_root())
    >>> tuple(request.syntax.value for request in corpus.requests)
    ('markdown', 'python_docstring', 'rust_doc_comment')
    """

    root: pathlib.Path
    requests: tuple[ProbeRequest, ...]

    @property
    def fixtures(self) -> tuple[StructuralFixture, ...]:
        """The fixture descriptors behind these requests.

        Returns
        -------
        tuple[StructuralFixture, ...]
            One descriptor per request, matching the request order.

        Examples
        --------
        >>> len(read_probe_corpus(repository_root()).fixtures)
        3
        """
        return tuple(request.as_fixture() for request in self.requests)


def read_probe_corpus(root: pathlib.Path) -> ProbeCorpus:
    """Discover and read every structural fixture beneath one root.

    Discovery rejects an incomplete corpus by raising ``FileNotFoundError``,
    which propagates from :func:`discover_structural_fixtures`.

    Parameters
    ----------
    root:
        The repository root containing the shared fixture corpus.

    Returns
    -------
    ProbeCorpus
        The discovered fixtures, read into memory, with their root.

    Examples
    --------
    >>> read_probe_corpus(repository_root()).requests[0].syntax.value
    'markdown'
    """
    fixtures = discover_structural_fixtures(root)
    return ProbeCorpus(
        root=root,
        requests=tuple(ProbeRequest.from_fixture(fixture) for fixture in fixtures),
    )
