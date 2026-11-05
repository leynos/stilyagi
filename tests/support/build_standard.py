"""Readings for the development build standard's contracts.

Three subjects live here, because every contract about the standard needs
them and none should re-derive them: the Cargo configuration's `rustflags`
sources, the Cargo and maturin invocations Make evaluates for a target, and
a hermetic way to run a target against recording stand-ins so the flags a
compiler would receive are observed rather than read.

Reading Make's text proves what a recipe says. The recording runs prove what
the shell hands the tool, including how an ambient `RUSTFLAGS` (CI exports
one) interacts with a recipe's own assignment, which no amount of reading the
Makefile shows.
"""

import dataclasses as dc
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess  # ruff: ignore[suspicious-subprocess-import] - runs the pinned `make` over probe tools only.
import tomllib
import typing as typ

from tests.support.errors import ReadingError

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPOSITORY_ROOT: typ.Final = pathlib.Path(__file__).resolve().parents[2]
CARGO_CONFIG: typ.Final = REPOSITORY_ROOT / ".cargo" / "config.toml"
TOOLCHAIN_FILE: typ.Final = REPOSITORY_ROOT / "rust-toolchain.toml"

THREADS_FLAG: typ.Final = "-Zthreads=8"
MOLD_FLAG: typ.Final = "-Clink-arg=-fuse-ld=mold"
LINUX_TARGET: typ.Final = 'cfg(target_os = "linux")'

#: The probe executables standing in for the tools a recipe names.
PROBE_CARGO: typ.Final = "probe-cargo"
PROBE_WHITAKER: typ.Final = "probe-whitaker"
PROBE_UV: typ.Final = "probe-uv"
PROBE_CHECK: typ.Final = "probe-check-build-tools"
PROBE_PYTHON: typ.Final = "probe-python"
PROBE_NAMES: typ.Final = (
    PROBE_CARGO,
    PROBE_WHITAKER,
    PROBE_UV,
    PROBE_CHECK,
    PROBE_PYTHON,
    "probe-ty",
    "probe-mdlint",
    "probe-nixie",
    "probe-mdtablefix",
    "probe-cargo-binstall",
)

#: Overrides that point every tool a recipe runs at a probe.
MAKE_OVERRIDES: typ.Final = (
    f"CARGO={PROBE_CARGO}",
    f"WHITAKER={PROBE_WHITAKER}",
    f"UV={PROBE_UV}",
    f"CHECK_BUILD_TOOLS={PROBE_CHECK}",
    f"RESOLVE_VENV_PYTHON=VENV_PYTHON={PROBE_PYTHON}",
    "TY=probe-ty",
    "MDLINT=probe-mdlint",
    "NIXIE=probe-nixie",
    "MDTABLEFIX=probe-mdtablefix",
    "CARGO_BINSTALL=probe-cargo-binstall",
)

_SEGMENT_BOUNDARY: typ.Final = re.compile(
    r"\s*(?:;|&&|\|\||\bthen\b|\belse\b|\bfi\b|\bif\b)\s*"
)
_ENV_ASSIGNMENT: typ.Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def read_toml(path: pathlib.Path) -> dict[str, object]:
    """Return a TOML file's parsed document."""
    return tomllib.loads(path.read_text(encoding="utf-8"))


def rustflag_sources(config: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Return every `rustflags` source a Cargo configuration declares.

    Parameters
    ----------
    config
        A parsed `.cargo/config.toml`.

    Returns
    -------
    dict
        Source name (`build`, or the `[target.<spec>]` key) to its flags.
        A source that names no `rustflags` is absent.
    """
    sources: dict[str, tuple[str, ...]] = {}
    build = config.get("build")
    if isinstance(build, dict) and "rustflags" in build:
        sources["build"] = tuple(build["rustflags"])
    targets = config.get("target")
    if isinstance(targets, dict):
        for spec, table in targets.items():
            if isinstance(table, dict) and "rustflags" in table:
                sources[str(spec)] = tuple(table["rustflags"])
    return sources


@dc.dataclass(frozen=True, slots=True)
class ToolInvocation:
    """One tool invocation read from, or recorded by, a Make target.

    `env` holds the variable assignments that prefix the command in the
    recipe text, or the compiler-relevant variables a recording observed.
    """

    program: str
    args: tuple[str, ...]
    env: dict[str, str | None] = dc.field(default_factory=dict)

    @property
    def rustflags(self) -> str | None:
        """The `RUSTFLAGS` value, or None when it is not assigned."""
        return self.env.get("RUSTFLAGS")

    def has_args(self, *prefix: str) -> bool:
        """Return whether the arguments begin with `prefix`."""
        return self.args[: len(prefix)] == prefix

    def contains_arg(self, arg: str) -> bool:
        """Return whether `arg` appears anywhere in the arguments."""
        return arg in self.args


def _recipe_text(dry_run_output: str) -> str:
    """Return a dry run's output without comments or continuation lines."""
    lines = [
        line
        for line in dry_run_output.replace("\\\n", " ").splitlines()
        if not line.lstrip().startswith(("#", "make["))
    ]
    return "\n".join(lines)


def _segment_invocation(segment: str) -> ToolInvocation | None:
    """Return the invocation a shell segment makes, or None for no command."""
    try:
        words = shlex.split(segment)
    except ValueError:
        return None
    env: dict[str, str | None] = {}
    while words and _ENV_ASSIGNMENT.match(words[0]):
        name, _, value = words.pop(0).partition("=")
        env[name] = value
    # Redirections are not arguments, and `2>&1` would otherwise leak into one.
    words = [word for word in words if not re.match(r"^\d*>", word)]
    if not words:
        return None
    return ToolInvocation(program=words[0], args=tuple(words[1:]), env=env)


def read_invocations(
    dry_run_output: str, programs: cabc.Iterable[str]
) -> list[ToolInvocation]:
    """Return every invocation of `programs` in a dry run, conditionals included.

    A recipe line such as `if probe-cargo nextest --version; then X; else Y; fi`
    carries two routes in one line. Splitting on shell control words, rather
    than reading line by line, returns both branches, so a branch that dropped
    the standard cannot hide behind the one a probe happened to take.

    Parameters
    ----------
    dry_run_output
        The text `make --dry-run` printed.
    programs
        The program names whose invocations are wanted.

    Returns
    -------
    list[ToolInvocation]
        The invocations in text order.
    """
    wanted = frozenset(programs)
    found: list[ToolInvocation] = []
    for line in _recipe_text(dry_run_output).splitlines():
        for segment in _SEGMENT_BOUNDARY.split(line):
            invocation = _segment_invocation(segment)
            if invocation is not None and invocation.program in wanted:
                found.append(invocation)
    return found


def make_available_tools(directory: pathlib.Path) -> pathlib.Path:
    """Create empty executables for every probe name, for `command -v`.

    Make's `ensure_tool` checks the injected tool exists at parse time, even
    under `--dry-run`, so a probe name must resolve on `PATH`.

    Returns
    -------
    pathlib.Path
        `directory`, now holding the executables.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name in PROBE_NAMES:
        path = directory / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return directory


def _make_executable() -> str:
    """Return the path of `make`, or raise when it is not installed."""
    make = shutil.which("make")
    if make is None:
        message = "make is required to evaluate the Makefile's routes"
        raise ReadingError(message, reader="build_standard")
    return make


def run_make(
    arguments: list[str], env: dict[str, str], cwd: pathlib.Path
) -> subprocess.CompletedProcess[str]:
    """Run `make` with `arguments` and return its completed process."""
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - fixed argv: the pinned `make` over probe tools.
        [_make_executable(), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def dry_run(
    target: str,
    tools: pathlib.Path,
    *extra: str,
    env: dict[str, str | None] | None = None,
) -> str:
    """Return `make --dry-run --always-make <target>` output with probe tools.

    `--always-make` evaluates every file target as out of date, so the result
    does not depend on whether a `.venv` exists on the machine running it.

    Parameters
    ----------
    target
        The Make target to evaluate.
    tools
        A directory of probe executables, from `make_available_tools`.
    *extra
        Further Make arguments, such as a command-line variable assignment.
    env
        Variables to set in the child environment; a `None` value removes the
        inherited one. This is how a route reads an environment override,
        which `?=` honours but a command-line assignment would not exercise,
        and how a test neutralizes an ambient value it does not want to test.

    Returns
    -------
    str
        What Make printed it would run.

    Raises
    ------
    ReadingError
        If Make exits non-zero, carrying its stderr.
    """
    inherited: dict[str, str] = {
        **os.environ,
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
    }
    overrides: dict[str, str | None] = env if env is not None else {}
    for name, value in overrides.items():
        if value is None:
            inherited.pop(name, None)
        else:
            inherited[name] = value
    result = run_make(
        [
            "--no-print-directory",
            "--dry-run",
            "--always-make",
            *MAKE_OVERRIDES,
            *extra,
            target,
        ],
        inherited,
        REPOSITORY_ROOT,
    )
    if result.returncode != 0:
        raise ReadingError(result.stderr, reader="dry_run", path=target)
    return result.stdout


_COMPILING_CARGO_SUBCOMMANDS: typ.Final = frozenset({
    "build",
    "check",
    "clippy",
    "doc",
    "nextest",
    "rustc",
    "test",
})


def compiles(invocation: ToolInvocation) -> bool:
    """Return whether an invocation can reach rustc and so needs a flag policy.

    `cargo fmt`, `cargo clean` and `cargo nextest --version` do not compile;
    every other Cargo subcommand that builds, Whitaker, `maturin` and the
    `uv sync` that installs the project through maturin do.

    Returns
    -------
    bool
        True when the invocation needs a flag policy.
    """
    if invocation.program == PROBE_WHITAKER:
        return True
    if invocation.program == PROBE_UV:
        return "maturin" in invocation.args or invocation.has_args("sync")
    if invocation.program != PROBE_CARGO or not invocation.args:
        return False
    if invocation.has_args("nextest", "--version"):
        return False
    return invocation.args[0] in _COMPILING_CARGO_SUBCOMMANDS
