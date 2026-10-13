"""Format stable path and timing fields for structural probe reports."""

import statistics
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import pathlib


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
