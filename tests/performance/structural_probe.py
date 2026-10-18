"""Repository-local cold and warm structural performance probe."""

import argparse
import json
import pathlib
import typing as typ

from stilyagi import model

from tests.performance.structural_probe_boundary import (
    DEFAULT_DEPENDENCIES,
    DEFAULT_ITERATIONS,
    ENTRYPOINT,
    MARKDOWN_FIXTURE,
    PROBE_NAME,
    PYTHON_FIXTURE,
    RUST_FIXTURE,
    SCHEMA_VERSION,
    ClockFn,
    EnvironmentProvider,
    ProbeCorpus,
    ProbeDependencies,
    ProbeMode,
    ProbeRequest,
    StructuralFixture,
    SubprocessRunner,
    default_environment,
    discover_structural_fixtures,
    read_probe_corpus,
    repository_root,
)
from tests.performance.structural_probe_reporting import (
    CorpusPayload,
    EnvironmentPayload,
    ReportPayload,
    RunPayload,
    normalise_repository_path,
    summarise_durations,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

__all__ = [
    "DEFAULT_DEPENDENCIES",
    "DEFAULT_ITERATIONS",
    "ENTRYPOINT",
    "MARKDOWN_FIXTURE",
    "PROBE_NAME",
    "PYTHON_FIXTURE",
    "RUST_FIXTURE",
    "SCHEMA_VERSION",
    "ClockFn",
    "CorpusPayload",
    "EnvironmentPayload",
    "EnvironmentProvider",
    "ProbeCorpus",
    "ProbeDependencies",
    "ProbeMode",
    "ProbeRequest",
    "ProbeRun",
    "ReportPayload",
    "RunPayload",
    "StructuralFixture",
    "SubprocessRunner",
    "build_report",
    "default_environment",
    "discover_structural_fixtures",
    "main",
    "measure_probe",
    "normalise_repository_path",
    "read_probe_corpus",
    "redact_report",
    "repository_root",
    "summarise_durations",
    "write_report",
]


class ProbeRun(typ.NamedTuple):
    """Measured durations for one probe mode."""

    mode: ProbeMode
    syntax: model.Syntax
    byte_count: int
    durations_ns: tuple[int, ...]


def build_report(
    *,
    corpus: ProbeCorpus,
    runs: cabc.Sequence[ProbeRun],
    environment_provider: EnvironmentProvider = default_environment,
) -> ReportPayload:
    """Build the stable JSON-compatible structural probe report.

    Corpus totals come from the sizes recorded when the fixtures were read, so
    reporting touches no file of its own.

    Parameters
    ----------
    corpus:
        The fixtures to describe, already read, with the root their paths are
        normalized against. For an unambiguous per-syntax summary, provide no
        more than one request for each syntax.
    runs:
        Measured runs in report order. Each run must contain at least one
        duration so its summary can be calculated; an empty sequence of runs
        is allowed.
    environment_provider:
        Reports the platform metadata recorded in the report. Defaults to the
        running platform; a test substitutes a provider to pin those fields.

    Returns
    -------
    ReportPayload
        The report with schema version, probe identity, environment, corpus
        totals per syntax, and run payloads.

    Examples
    --------
    >>> corpus = read_probe_corpus(repository_root())
    >>> report = build_report(corpus=corpus, runs=[])
    >>> (report["probe"], report["corpus"]["file_count"], report["runs"])
    ('structural-syntax', 3, [])
    """
    requests = corpus.requests
    return ReportPayload(
        schema_version=SCHEMA_VERSION,
        probe=PROBE_NAME,
        entrypoint=ENTRYPOINT,
        environment=environment_provider(),
        corpus=CorpusPayload(
            fixture_paths=[
                normalise_repository_path(request.path, corpus.root)
                for request in requests
            ],
            file_count=len(requests),
            total_bytes=sum(request.byte_count for request in requests),
            per_syntax={
                request.syntax.value: {
                    "file_count": 1,
                    "total_bytes": request.byte_count,
                }
                for request in requests
            },
        ),
        runs=[_run_payload(run) for run in runs],
    )


def redact_report(report: ReportPayload) -> ReportPayload:
    """Redact volatile fields from a structural probe report for snapshots."""
    return ReportPayload(
        schema_version=report["schema_version"],
        probe=report["probe"],
        entrypoint=report["entrypoint"],
        environment=EnvironmentPayload(
            platform="<redacted>",
            python="<redacted>",
        ),
        corpus=report["corpus"],
        runs=[_redact_run(run) for run in _runs_from_report(report)],
    )


def measure_probe(
    *,
    mode: str,
    iterations: int,
    root: pathlib.Path,
    dependencies: ProbeDependencies = DEFAULT_DEPENDENCIES,
) -> ReportPayload:
    """Measure the requested structural probe mode and return a report.

    Parameters
    ----------
    mode:
        Either ``"cold"``, ``"warm"``, or ``"both"``.
    iterations:
        Measurements per mode. Must be at least 1.
    root:
        The repository root containing the shared fixture corpus.
    dependencies:
        The clock, subprocess runner, and environment provider to measure
        through. Defaults to the production adapters.

    Returns
    -------
    ReportPayload
        The structural probe report covering every fixture and requested
        mode.

    Examples
    --------
    >>> report = measure_probe(mode="warm", iterations=1, root=repository_root())
    >>> report["probe"]
    'structural-syntax'
    """
    from tests.performance.structural_probe_execution import (
        measure_probe as run_probe,
    )

    return run_probe(
        mode=mode,
        iterations=iterations,
        corpus=read_probe_corpus(root),
        dependencies=dependencies,
    )


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
        return _child_run(args)

    root = repository_root()
    report = measure_probe(
        mode=args.mode,
        iterations=args.iterations,
        root=root,
    )
    write_report(report, args.output)
    print(f"wrote {_display_output_path(args.output, root)}")
    return 0


def _child_run(args: argparse.Namespace) -> int:
    """Measure one extraction in this interpreter and print its duration.

    The parent sends the source text it wants measured, so the child never
    reopens a file whose contents might differ from the request. ``--source``
    still names the fixture, and a command run by hand without ``--text`` reads
    it, so the documented manual reproduction keeps working.

    Returns
    -------
    int
        Process exit status, always 0 because a failure raises instead.
    """
    from tests.performance.structural_probe_execution import measure_extraction

    source = args.text
    if source is None:
        source = args.source.read_text(encoding="utf-8")
    duration_ns = measure_extraction(source, model.Syntax(args.syntax))
    print(json.dumps({"duration_ns": duration_ns}, sort_keys=True))
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
        "--text",
        default=None,
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
