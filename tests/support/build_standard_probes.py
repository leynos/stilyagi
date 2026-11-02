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
import typing as typ

from tests.support.build_standard import (
    MAKE_OVERRIDES,
    PROBE_NAMES,
    REPOSITORY_ROOT,
    ToolInvocation,
    run_make,
)

if typ.TYPE_CHECKING:
    import pathlib

_PROBE_SOURCE: typ.Final = """\
import json, os, sys

name = os.path.basename(sys.argv[0])
record = {
    "program": name,
    "args": sys.argv[1:],
    "env": {
        key: os.environ.get(key) for key in ("RUSTFLAGS", "RUSTDOCFLAGS")
    },
}
with open(os.environ["PROBE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(record) + "\\n")
failing = os.environ.get("PROBE_FAIL", "")
if failing and failing in name + " " + " ".join(sys.argv[1:]):
    sys.exit(1)
"""


def make_recording_tools(directory: pathlib.Path) -> pathlib.Path:
    """Create probe executables that log their arguments and `RUSTFLAGS`.

    Each probe appends one JSON line to `$PROBE_LOG` and exits 0, unless the
    `PROBE_FAIL` environment variable is a substring of `<name> <args>`, when
    it exits 1. That is how a test makes `nextest --version` fail to take the
    `cargo test` fallback, or a preflight fail to prove it stops the target.

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


def run_recorded(
    target: str,
    tree: RecordingTree,
    *,
    ambient_rustflags: str | None,
    fail: str = "",
) -> RecordedRun:
    """Run `make <target>` in a staged tree and return what the probes saw.

    Parameters
    ----------
    target
        The Make target.
    tree
        A staged tree from `stage_makefile_tree` with its recording probes.
    ambient_rustflags
        The `RUSTFLAGS` the caller exports (CI exports `-D warnings`), or
        None for a caller exporting none.
    fail
        A substring of `<probe> <args>` that makes the probe exit 1.

    Returns
    -------
    RecordedRun
        Make's exit status, its stderr, and each probe call in order.
    """
    log = tree.workdir / "probe.log"
    log.unlink(missing_ok=True)
    env = {key: value for key, value in os.environ.items() if key != "RUSTFLAGS"}
    env |= {
        "PATH": f"{tree.tools}{os.pathsep}{env['PATH']}",
        "PROBE_LOG": str(log),
        "PROBE_FAIL": fail,
    }
    if ambient_rustflags is not None:
        env["RUSTFLAGS"] = ambient_rustflags
    result = run_make(
        ["--no-print-directory", *MAKE_OVERRIDES, target], env, tree.workdir
    )
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    records = tuple(_record(json.loads(line)) for line in lines)
    return RecordedRun(result.returncode, result.stderr, records)


def _record(raw: dict[str, typ.Any]) -> ToolInvocation:
    """Return one probe log line as an invocation."""
    return ToolInvocation(
        program=raw["program"], args=tuple(raw["args"]), env=dict(raw["env"])
    )
