"""Property tests for the structural performance probe's pure helpers.

The example tests in ``test_structural_performance_probe.py`` pin the report
against readings chosen by hand. These properties hold over generated
readings instead, so a summary, path, or report that is right about the
fixtures someone typed and wrong about another sequence fails here rather
than in a baseline comparison months later.

The generated inputs live in ``tests.support.structural_probe_strategies``
so the report-building context manager can be shared rather than restated.
"""

import pathlib
import tempfile

import hypothesis as hyp
import hypothesis.strategies as st
import pytest
from stilyagi import model

from tests.performance import structural_probe
from tests.support.assertions import assert_with_context
from tests.support.structural_probe_strategies import (
    DURATIONS,
    FILE_BYTES,
    PATH_COMPONENT,
    RELATIVE_PATH,
    RUNS,
    built_report,
    fixture_corpora,
)


@hyp.given(durations=DURATIONS)
@hyp.settings(max_examples=64)
def test_summarise_durations_is_bounded_by_its_own_extremes(
    durations: list[int],
) -> None:
    """The summary cannot contain a value the input does not contain."""
    summary = structural_probe.summarise_durations(durations)

    assert_with_context(
        summary["min"] <= summary["median"] <= summary["max"],
        "expected the summary to lie between its own minimum and maximum",
    )


@hyp.given(durations=DURATIONS)
@hyp.settings(max_examples=64)
def test_summarise_durations_reports_the_actual_minimum_and_maximum(
    durations: list[int],
) -> None:
    """Minimum and maximum are the input's extremes, not position-dependent."""
    summary = structural_probe.summarise_durations(durations)

    assert_with_context(
        summary["min"] == min(durations),
        "expected summary['min'] to be the input minimum",
    )
    assert_with_context(
        summary["max"] == max(durations),
        "expected summary['max'] to be the input maximum",
    )


@hyp.given(durations=DURATIONS)
@hyp.settings(max_examples=64)
def test_summarise_durations_always_reports_an_integer_median(
    durations: list[int],
) -> None:
    """The median is a plain ``int`` even when the input length is even.

    ``statistics.median`` returns a half-integer mean for an even-length
    sequence; the module casts it, and the cast must survive every length.
    """
    summary = structural_probe.summarise_durations(durations)

    assert_with_context(
        type(summary["median"]) is int,
        "expected the median to be a plain int",
    )


@hyp.given(
    durations=st.lists(
        st.integers(min_value=0, max_value=10**6),
        min_size=1,
        max_size=8,
    )
)
@hyp.settings(max_examples=64)
def test_summarise_durations_median_is_the_truncated_lower_middle(
    durations: list[int],
) -> None:
    """Pin the deterministic cast against an independently sorted middle.

    Odd lengths select the middle element; even lengths average the two
    middle elements, which for non-negative readings truncates downwards.
    """
    ordered = sorted(durations)
    middle = len(ordered) // 2
    expected = (
        ordered[middle]
        if len(ordered) % 2
        else int((ordered[middle - 1] + ordered[middle]) / 2)
    )

    summary = structural_probe.summarise_durations(durations)

    assert_with_context(
        summary["median"] == expected,
        "expected the median to be the truncated lower middle value",
    )


@hyp.given(durations=DURATIONS)
@hyp.settings(max_examples=64)
def test_summarise_durations_ignores_input_order(durations: list[int]) -> None:
    """Reversing the readings cannot change the summary."""
    summary = structural_probe.summarise_durations(durations)

    assert_with_context(
        summary == structural_probe.summarise_durations(list(reversed(durations))),
        "expected the summary to be independent of input order",
    )


@hyp.given(
    relative_path=RELATIVE_PATH,
    root_fragment=PATH_COMPONENT,
    byte_count=FILE_BYTES,
)
@hyp.settings(max_examples=64, deadline=None)
def test_normalise_repository_path_returns_posix_relative_text(
    relative_path: str,
    root_fragment: str,
    byte_count: int,
) -> None:
    """A path beneath the root normalises to a relative POSIX string.

    ``deadline=None`` because each example creates and removes a directory
    tree; elapsed time tracks filesystem latency under a shared runner.
    """
    with tempfile.TemporaryDirectory(prefix=root_fragment) as root_dir:
        root = pathlib.Path(root_dir)
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * byte_count)

        normalised = structural_probe.normalise_repository_path(target, root)

    assert_with_context(
        normalised == relative_path,
        "expected the path beneath the root to survive verbatim",
    )
    assert_with_context(
        not normalised.startswith("/"),
        "expected no leading separator",
    )
    assert_with_context(
        "\\" not in normalised,
        "expected POSIX separators only",
    )


@hyp.given(relative_path=RELATIVE_PATH, root_fragment=PATH_COMPONENT)
@hyp.settings(max_examples=64, deadline=None)
def test_normalise_repository_path_rejects_paths_outside_the_root(
    relative_path: str,
    root_fragment: str,
) -> None:
    """A sibling directory is outside the root and always raises."""
    with tempfile.TemporaryDirectory(prefix=root_fragment) as root_dir:
        root = pathlib.Path(root_dir)
        # The prefix makes the sibling distinct from the random temporary
        # directory itself, which would otherwise normalise to ``"."``.
        outside = root.parent / f"outside-{relative_path}"

        with pytest.raises(ValueError, match="is not under repository root"):
            structural_probe.normalise_repository_path(outside, root)


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_build_report_pins_the_schema_identity(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """Every generated report names the same schema, probe, and entrypoint."""
    with built_report(fixture_specs, runs) as report:
        assert_with_context(
            report["schema_version"] == structural_probe.SCHEMA_VERSION,
            "expected the schema version to be the module constant",
        )
        assert_with_context(
            report["schema_version"] == 1,
            "expected the schema version to be 1",
        )
        assert_with_context(
            report["probe"] == structural_probe.PROBE_NAME,
            "expected the probe name to be the module constant",
        )
        assert_with_context(
            report["entrypoint"] == structural_probe.ENTRYPOINT,
            "expected the entrypoint to be the module constant",
        )


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_build_report_corpus_totals_describe_the_supplied_fixtures(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """Corpus counts describe exactly the fixtures that were supplied."""
    with built_report(fixture_specs, runs) as report:
        corpus = report["corpus"]

        # Compare against the inputs, not against another field of the same
        # report: a build that dropped or duplicated a fixture could leave
        # ``file_count`` and ``fixture_paths`` agreeing with each other.
        assert_with_context(
            corpus["file_count"] == len(fixture_specs) == len(corpus["fixture_paths"]),
            "expected one corpus entry per supplied fixture",
        )
        assert_with_context(
            sorted(corpus["fixture_paths"])
            == sorted(path.as_posix() for path, _ in fixture_specs),
            "expected the corpus paths to be the supplied relative paths",
        )
        assert_with_context(
            all(
                not path.startswith("/") and "\\" not in path
                for path in corpus["fixture_paths"]
            ),
            "expected every corpus path to be relative POSIX text",
        )
        assert_with_context(
            corpus["total_bytes"] == sum(byte_count for _, byte_count in fixture_specs),
            "expected corpus['total_bytes'] to be the supplied byte total",
        )
        assert_with_context(
            set(corpus["per_syntax"]) <= {syntax.value for syntax in model.Syntax},
            "expected per_syntax keys to be registered syntaxes",
        )


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_build_report_run_iterations_match_the_durations(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """Each run's iteration count is the length of its own durations."""
    with built_report(fixture_specs, runs) as report:
        assert_with_context(
            len(report["runs"]) == len(runs),
            "expected one payload per supplied run",
        )
        for payload, run in zip(report["runs"], runs, strict=True):
            durations_ns = payload["durations_ns"]
            assert_with_context(
                isinstance(durations_ns, list),
                "expected unredacted durations in a fresh report",
            )
            assert_with_context(
                payload["iterations"] == len(durations_ns),
                "expected run['iterations'] == len(run['durations_ns'])",
            )
            assert_with_context(
                durations_ns == list(run.durations_ns),
                "expected the payload to carry the measured durations in order",
            )


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_build_report_run_summaries_match_the_durations(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """Every run's timing fields are derivable from its own durations."""
    with built_report(fixture_specs, runs) as report:
        for payload in report["runs"]:
            durations_ns = payload["durations_ns"]
            assert_with_context(
                isinstance(durations_ns, list),
                "expected unredacted durations in a fresh report",
            )
            expected = structural_probe.summarise_durations(durations_ns)
            summary = payload["summary_ns"]
            assert_with_context(
                summary == expected,
                "expected the run summary to summarise its own durations",
            )
            assert_with_context(
                payload["median_ns_per_file"] == expected["median"],
                "expected the median per file to reuse the summary median",
            )


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_redact_report_preserves_structural_fields(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """Redaction replaces volatile values and leaves structure untouched."""
    with built_report(fixture_specs, runs) as report:
        redacted = structural_probe.redact_report(report)

    for key in ("schema_version", "probe", "entrypoint", "corpus"):
        assert_with_context(
            redacted[key] == report[key],
            f"expected redaction to preserve {key!r}",
        )


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_redact_report_replaces_every_timing_and_environment_value(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """No timing or environment value survives redaction."""
    with built_report(fixture_specs, runs) as report:
        redacted = structural_probe.redact_report(report)

    assert_with_context(
        redacted["environment"] == {"platform": "<redacted>", "python": "<redacted>"},
        "expected both environment values to be redacted",
    )
    assert_with_context(
        len(redacted["runs"]) == len(report["runs"]),
        "expected redaction to preserve the run count",
    )
    for payload in redacted["runs"]:
        assert_with_context(
            payload["durations_ns"] == "<redacted>",
            "expected durations to be redacted",
        )
        summary = payload["summary_ns"]
        assert_with_context(
            isinstance(summary, dict),
            "expected a redacted summary mapping",
        )
        assert_with_context(
            set(summary.values()) == {"<redacted>"},
            "expected every summary value to be redacted",
        )
        assert_with_context(
            payload["median_ns_per_file"] == "<redacted>",
            "expected the median per file to be redacted",
        )
        assert_with_context(
            payload["throughput_mib_per_s"] == "<redacted>",
            "expected throughput to be redacted",
        )


@hyp.given(fixture_specs=fixture_corpora(), runs=RUNS)
@hyp.settings(max_examples=64, deadline=None)
def test_redact_report_preserves_non_timing_run_fields(
    fixture_specs: list[tuple[pathlib.Path, int]],
    runs: list[structural_probe.ProbeRun],
) -> None:
    """Mode, syntax, byte count, and iteration count are not timing values."""
    with built_report(fixture_specs, runs) as report:
        redacted = structural_probe.redact_report(report)

        for original, redacted_payload in zip(
            report["runs"], redacted["runs"], strict=True
        ):
            for key in ("mode", "syntax", "byte_count", "iterations"):
                assert_with_context(
                    redacted_payload[key] == original[key],
                    f"expected redaction to preserve run {key!r}",
                )
