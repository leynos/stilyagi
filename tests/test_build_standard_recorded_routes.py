"""Execute every gate route against recording probes and hold its outcome.

`tests/test_build_standard_make_routes.py` reads what Make would evaluate, and
a dry run shows the recipe text but neither the environment a tool actually
receives nor whether its exit status reaches the shell. These contracts run the
targets against probes that log the `RUSTFLAGS` they were handed, and assert
both the flags and the failure propagation.

The route table and the flag policy stay in that module, which this one reads
through `_assert_kind`, so there is one description of what each route kind
must carry.
"""

import typing as typ

import pytest

from tests.support.build_standard import (
    PROBE_CARGO,
    PROBE_CHECK,
    PROBE_WHITAKER,
    ToolInvocation,
    compiles,
)
from tests.support.build_standard_probes import (
    RecordedRun,
    RecordingTree,
    RunOptions,
    make_recording_tools,
    run_recorded,
    stage_makefile_tree,
    start_recorded,
)
from tests.test_build_standard_make_routes import GATE_TARGETS, _assert_kind

if typ.TYPE_CHECKING:
    import pathlib


@pytest.fixture
def recording(tmp_path: pathlib.Path) -> RecordingTree:
    """Return a staged Make tree and a directory of recording probes."""
    return RecordingTree(
        stage_makefile_tree(tmp_path / "tree"),
        make_recording_tools(tmp_path / "bin"),
    )


AMBIENT: typ.Final = [
    pytest.param(None, id="no_ambient_rustflags"),
    pytest.param("-D warnings", id="ci_exports_warnings"),
]


@pytest.mark.parametrize("ambient", AMBIENT)
@pytest.mark.parametrize("target", [*GATE_TARGETS, "build"])
def test_executed_dev_routes_keep_the_standard(
    target: str,
    ambient: str | None,
    recording: RecordingTree,
) -> None:
    """Under CI's exported `-D warnings`, every compile still gets the standard."""
    run = run_recorded(target, recording, RunOptions(ambient_rustflags=ambient))
    assert run.returncode == 0, run.stderr
    compiling = [
        record
        for record in run.records
        if compiles(record) and record.program != PROBE_WHITAKER
    ]
    assert compiling, f"{target}: no compiling invocation was recorded"
    for record in compiling:
        is_editable_install = "maturin" in record.args or record.has_args("sync")
        kind = "dev" if is_editable_install else "gate"
        _assert_kind(kind, record, f"{target}: {record.program} {record.args}")


@pytest.mark.parametrize("ambient", AMBIENT)
def test_executed_whitaker_route_takes_no_development_flags(
    ambient: str | None, recording: RecordingTree
) -> None:
    """Whitaker's `RUSTFLAGS` is `-D warnings` whatever the caller exports."""
    run = run_recorded("lint", recording, RunOptions(ambient_rustflags=ambient))
    assert run.returncode == 0, run.stderr
    whitaker = [r for r in run.records if r.program == PROBE_WHITAKER]
    assert len(whitaker) == 1, "expected len(whitaker) == 1"
    _assert_kind("whitaker", whitaker[0], "lint: whitaker")


#: The package and target scope Whitaker receives after `--`.
CARGO_SCOPE: typ.Final = (
    "--manifest-path",
    "Cargo.toml",
    "--workspace",
    "--all-targets",
    "--all-features",
)


def _single_whitaker_invocation(run: RecordedRun) -> ToolInvocation:
    """Return the one Whitaker invocation a run recorded."""
    whitaker = [record for record in run.records if record.program == PROBE_WHITAKER]
    assert len(whitaker) == 1, f"expected one Whitaker invocation, got {whitaker}"
    return whitaker[0]


def test_lint_whitaker_defaults_to_every_library_and_scopes_with_cargo_flags(
    recording: RecordingTree,
) -> None:
    """Whitaker loads `--all` and takes the Cargo scope after `--`."""
    run = run_recorded("lint-whitaker", recording, RunOptions())
    assert run.returncode == 0, run.stderr
    invocation = _single_whitaker_invocation(run)
    assert "--" in invocation.args, invocation.args
    separator = invocation.args.index("--")
    assert invocation.args[:separator] == ("--all",)
    assert invocation.args[separator + 1 :] == CARGO_SCOPE


def test_lint_whitaker_forwards_a_command_line_library_override(
    recording: RecordingTree,
) -> None:
    """A `WHITAKER_LIBRARIES` assignment replaces the `--all` default."""
    run = run_recorded(
        "lint-whitaker",
        recording,
        RunOptions(make_arguments=("WHITAKER_LIBRARIES=--lib-a --lib-b",)),
    )
    assert run.returncode == 0, run.stderr
    invocation = _single_whitaker_invocation(run)
    assert "--" in invocation.args, invocation.args
    separator = invocation.args.index("--")
    assert invocation.args[:separator] == ("--lib-a", "--lib-b")
    assert invocation.args[separator + 1 :] == CARGO_SCOPE


def test_parallel_lint_cannot_start_whitaker_until_clippy_completes(
    recording: RecordingTree,
) -> None:
    """`make -j4 lint` holds Whitaker back while a Clippy-stage probe blocks."""
    options = RunOptions(make_arguments=("-j4",), block=f"{PROBE_CARGO} clippy")
    with start_recorded("lint", recording, options) as run:
        run.wait_for_block()
        assert not [r for r in run.records() if r.program == PROBE_WHITAKER], (
            "Whitaker started while the Clippy stage was still running"
        )
        run.release()
    finished = run.finish()
    assert finished.returncode == 0, finished.stderr
    clippy = next(
        index
        for index, record in enumerate(finished.records)
        if record.program == PROBE_CARGO and record.has_args("clippy")
    )
    whitaker = next(
        index
        for index, record in enumerate(finished.records)
        if record.program == PROBE_WHITAKER
    )
    assert clippy < whitaker, (
        f"expected cargo clippy before Whitaker: clippy at {clippy}, "
        f"whitaker at {whitaker}"
    )


@pytest.mark.parametrize("target", ["lint-whitaker", "lint"])
@pytest.mark.parametrize(
    ("fail", "should_pass"),
    [("", True), ("whitaker", False)],
    ids=["whitaker_passes", "whitaker_fails"],
)
def test_a_whitaker_failure_fails_the_gate(
    target: str,
    fail: str,
    recording: RecordingTree,
    *,
    should_pass: bool,
) -> None:
    """The Whitaker exit status reaches Make, and so CI, without being masked."""
    run = run_recorded(
        target,
        recording,
        RunOptions(fail=fail),
    )
    if should_pass:
        assert run.returncode == 0, run.stderr
    else:
        assert run.returncode != 0, "expected run.returncode != 0"
        assert [r for r in run.records if r.program == PROBE_WHITAKER], (
            "expected the Whitaker probe to have run"
        )


@pytest.mark.parametrize("ambient", AMBIENT)
def test_executed_release_route_displaces_the_standard_and_skips_the_preflight(
    ambient: str | None, recording: RecordingTree
) -> None:
    """The release wheel and the editable install take the caller's flags only."""
    run = run_recorded(
        "release-artefact", recording, RunOptions(ambient_rustflags=ambient)
    )
    assert run.returncode == 0, run.stderr
    assert not [r for r in run.records if r.program == PROBE_CHECK], (
        "expected not [r for r in run.records if r.program == PROBE_CHECK]"
    )
    builds = [r for r in run.records if compiles(r)]
    assert [b.args[:2] for b in builds if "maturin" in b.args], "no maturin build"
    for build in builds:
        assert build.rustflags == (ambient or ""), (build.args, build.rustflags)


@pytest.mark.parametrize("target", [*GATE_TARGETS, "build"])
def test_the_preflight_runs_before_any_compilation(
    target: str, recording: RecordingTree
) -> None:
    """The first record of each dev or gate route is the build-tools check."""
    run = run_recorded(target, recording, RunOptions(ambient_rustflags="-D warnings"))
    assert run.returncode == 0, run.stderr
    first_check = next(
        (i for i, r in enumerate(run.records) if r.program == PROBE_CHECK), None
    )
    assert first_check is not None, f"{target}: the preflight never ran"
    first_compile = next(i for i, r in enumerate(run.records) if compiles(r))
    assert first_check < first_compile, f"{target}: compiled before the preflight"


@pytest.mark.parametrize("target", [*GATE_TARGETS, "build"])
def test_a_failing_preflight_stops_the_target_before_compiling(
    target: str, recording: RecordingTree
) -> None:
    """A preflight that exits 1 ends the run: nothing compiles after it."""
    run = run_recorded(target, recording, RunOptions(fail=PROBE_CHECK))
    assert run.returncode != 0, "expected run.returncode != 0"
    assert not [r for r in run.records if compiles(r)], (
        "expected not [r for r in run.records if compiles(r)]"
    )


def test_the_cargo_test_fallback_carries_the_standard_when_nextest_is_absent(
    recording: RecordingTree,
) -> None:
    """With `nextest --version` failing, the `cargo test` branch runs and is flagged."""
    run = run_recorded(
        "test",
        recording,
        RunOptions(
            ambient_rustflags="-D warnings",
            fail=f"{PROBE_CARGO} nextest --version",
        ),
    )
    assert run.returncode == 0, run.stderr
    cargo = [r for r in run.records if r.program == PROBE_CARGO]
    assert not [r for r in cargo if r.has_args("nextest", "run")], (
        "expected not [r for r in cargo if r.has_args('nextest', 'run')]"
    )
    fallback = [r for r in cargo if r.has_args("test") and "--doc" not in r.args]
    assert len(fallback) == 1, "expected len(fallback) == 1"
    _assert_kind("gate", fallback[0], "fallback")
