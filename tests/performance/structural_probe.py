"""Repository-local cold and warm structural performance probe."""

import argparse
import json
import pathlib
import platform
import statistics
import subprocess  # noqa: S404 -- justified: using subprocess in test to run external benchmark tool; validated input/control
import sys
import time
import typing as typ

from stilyagi import engine, model

if typ.TYPE_CHECKING:
    import collections.abc as cabc

PROBE_NAME = "structural-markdown"
ENTRYPOINT = "stilyagi.engine.extract_document"
SCHEMA_VERSION = 1
DEFAULT_ITERATIONS = 5
MARKDOWN_FIXTURE = pathlib.Path(
    "tests/fixtures/corpus/markdown/valid/heading-table-link-suppression.md",
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


class EnvironmentPayload(typ.TypedDict):
    """Machine-identifying environment fields."""

    platform: str
    python: str


class CorpusPayload(typ.TypedDict):
    """Fixture corpus fields."""

    fixture_paths: list[str]
    file_count: int


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
    durations_ns: tuple[int, ...]


def repository_root() -> pathlib.Path:
    """Return the repository root from this maintainer-facing module."""
    return pathlib.Path(__file__).resolve().parents[2]


def discover_structural_fixtures(root: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """Return the stable Markdown fixture set for structural baseline probes."""
    fixture = root / MARKDOWN_FIXTURE
    if not fixture.is_file():
        msg = f"structural fixture is missing: {MARKDOWN_FIXTURE.as_posix()}"
        raise FileNotFoundError(msg)
    return (fixture,)


def normalize_repository_path(path: pathlib.Path, root: pathlib.Path) -> str:
    """Return a portable repository-relative path with POSIX separators."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        msg = f"{path} is not under repository root {root}"
        raise ValueError(msg) from error
    return relative.as_posix()


def summarize_durations(durations_ns: cabc.Sequence[int]) -> SummaryNs:
    """Summarize nanosecond durations with deterministic integer values."""
    if not durations_ns:
        msg = "cannot summarize an empty duration sequence"
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
    fixture_paths: cabc.Sequence[pathlib.Path],
    runs: cabc.Sequence[ProbeRun],
) -> ReportPayload:
    """Build the stable JSON-compatible structural probe report."""
    normalized_fixtures = [
        normalize_repository_path(path, repository_root) for path in fixture_paths
    ]
    return ReportPayload(
        schema_version=SCHEMA_VERSION,
        probe=PROBE_NAME,
        entrypoint=ENTRYPOINT,
        environment=EnvironmentPayload(
            platform=platform.platform(),
            python=platform.python_version(),
        ),
        corpus=CorpusPayload(
            fixture_paths=normalized_fixtures,
            file_count=len(normalized_fixtures),
        ),
        runs=[_run_payload(run) for run in runs],
    )


def redact_report(report: ReportPayload) -> ReportPayload:
    """Redact volatile fields from a structural probe report for snapshots."""
    redacted = dict(report)
    redacted["environment"] = {
        "platform": "<redacted>",
        "python": "<redacted>",
    }
    redacted["runs"] = [_redact_run(run) for run in _runs_from_report(report)]
    return redacted  # type: ignore[return-value]


def measure_probe(
    *,
    mode: str,
    iterations: int,
    root: pathlib.Path,
) -> ReportPayload:
    """Measure the requested structural probe mode and return a report."""
    if iterations < 1:
        msg = "iterations must be at least 1"
        raise ValueError(msg)

    fixtures = discover_structural_fixtures(root)
    source = fixtures[0].read_text(encoding="utf-8")
    runs = [_measure_run(run_mode, iterations, source) for run_mode in _modes(mode)]
    return build_report(repository_root=root, fixture_paths=fixtures, runs=runs)


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
        duration_ns = _measure_extraction(args.source.read_text(encoding="utf-8"))
        print(json.dumps({"duration_ns": duration_ns}, sort_keys=True))
        return 0

    root = repository_root()
    report = measure_probe(mode=args.mode, iterations=args.iterations, root=root)
    write_report(report, args.output)
    print(f"wrote {_display_output_path(args.output, root)}")
    return 0


def _run_payload(run: ProbeRun) -> RunPayload:
    """Return one JSON-compatible run payload."""
    return RunPayload(
        mode=run.mode,
        iterations=len(run.durations_ns),
        durations_ns=list(run.durations_ns),
        summary_ns=summarize_durations(run.durations_ns),
    )


def _display_output_path(output_path: pathlib.Path, root: pathlib.Path) -> str:
    """Return a non-absolute output path for command feedback."""
    try:
        return normalize_repository_path(output_path, root)
    except ValueError:
        return output_path.name


def _redact_run(run: RunPayload) -> RunPayload:
    """Return one run payload with timing fields redacted."""
    redacted: dict[str, object] = dict(run)
    redacted["durations_ns"] = "<redacted>"
    redacted["summary_ns"] = {
        "min": "<redacted>",
        "median": "<redacted>",
        "max": "<redacted>",
    }
    return redacted  # type: ignore[return-value]


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


def _measure_run(mode: ProbeMode, iterations: int, source: str) -> ProbeRun:
    """Measure one concrete structural probe mode."""
    if mode == "cold":
        durations = tuple(_measure_cold_iteration() for _ in range(iterations))
    else:
        engine.extract_document(source, model.Syntax.MARKDOWN)
        durations = tuple(_measure_extraction(source) for _ in range(iterations))
    return ProbeRun(mode=mode, durations_ns=durations)


def _measure_cold_iteration() -> int:
    """Measure one extraction in a fresh Python interpreter."""
    root = repository_root()
    source_path = root / MARKDOWN_FIXTURE
    completed = subprocess.run(  # noqa: S603 -- justified: spawning own module under test with known sys.executable; no user input reaches argv
        [
            sys.executable,
            "-m",
            "tests.performance.structural_probe",
            "--child-run",
            "--source",
            str(source_path),
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


def _measure_extraction(source: str) -> int:
    """Measure one structural Markdown extraction in nanoseconds."""
    started_ns = time.perf_counter_ns()
    engine.extract_document(source, model.Syntax.MARKDOWN)
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
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
