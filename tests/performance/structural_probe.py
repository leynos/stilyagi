"""Repository-local cold and warm structural performance probe."""

import argparse
import json
import logging
import pathlib
import platform
import typing as typ

from stilyagi import model

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

logger = logging.getLogger(__name__)

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
            logger.error("structural fixture is missing: path=%s", fixture.path)
            msg = f"structural fixture is missing: {fixture.path.as_posix()}"
            raise FileNotFoundError(msg)
        logger.debug("fixture discovered: path=%s", fixture.path)
    return fixtures


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
        Existing fixture files beneath ``repository_root``. Their byte sizes
        populate the corpus totals. For an unambiguous per-syntax summary,
        provide no more than one fixture for each syntax.
    runs:
        Measured runs in report order. Each run must contain at least one
        duration so its summary can be calculated; an empty sequence of runs
        is allowed.

    Returns
    -------
    ReportPayload
        The report with schema version, probe identity, environment, corpus
        totals per syntax, and run payloads.

    Examples
    --------
    >>> root = repository_root()
    >>> fixtures = discover_structural_fixtures(root)
    >>> report = build_report(repository_root=root, fixtures=fixtures, runs=[])
    >>> (report["probe"], report["corpus"]["file_count"], report["runs"])
    ('structural-syntax', 3, [])
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
        Either ``"cold"``, ``"warm"``, or ``"both"``.
    iterations:
        Measurements per mode. Must be at least 1.
    root:
        The repository root containing the shared fixture corpus.

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
    from tests.performance.structural_probe_execution import measure_probe as run_probe

    return run_probe(mode=mode, iterations=iterations, root=root)


def write_report(report: ReportPayload, output_path: pathlib.Path) -> None:
    """Write a structural probe report as formatted JSON."""
    logger.debug("writing report: path=%s", output_path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            f"{json.dumps(report, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
    except OSError:
        logger.exception("report write failed: path=%s", output_path)
        raise


def main(argv: cabc.Sequence[str] | None = None) -> int:
    """Run the structural performance probe command."""
    args = _argument_parser().parse_args(argv)
    if args.child_run:
        from tests.performance.structural_probe_execution import measure_extraction

        duration_ns = measure_extraction(
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
