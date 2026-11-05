"""Recording probes that observe the `RUSTFLAGS` a Make target hands each tool.

`build_standard` reads what Make's text says. These helpers run a target
against stand-in executables that log their arguments and the compiler-flag
variables they received, which is what shows how an ambient `RUSTFLAGS` (CI
exports one) interacts with a recipe's own assignment.
"""

import dataclasses as dc
import json
import os
import shutil
import stat
import sys
import time
import typing as typ

from tests.support.build_standard import (
    MAKE_OVERRIDES,
    PROBE_NAMES,
    REPOSITORY_ROOT,
    ToolInvocation,
    start_make,
)

if typ.TYPE_CHECKING:
    import pathlib
    import subprocess

_PROBE_SOURCE: typ.Final = """\
import json, os, sys, time

name = os.path.basename(sys.argv[0])
identity = name + " " + " ".join(sys.argv[1:])
record = {
    "program": name,
    "args": sys.argv[1:],
    "env": {
        key: os.environ.get(key) for key in ("RUSTFLAGS", "RUSTDOCFLAGS")
    },
}
with open(os.environ["PROBE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(record) + "\\n")
blocking = os.environ.get("PROBE_BLOCK", "")
if blocking and blocking in identity:
    deadline = time.monotonic() + 120
    release = os.environ["PROBE_RELEASE"]
    while not os.path.exists(release):
        if time.monotonic() > deadline:
            sys.exit(2)
        time.sleep(0.02)
failing = os.environ.get("PROBE_FAIL", "")
if failing and failing in identity:
    sys.exit(1)
"""


def make_recording_tools(directory: pathlib.Path) -> pathlib.Path:
    """Create probe executables that log their arguments and `RUSTFLAGS`.

    Each probe appends one JSON line to `$PROBE_LOG` and exits 0, unless the
    `PROBE_FAIL` environment variable is a substring of `<name> <args>`, when
    it exits 1. That is how a test makes `nextest --version` fail to take the
    `cargo test` fallback, or a preflight fail to prove it stops the target.
    A probe whose `<name> <args>` matches `$PROBE_BLOCK` first waits for the
    file named by `$PROBE_RELEASE`, so a test can hold a stage open and check
    what has not started yet.

    Returns
    -------
    pathlib.Path
        `directory`, now holding the probe executables.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in PROBE_NAMES:
        path = directory / name
        path.write_text(f"#!{sys.executable}\n{_PROBE_SOURCE}", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return directory


def stage_makefile_tree(destination: pathlib.Path) -> pathlib.Path:
    """Copy the files a Make run reads into `destination`, and return it.

    A recording run executes recipes, some of which delete or create paths
    such as `dist`. A copy keeps them off the real checkout.

    Returns
    -------
    pathlib.Path
        `destination`, now holding the copied files.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for name in (
        "Makefile",
        "pyproject.toml",
        "uv.lock",
        "Cargo.toml",
        "Cargo.lock",
        "scripts/duplication_gate.py",
    ):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / name, target)
    return destination


if typ.TYPE_CHECKING:
    import pathlib


@dc.dataclass(frozen=True, slots=True)
class RecordedRun:
    """The outcome of one recording run of a Make target."""

    returncode: int
    stderr: str
    records: tuple[ToolInvocation, ...]


@dc.dataclass(frozen=True, slots=True)
class RecordingTree:
    """A staged Make tree and the recording probes that stand in for tools."""

    workdir: pathlib.Path
    tools: pathlib.Path


@dc.dataclass(frozen=True, slots=True)
class RunOptions:
    """The environment and invocation controls for one recording run.

    Parameters
    ----------
    ambient_rustflags
        The `RUSTFLAGS` the caller exports (CI exports `-D warnings`), or
        None for a caller exporting none.
    block
        A substring of `<probe> <args>` that makes the probe wait for the
        run's release marker before it exits. A test uses it to hold one
        stage open while it inspects what else has started.
    fail
        A substring of `<probe> <args>` that makes the probe exit 1.
    make_arguments
        Extra Make arguments placed before the target, such as `("-j4",)` for
        a parallel run or a `NAME=value` assignment for a command-line
        variable override.
    """

    ambient_rustflags: str | None = None
    block: str = ""
    fail: str = ""
    make_arguments: tuple[str, ...] = ()


#: How often a live run re-reads the probe log while waiting for a block.
_POLL_SECONDS: typ.Final = 0.02
#: How long a test waits for a blocked probe to record its start.
_BLOCK_TIMEOUT_SECONDS: typ.Final = 60.0


@dc.dataclass(slots=True)
class StartedRun:
    """A recording run whose Make process has not yet been waited on.

    `start_recorded` returns one so a test can read the probe log while Make
    is still running. `finish` then returns the same evidence `run_recorded`
    would have returned.
    """

    process: subprocess.Popen[str]
    log: pathlib.Path
    release_marker: pathlib.Path
    block: str
    _finished: RecordedRun | None = dc.field(default=None, init=False)

    def records(self) -> tuple[ToolInvocation, ...]:
        """Return the records the probe log holds now."""
        return _read_records(self.log)

    def wait_for_block(self, timeout: float = _BLOCK_TIMEOUT_SECONDS) -> None:
        """Wait until the probe selected by `block` has recorded its start.

        Raises
        ------
        TimeoutError
            If Make exits, or `timeout` passes, before the probe records.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(self.block in _identity(record) for record in self.records()):
                return
            if self.process.poll() is not None:
                break
            time.sleep(_POLL_SECONDS)
        msg = f"no probe matching {self.block!r} recorded a start"
        raise TimeoutError(msg)

    def release(self) -> None:
        """Let a blocked probe continue."""
        self.release_marker.write_text("", encoding="utf-8")

    def finish(self) -> RecordedRun:
        """Wait for Make to exit and return everything the probes recorded."""
        if self._finished is None:
            _, stderr = self.process.communicate()
            self._finished = RecordedRun(
                self.process.returncode, stderr, self.records()
            )
        return self._finished

    def __enter__(self) -> typ.Self:
        """Return this run."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Release any blocked probe and reap Make, even when a test fails."""
        self.release()
        self.finish()


def start_recorded(
    target: str,
    tree: RecordingTree,
    options: RunOptions,
) -> StartedRun:
    """Start `make <target>` in a staged tree without waiting for it.

    Parameters
    ----------
    target
        The Make target.
    tree
        A staged tree from `stage_makefile_tree` with its recording probes.
    options
        The controls for this run, including the `block` selector.

    Returns
    -------
    StartedRun
        The live run; `finish` returns the records it produced.
    """
    log = tree.workdir / "probe.log"
    log.unlink(missing_ok=True)
    release = tree.workdir / "probe.release"
    release.unlink(missing_ok=True)
    arguments = [
        *options.make_arguments,
        "--no-print-directory",
        *MAKE_OVERRIDES,
        target,
    ]
    process = start_make(
        arguments, _run_environment(tree, options, log, release), tree.workdir
    )
    return StartedRun(process, log, release, options.block)


def run_recorded(
    target: str,
    tree: RecordingTree,
    options: RunOptions,
) -> RecordedRun:
    """Run `make <target>` in a staged tree and return what the probes saw.

    Parameters
    ----------
    target
        The Make target.
    tree
        A staged tree from `stage_makefile_tree` with its recording probes.
    options
        The ambient `RUSTFLAGS`, the probe selectors, and any extra Make
        options for this run.

    Returns
    -------
    RecordedRun
        Make's exit status, its stderr, and each probe call in order.
    """
    return start_recorded(target, tree, options).finish()


def _run_environment(
    tree: RecordingTree,
    options: RunOptions,
    log: pathlib.Path,
    release: pathlib.Path,
) -> dict[str, str]:
    """Return the environment a recording run hands its probes."""
    env = {key: value for key, value in os.environ.items() if key != "RUSTFLAGS"}
    env |= {
        "PATH": f"{tree.tools}{os.pathsep}{env['PATH']}",
        "PROBE_LOG": str(log),
        "PROBE_BLOCK": options.block,
        "PROBE_RELEASE": str(release),
        "PROBE_FAIL": options.fail,
    }
    if options.ambient_rustflags is not None:
        env["RUSTFLAGS"] = options.ambient_rustflags
    return env


def _read_records(log: pathlib.Path) -> tuple[ToolInvocation, ...]:
    """Return the records a probe log holds, skipping a torn trailing line.

    A live run polls the log while a probe may be mid-write, so the last line
    can be incomplete. A completed run never loses a record this way.

    Returns
    -------
    tuple[ToolInvocation, ...]
        Each complete probe call in the order it was recorded.
    """
    if not log.exists():
        return ()
    records: list[ToolInvocation] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            records.append(_record(json.loads(line)))
        except json.JSONDecodeError:
            continue
    return tuple(records)


def _identity(record: ToolInvocation) -> str:
    """Return the text a probe matches its selectors against."""
    return f"{record.program} {' '.join(record.args)}"


def _record(raw: dict[str, typ.Any]) -> ToolInvocation:
    """Return one probe log line as an invocation."""
    return ToolInvocation(
        program=raw["program"], args=tuple(raw["args"]), env=dict(raw["env"])
    )
