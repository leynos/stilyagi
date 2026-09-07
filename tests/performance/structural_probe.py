"""Repository-local cold and warm structural performance probe."""

import argparse
import json
import pathlib
import platform
import statistics
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- justified: using subprocess in test to run external benchmark tool; validated input/control
import sys
import time
import typing as typ

from stilyagi import engine, model

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PROBE_NAME = "structural-syntax"
ENTRYPOINT = "stilyagi.engine.extract_document"
SCHEMA_VERSION = 1
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


class SummaryNs(typ.TypedDict):
    """Nanosecond duration summary with deterministic integer values."""

    min: int
    median: int
    max: int


class RunPayload(typ.TypedDict):
    """JSON-compatible run payload (raw or redacted)."""

    mode: str
    iterations: int
    durations_ns: list[int] | str
    summary_ns: SummaryNs | dict[str, str]
    syntax: str
    byte_count: int
    median_ns_per_file: int | str
    throughput_mib_per_s: float | str


class EnvironmentPayload(typ.TypedDict):
    """Machine-identifying environment fields."""

    platform: str
    python: str


class CorpusPayload(typ.TypedDict):
    """Fixture corpus fields."""

    fixture_paths: list[str]
    file_count: int
    total_bytes: int
    per_syntax: dict[str, dict[str, int]]


class ReportPayload(typ.TypedDict):
    """Stable JSON-compatible structural probe report."""

    schema_version: int
    probe: str
    entrypoint: str
    environment: EnvironmentPayload | dict[str, str]
    corpus: CorpusPayload
    runs: list[RunPayload]


type Report = ReportPayload


class ProbeRun(typ.NamedTuple):
    """Measured durations for one probe mode."""

    mode: ProbeMode
    syntax: model.Syntax
    byte_count: int
    durations_ns: tuple[int, ...]


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
    >>> repository_root().name
    'stilyagi'
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


def normalise_repository_path(path: pathlib.Path, root: pathlib.Path) -> str:
    """Return a portable repository-relative path with POSIX separators."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        msg = f"{path} is not under repository root {root}"
        raise ValueError(msg) from error
    return relative.as_posix()


def summarise_durations(durations_ns: cabc.Sequence[int]) -> SummaryNs:
    """Summarise nanosecond durations with deterministic integer values."""
    if not durations_ns:
        msg = "cannot summarise an empty duration sequence"
        raise ValueError(msg)
    ordered = sorted(durations_ns)
    return SummaryNs(
        min=ordered[0],
        median=int(statistics.median(ordered)),
        max=ordered[-1],
    )


def build_report(
    *,
    repository_root: pathlib.Path,
    fixtures: cabc.Sequence[StructuralFixture],
    runs: cabc.Sequence[ProbeRun],
) -> ReportPayload:
    """Build the stable JSON-compatible structural probe report.

    Parameters
    ----------
    repository_root:
        The root used to normalise fixture paths to repository-relative POSIX
        form; every fixture must live beneath it.
    fixtures:
        The measured fixtures; their byte sizes populate the corpus totals.
    runs:
        One payload per measured run, in measurement order.

    Returns
    -------
    ReportPayload
        The report with schema version, probe identity, environment, corpus
        totals per syntax, and run payloads.
    """
    normalised_fixtures = [
        normalise_repository_path(fixture.path, repository_root) for fixture in fixtures
    ]
    per_syntax = {
        fixture.syntax.value: {
            "file_count": 1,
            "total_bytes": fixture.path.stat().st_size,
        }
        for fixture in fixtures
    }
    return ReportPayload(
        schema_version=SCHEMA_VERSION,
        probe=PROBE_NAME,
        entrypoint=ENTRYPOINT,
        environment=EnvironmentPayload(
            platform=platform.platform(),
            python=platform.python_version(),
        ),
        corpus=CorpusPayload(
            fixture_paths=normalised_fixtures,
            file_count=len(normalised_fixtures),
            total_bytes=sum(fixture.path.stat().st_size for fixture in fixtures),
            per_syntax=per_syntax,
        ),
        runs=[_run_payload(run) for run in runs],
    )


def redact_report(report: ReportPayload) -> ReportPayload:
    """Redact volatile fields from a structural probe report for snapshots."""
    return ReportPayload(
        schema_version=report["schema_version"],
        probe=report["probe"],
        entrypoint=report["entrypoint"],
        environment={
            "platform": "<redacted>",
            "python": "<redacted>",
        },
        corpus=report["corpus"],
        runs=[_redact_run(run) for run in _runs_from_report(report)],
    )


def measure_probe(
    *,
    mode: str,
    iterations: int,
    root: pathlib.Path,
) -> ReportPayload:
    """Measure the requested structural probe mode and return a report.

    Parameters
    ----------
    mode:
        Either ``"cold"``, ``"warm"``, or ``"both"``; any other value selects
        no modes and yields no runs.
    iterations:
        Measurements per mode. Must be at least 1.
    root:
        The repository root containing the shared fixture corpus.

    Returns
    -------
    ReportPayload
        The structural probe report covering every fixture and requested
        mode.

    Raises
    ------
    ValueError
        ``iterations`` is below 1.

    Examples
    --------
    >>> report = measure_probe(mode="warm", iterations=1, root=repository_root())
    >>> report["probe"]
    'structural-syntax'
    """
    if iterations < 1:
        msg = "iterations must be at least 1"
        raise ValueError(msg)

    fixtures = discover_structural_fixtures(root)
    runs = [
        _measure_run(
            run_mode,
            iterations,
            fixture.path.read_text(encoding="utf-8"),
            fixture,
        )
        for fixture in fixtures
        for run_mode in _modes(mode)
    ]
    return build_report(repository_root=root, fixtures=fixtures, runs=runs)


def write_report(report: ReportPayload, output_path: pathlib.Path) -> None:
    """Write a structural probe report as formatted JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"{json.dumps(report, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the structural performance probe command."""
    args = _argument_parser().parse_args(argv)
    if args.child_run:
        duration_ns = _measure_extraction(
            args.source.read_text(encoding="utf-8"),
            model.Syntax(args.syntax),
        )
        print(json.dumps({"duration_ns": duration_ns}, sort_keys=True))
        return 0

    root = repository_root()
    report = measure_probe(mode=args.mode, iterations=args.iterations, root=root)
    write_report(report, args.output)
    print(f"wrote {_display_output_path(args.output, root)}")
    return 0


def _run_payload(run: ProbeRun) -> RunPayload:
    """Return one JSON-compatible run payload."""
    median_ns_per_file = summarise_durations(run.durations_ns)["median"]
    seconds_per_file = median_ns_per_file / 1_000_000_000
    throughput_mib_per_s = (
        0.0 if seconds_per_file == 0 else run.byte_count / (1024**2) / seconds_per_file
    )
    return RunPayload(
        mode=run.mode,
        syntax=run.syntax.value,
        byte_count=run.byte_count,
        iterations=len(run.durations_ns),
        durations_ns=list(run.durations_ns),
        summary_ns=summarise_durations(run.durations_ns),
        median_ns_per_file=median_ns_per_file,
        throughput_mib_per_s=throughput_mib_per_s,
    )


def _display_output_path(output_path: pathlib.Path, root: pathlib.Path) -> str:
    """Return a non-absolute output path for command feedback."""
    try:
        return normalise_repository_path(output_path, root)
    except ValueError:
        return output_path.name


def _redact_run(run: RunPayload) -> RunPayload:
    """Return one run payload with timing fields redacted."""
    return RunPayload(
        mode=run["mode"],
        iterations=run["iterations"],
        durations_ns="<redacted>",
        summary_ns={"min": "<redacted>", "median": "<redacted>", "max": "<redacted>"},
        syntax=run["syntax"],
        byte_count=run["byte_count"],
        median_ns_per_file="<redacted>",
        throughput_mib_per_s="<redacted>",
    )


def _runs_from_report(report: ReportPayload) -> tuple[RunPayload, ...]:
    """Return run payloads from a report with defensive type checks."""
    runs = report["runs"]
    match runs:
        case list():
            if not all(isinstance(run, dict) for run in runs):
                msg = "report runs must contain dictionaries"
                raise TypeError(msg)
            return tuple(runs)
        case _:
            msg = "report runs must be a list"
            raise TypeError(msg)


def _modes(mode: str) -> tuple[ProbeMode, ...]:
    """Return the concrete run modes requested by the command line."""
    match mode:
        case "cold":
            return ("cold",)
        case "warm":
            return ("warm",)
        case "both":
            return ("cold", "warm")
        case _:
            msg = f"unknown probe mode: {mode}"
            raise ValueError(msg)


def _measure_run(
    mode: ProbeMode,
    iterations: int,
    source: str,
    fixture: StructuralFixture,
) -> ProbeRun:
    """Measure one concrete structural probe mode for one source syntax."""
    if mode == "cold":
        durations = tuple(_measure_cold_iteration(fixture) for _ in range(iterations))
    else:
        engine.extract_document(source, fixture.syntax)
        durations = tuple(
            _measure_extraction(source, fixture.syntax) for _ in range(iterations)
        )
    return ProbeRun(
        mode=mode,
        syntax=fixture.syntax,
        byte_count=fixture.path.stat().st_size,
        durations_ns=durations,
    )


def _measure_cold_iteration(fixture: StructuralFixture) -> int:
    """Measure one syntax extraction in a fresh Python interpreter."""
    root = repository_root()
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- justified: spawning own module under test with known sys.executable; no user input reaches argv
        [
            sys.executable,
            "-m",
            "tests.performance.structural_probe",
            "--child-run",
            "--source",
            str(fixture.path),
            "--syntax",
            fixture.syntax.value,
        ],
        check=True,
        cwd=root,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    duration_ns = payload["duration_ns"]
    if not isinstance(duration_ns, int):
        msg = "child probe did not return an integer duration"
        raise TypeError(msg)
    return duration_ns


def _measure_extraction(source: str, syntax: model.Syntax) -> int:
    """Measure one structural extraction in nanoseconds."""
    started_ns = time.perf_counter_ns()
    engine.extract_document(source, syntax)
    return time.perf_counter_ns() - started_ns


def _argument_parser() -> argparse.ArgumentParser:
    """Return the structural probe argument parser."""
    parser = argparse.ArgumentParser(
        description="Record cold and warm structural Stilyagi timings.",
    )
    parser.add_argument(
        "--mode",
        choices=("cold", "warm", "both"),
        default="both",
        help="probe mode to run",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="measured iterations per mode",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("build/performance/structural-baseline.json"),
        help="JSON report output path",
    )
    parser.add_argument(
        "--child-run",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--source",
        type=pathlib.Path,
        default=repository_root() / MARKDOWN_FIXTURE,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--syntax",
        choices=tuple(syntax.value for syntax in model.Syntax),
        default=model.Syntax.MARKDOWN.value,
        help=argparse.SUPPRESS,
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
