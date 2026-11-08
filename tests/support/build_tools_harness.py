"""Shared stand-ins for driving scripts/build_tools.py at two boundaries.

The script runs `curl`, `tar`, `rustup` and `mold`, and every failure it
reports is a promise to the developer: an actionable `build-tools:` line and a
non-zero exit instead of a silent fallback to a slower or different build.

The stand-ins serve two kinds of test, and the difference is what each can see.
The cross-process cases run the script as a subprocess whose `PATH` holds only
shims, so a real `mold` on the machine cannot make a missing-tool case pass for
the wrong reason, and they read the journal to prove what was, and was not, run.
The in-process cases import the script and call its orchestration with the
catalogue runner replaced. Nothing is spawned there, so a result value is
observable directly -- which is how the exact problem set of one preflight, or
the whole argument vector of one tool call, is asserted rather than
pattern-matched out of a merged standard-error stream.

`ScriptedRunner` and `CurlServingRunner` are the in-process answers, and
`command_result` builds the values they return. The shim factories and journal
helpers are their cross-process counterparts. Importing the script also puts
its sibling modules on the path, so `build_tools_environment` and
`build_tools_pins` are available to both kinds.
"""

import dataclasses as dc
import hashlib
import importlib.util
import io
import os
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs this repository's script under a shim-only PATH.
import sys
import tarfile
import typing as typ

from cuprum.program import Program
from cuprum.sh import CommandResult

from tests.support.errors import ReadingError

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import types

    from cmd_mox import CmdMox, Invocation

    type Handler = cabc.Callable[[Invocation], tuple[str, str, int]]

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "build_tools.py"
CHANNEL = "nightly-2026-10-18"
HOST = "x86_64-unknown-linux-gnu"
COMPONENTS = ("clippy", "rustc-codegen-cranelift-preview", "rustfmt")
MOLD_ARCHIVE = "mold-2.41.0-x86_64-linux.tar.gz"
DOWNLOAD_URL = "https://example.invalid/mold"
MOLD_BANNER = "mold 2.41.0 (compatible with GNU ld)\n"


def load_script_module() -> types.ModuleType:
    """Import the script as a module, for the pure helpers."""
    spec = importlib.util.spec_from_file_location("build_tools_script", SCRIPT)
    if spec is None or spec.loader is None:
        message = f"cannot load {SCRIPT} as a module"
        raise ReadingError(message, reader="load_script_module", path=str(SCRIPT))
    # The script imports its sibling `build_tools_pins`, which Python resolves
    # from the script's own directory when it is run as a program.
    if str(SCRIPT.parent) not in sys.path:
        sys.path.insert(0, str(SCRIPT.parent))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build_tools = load_script_module()
# Loading the script put `scripts/` on the path; the siblings come back here so
# the in-process helpers are testable without a second import mechanism.
build_tools_environment = importlib.import_module("build_tools_environment")
build_tools_pins = importlib.import_module("build_tools_pins")


def mold_archive() -> bytes:
    """Return a gzip tarball laid out as the real mold release is."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"#!/bin/sh\necho mold 2.41.0\n"
        entry = tarfile.TarInfo("mold-2.41.0-x86_64-linux/bin/mold")
        entry.size = len(payload)
        entry.mode = 0o755
        archive.addfile(entry, io.BytesIO(payload))
    return buffer.getvalue()


@dc.dataclass(frozen=True, slots=True)
class PinWorkspace:
    """A temporary root and the pin files written beneath it.

    The pins travel together because the script is always invoked with all
    three: a case that wants to corrupt one still needs the other two.
    """

    root: pathlib.Path
    toolchain: pathlib.Path
    version: pathlib.Path
    sums: pathlib.Path


def write_pins(tmp_path: pathlib.Path) -> PinWorkspace:
    """Write fixture pin files naming the pinned channel and mold release."""
    toolchain = tmp_path / "rust-toolchain.toml"
    components = ", ".join(f'"{name}"' for name in COMPONENTS)
    toolchain.write_text(
        f'[toolchain]\nchannel = "{CHANNEL}"\ncomponents = [{components}]\n',
        encoding="utf-8",
    )
    version = tmp_path / "VERSION"
    version.write_text("2.41.0\n", encoding="utf-8")
    sums = tmp_path / "SHA256SUMS"
    digest = hashlib.sha256(mold_archive()).hexdigest()
    sums.write_text(f"{digest}  {MOLD_ARCHIVE}\n", encoding="utf-8")
    return PinWorkspace(tmp_path, toolchain, version, sums)


def rustup_replies(*, installed_components: tuple[str, ...] = COMPONENTS) -> Handler:
    """Return a rustup handler answering `toolchain list` and `component list`."""
    listed = [
        f"{name.removesuffix('-preview')}-{HOST}" for name in installed_components
    ]

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        """Answer rustup's two listing subcommands, and accept the rest."""
        if invocation.args[:2] == ["toolchain", "list"]:
            return (f"stable-{HOST} (default)\n{CHANNEL}-{HOST}\n", "", 0)
        if invocation.args[:2] == ["component", "list"]:
            return ("\n".join(listed) + "\n", "", 0)
        return ("", "", 0)

    return handler


def support_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return a directory holding only what a shim needs to start.

    A shim's shebang resolves `python3` through `PATH`. Nothing else may be
    reachable: a distribution `mold` in `/usr/bin` would otherwise answer the
    missing-mold cases.

    Returns
    -------
    pathlib.Path
        The directory to append to the shim directory on `PATH`.
    """
    support = tmp_path / "support-bin"
    support.mkdir(exist_ok=True)
    link = support / "python3"
    if not link.exists():
        link.symlink_to(sys.executable)
    return support


def run_script(
    cmd_mox: CmdMox,
    command: str,
    workspace: PinWorkspace,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    """Run `build_tools.py <command>` with only the shims on `PATH`."""
    shim_dir = cmd_mox.environment.shim_dir
    if shim_dir is None:
        message = "cmd-mox has no shim directory; is the fixture replaying?"
        raise ReadingError(message, reader="run_script")
    env = {
        **os.environ,
        "PATH": f"{shim_dir}{os.pathsep}{support_bin(workspace.root)}",
        "HOME": str(workspace.root / "home"),
    }
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv: this interpreter and this repository's script.
        [
            sys.executable,
            str(SCRIPT),
            command,
            "--toolchain-file",
            str(workspace.toolchain),
            "--mold-version-file",
            str(workspace.version),
            "--mold-sha256sums-file",
            str(workspace.sums),
            "--prefix",
            str(workspace.root / "prefix"),
            "--release-base-url",
            DOWNLOAD_URL,
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def commands(cmd_mox: CmdMox) -> list[str]:
    """Return the shimmed commands the script ran, in order."""
    return [invocation.command for invocation in cmd_mox.journal]


def with_working_toolchain(cmd_mox: CmdMox) -> None:
    """Register a passing mold and a rustup answering for the pinned toolchain."""
    cmd_mox.stub("mold").returns(stdout=MOLD_BANNER)
    cmd_mox.stub("rustup").runs(rustup_replies())


def extract_archive(invocation: Invocation) -> tuple[str, str, int]:
    """Stand in for `tar`: unpack the `--file` archive into `--directory`.

    Done in Python because a passthrough shim would reintroduce the real
    `PATH`, and the point of the stand-in is that it, not the machine, answers.

    Returns
    -------
    tuple[str, str, int]
        Empty output and a zero exit status, in cmd-mox's handler shape.
    """
    args = invocation.args
    archive = pathlib.Path(args[args.index("--file") + 1])
    destination = pathlib.Path(args[args.index("--directory") + 1])
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            member.name = member.name.split("/", 1)[-1]
            if member.name:
                bundle.extract(member, destination, filter="data")
    return ("", "", 0)


def serve_archive(archive: bytes) -> Handler:
    """Return a curl handler that writes `archive` to its `--output` path."""

    def handler(invocation: Invocation) -> tuple[str, str, int]:
        """Write the archive where curl was told to put it."""
        output = invocation.args[invocation.args.index("--output") + 1]
        pathlib.Path(output).write_bytes(archive)
        return ("", "", 0)

    return handler


def command_result(
    *,
    stdout: str = "",
    exit_code: int = 0,
) -> CommandResult:
    """Return a stand-in command result with the chosen output and status.

    Parameters
    ----------
    stdout:
        The captured standard output the caller expects to read back.
    exit_code:
        The status the stand-in should report.

    Returns
    -------
    cuprum.sh.CommandResult
        A result carrying no argv or process identity, because nothing in
        these contracts reads either.

    Examples
    --------
    >>> command_result(exit_code=1).exit_code
    1
    """
    return CommandResult(
        program=Program("stub"),
        argv=(),
        exit_code=exit_code,
        pid=0,
        stdout=stdout,
        stderr="",
    )


class ScriptedRunner:
    r"""Answer a scripted command runner, recording what it was asked.

    The orchestration under test takes its command runner as a parameter, so a
    test substitutes this for it and then asserts the exact argument vector of
    every call. Each queued answer is consumed in order; an exception queued in
    place of a result is raised, which is how a missing executable or a failed
    `curl` is expressed.

    Examples
    --------
    >>> runner = ScriptedRunner(command_result(stdout="1.0\\n"))
    >>> runner("mold", "--version").stdout
    '1.0\\n'
    >>> runner.calls
    [('mold', ('--version',))]
    """

    def __init__(self, *answers: CommandResult | BaseException) -> None:
        """Queue one answer per expected call, in order."""
        self._answers = list(answers)
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(
        self,
        program: str,
        *args: str,
        echo: bool = False,
    ) -> CommandResult:
        """Return the next queued answer, recording the invocation."""
        self.calls.append((str(program), args))
        answer = self._answers.pop(0) if self._answers else command_result()
        if isinstance(answer, BaseException):
            raise answer
        return answer


class CurlServingRunner(ScriptedRunner):
    """Answer as `ScriptedRunner` does, writing the fixture archive for curl.

    `curl` is the one command whose effect the orchestration reads back from the
    filesystem rather than from its output, so the stand-in has to perform the
    download it was asked for before handing over the queued answer.
    """

    def __call__(
        self,
        program: str,
        *args: str,
        echo: bool = False,
    ) -> CommandResult:
        """Serve the pinned archive to curl, then answer as usual."""
        if str(program) == "curl":
            destination = pathlib.Path(args[args.index("--output") + 1])
            destination.write_bytes(mold_archive())
        return super().__call__(program, *args, echo=echo)
