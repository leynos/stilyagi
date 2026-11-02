"""Hold every Cargo and maturin invocation Make evaluates to the build standard.

Each gate recipe assigns `RUSTFLAGS`, and an assignment displaces the Cargo
configuration's `rustflags` outright, so a recipe that restates only
`-D warnings` stays green while building without the standard. These contracts
read the evaluated invocation of every route separately (a Cargo invocation
per line, both branches of the nextest fallback, doctests, Clippy, rustdoc,
Whitaker, maturin and the editable install), then run the targets against
recording probes to observe the `RUSTFLAGS` each tool would receive, with and
without the `-D warnings` CI exports.

Make's text alone does not prove compiler behaviour; the empirical builds in
docs/developers-guide.md (verbose rustc lines, `readelf -p .comment`) do.
"""

import dataclasses as dc
import sys
import typing as typ

import pytest

from tests.support.build_standard import (
    MOLD_FLAG,
    PROBE_CARGO,
    PROBE_CHECK,
    PROBE_UV,
    PROBE_WHITAKER,
    THREADS_FLAG,
    ToolInvocation,
    compiles,
    dry_run,
    make_available_tools,
    read_invocations,
)
from tests.support.build_standard_probes import (
    RecordingTree,
    make_recording_tools,
    run_recorded,
    stage_makefile_tree,
)

if typ.TYPE_CHECKING:
    import pathlib

IS_LINUX_HOST: typ.Final = sys.platform.startswith("linux")
GATE_TARGETS: typ.Final = (
    "typecheck",
    "lint",
    "test",
    "test-doc",
    "test-ci",
    "test-quick",
)


@dc.dataclass(frozen=True, slots=True)
class Route:
    """One compiling invocation a Make target is expected to evaluate."""

    case_id: str
    target: str
    kind: typ.Literal["gate", "dev", "release", "whitaker"]
    program: str
    prefix: tuple[str, ...]
    required_arg: str | None = None
    forbidden_arg: str | None = None

    def matches(self, invocation: ToolInvocation) -> bool:
        """Return whether `invocation` is this route's invocation."""
        return (
            invocation.program == self.program
            and invocation.has_args(*self.prefix)
            and (self.required_arg is None or self.required_arg in invocation.args)
            and (
                self.forbidden_arg is None or self.forbidden_arg not in invocation.args
            )
        )


def _cargo(case_id: str, target: str, *prefix: str, **kwargs: str) -> Route:
    """Return a gate route over a `cargo` subcommand."""
    return Route(case_id, target, "gate", PROBE_CARGO, prefix, **kwargs)


#: Distinct ids, because `#[case::name]`-style discovery trouble recorded in the
#: estate playbook makes a shared id a silently missing case.
ROUTES: typ.Final[tuple[Route, ...]] = (
    _cargo("make_typecheck_check", "typecheck", "check"),
    _cargo("make_lint_doc", "lint", "doc"),
    _cargo("make_lint_clippy", "lint", "clippy"),
    Route("make_lint_whitaker", "lint", "whitaker", PROBE_WHITAKER, ()),
    _cargo("make_test_clippy", "test", "clippy"),
    _cargo("make_test_nextest", "test", "nextest", "run"),
    _cargo("make_test_cargo_test_fallback", "test", "test", forbidden_arg="--doc"),
    _cargo("make_test_doc", "test", "test", required_arg="--doc"),
    _cargo("make_test_doc_doc", "test-doc", "test", required_arg="--doc"),
    _cargo("make_test_ci_nextest", "test-ci", "nextest", "run", "--profile", "ci"),
    _cargo("make_test_ci_doc", "test-ci", "test", required_arg="--doc"),
    _cargo("make_test_quick_nextest", "test-quick", "nextest", "run"),
    Route("make_build_maturin_develop", "build", "dev", PROBE_UV, (), "develop"),
    Route("make_venv_uv_sync", ".venv", "dev", PROBE_UV, ("sync",)),
    Route(
        "make_release_artifact_maturin_build",
        "release-artifact",
        "release",
        PROBE_UV,
        (),
        "--release",
    ),
)
EXPECTED_ROUTE_COUNT: typ.Final = 15

ROUTE_PARAMS: typ.Final = [pytest.param(route, id=route.case_id) for route in ROUTES]


@pytest.fixture(scope="module")
def probe_dir(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """Return a directory of empty probe executables on which `command -v` works."""
    return make_available_tools(tmp_path_factory.mktemp("probes"))


def _compiling(target: str, probe_dir: pathlib.Path) -> list[ToolInvocation]:
    """Return the compiling invocations Make evaluates for `target`."""
    output = dry_run(target, probe_dir)
    programs = (PROBE_CARGO, PROBE_WHITAKER, PROBE_UV)
    return [inv for inv in read_invocations(output, programs) if compiles(inv)]


def _expected_standard() -> tuple[str, ...]:
    """Return the standard flags the host's Make restates."""
    return (THREADS_FLAG, MOLD_FLAG) if IS_LINUX_HOST else (THREADS_FLAG,)


def _assert_kind(kind: str, invocation: ToolInvocation, label: str) -> None:
    """Assert that an invocation carries the flag policy of its route kind."""
    flags = invocation.rustflags
    assert flags is not None, f"{label}: expected the recipe to assign RUSTFLAGS"
    standard = _expected_standard()
    if kind in {"gate", "dev"}:
        missing = [flag for flag in standard if flag not in flags.split()]
        assert not missing, f"{label}: RUSTFLAGS {flags!r} dropped {missing}"
    if kind == "gate":
        assert "-D warnings" in flags, f"{label}: RUSTFLAGS {flags!r} lost -D warnings"
    if kind in {"release", "whitaker"}:
        leaked = [flag for flag in (THREADS_FLAG, MOLD_FLAG) if flag in flags]
        assert not leaked, f"{label}: RUSTFLAGS {flags!r} leaks {leaked}"
    if kind == "whitaker":
        assert flags == "-D warnings", f"{label}: expected the known boundary"


def test_the_route_table_is_the_expected_size() -> None:
    """Distinct ids, and a count to catch a case silently dropped."""
    ids = [route.case_id for route in ROUTES]
    assert len(ids) == len(set(ids)) == EXPECTED_ROUTE_COUNT, (
        "expected len(ids) == len(set(ids)) == EXPECTED_ROUTE_COUNT"
    )


@pytest.mark.parametrize("route", ROUTE_PARAMS)
def test_each_route_carries_its_flag_policy(
    route: Route, probe_dir: pathlib.Path
) -> None:
    """Every route's own invocation line carries its kind's flags, once."""
    matches = [inv for inv in _compiling(route.target, probe_dir) if route.matches(inv)]
    assert len(matches) == 1, f"{route.case_id}: found {len(matches)} invocations"
    _assert_kind(route.kind, matches[0], route.case_id)


@pytest.mark.parametrize(
    "target", [*GATE_TARGETS, "build", "release-artifact", ".venv"]
)
def test_no_compiling_invocation_escapes_the_route_table(
    target: str, probe_dir: pathlib.Path
) -> None:
    """A Cargo line no route names fails, so a new line cannot skip the policy."""
    unlisted = [
        inv
        for inv in _compiling(target, probe_dir)
        if not any(route.matches(inv) for route in ROUTES)
    ]
    assert not unlisted, f"{target}: unrouted invocations {unlisted}"


@pytest.mark.parametrize("target", [*GATE_TARGETS, "build", "release-artifact"])
def test_executable_substitution_is_honoured(
    target: str, probe_dir: pathlib.Path
) -> None:
    """With the tools overridden, no recipe line still names the real tool."""
    output = dry_run(target, probe_dir)
    assert not read_invocations(output, ("cargo", "whitaker")), (
        "expected not read_invocations(output, ('cargo', 'whitaker'))"
    )
    probes = (PROBE_CARGO, PROBE_UV, PROBE_WHITAKER)
    assert any(compiles(inv) for inv in read_invocations(output, probes)), target


def test_the_nextest_fallback_branch_is_read_alongside_its_primary(
    probe_dir: pathlib.Path,
) -> None:
    """`make test` reads both branches of the shell conditional, not one."""
    cargo = [inv for inv in _compiling("test", probe_dir) if inv.program == PROBE_CARGO]
    subcommands = {inv.args[0] for inv in cargo}
    assert {"nextest", "test"} <= subcommands, (
        "expected {'nextest', 'test'} <= subcommands"
    )


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
    run = run_recorded(target, recording, ambient_rustflags=ambient)
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
    run = run_recorded("lint", recording, ambient_rustflags=ambient)
    assert run.returncode == 0, run.stderr
    whitaker = [r for r in run.records if r.program == PROBE_WHITAKER]
    assert len(whitaker) == 1, "expected len(whitaker) == 1"
    _assert_kind("whitaker", whitaker[0], "lint: whitaker")


@pytest.mark.parametrize("ambient", AMBIENT)
def test_executed_release_route_displaces_the_standard_and_skips_the_preflight(
    ambient: str | None, recording: RecordingTree
) -> None:
    """The release wheel and the editable install take the caller's flags only."""
    run = run_recorded("release-artifact", recording, ambient_rustflags=ambient)
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
    run = run_recorded(target, recording, ambient_rustflags="-D warnings")
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
    run = run_recorded(target, recording, ambient_rustflags=None, fail=PROBE_CHECK)
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
        ambient_rustflags="-D warnings",
        fail=f"{PROBE_CARGO} nextest --version",
    )
    assert run.returncode == 0, run.stderr
    cargo = [r for r in run.records if r.program == PROBE_CARGO]
    assert not [r for r in cargo if r.has_args("nextest", "run")], (
        "expected not [r for r in cargo if r.has_args('nextest', 'run')]"
    )
    fallback = [r for r in cargo if r.has_args("test") and "--doc" not in r.args]
    assert len(fallback) == 1, "expected len(fallback) == 1"
    _assert_kind("gate", fallback[0], "fallback")
