"""Shared subprocess environment helper for CLI end-to-end tests.

Both the stdin and end-to-end CLI tests spawn ``python -m stilyagi`` in a
temporary working directory and need the repository's ``python/`` source tree
on ``PYTHONPATH``. Centralising the environment build keeps that setup in one
place instead of duplicating it per test module.
"""

import os
import pathlib
import subprocess  # ruff: ignore[suspicious-subprocess-import] - fixed local interpreter invocation.
import sys


def run_python_module(
    cwd: pathlib.Path,
    *arguments: str,
    stdin_bytes: bytes | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[bytes]:
    """Run the local Stilyagi CLI module with bounded process input.

    Parameters
    ----------
    cwd
        Working directory used by the CLI process.
    *arguments
        CLI arguments passed after ``python -m stilyagi``.
    stdin_bytes
        Optional standard input. When absent, standard input is closed.
    timeout
        Maximum subprocess duration in seconds.

    Returns
    -------
    subprocess.CompletedProcess[bytes]
        Captured process status, standard output and standard error.

    Examples
    --------
    >>> result = run_python_module(pathlib.Path.cwd(), "--help")
    >>> result.returncode
    0
    """
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] - trusted interpreter, fixed argv, no shell.
        [sys.executable, "-m", "stilyagi", *arguments],
        cwd=cwd,
        env=python_module_environment(),
        input=stdin_bytes,
        stdin=subprocess.DEVNULL if stdin_bytes is None else None,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def python_module_environment() -> dict[str, str]:
    """Return an environment that can import the local `stilyagi` package.

    Returns
    -------
    dict[str, str]
        A copy of the current process environment with the repository's
        ``python/`` directory prepended to ``PYTHONPATH``.
    """
    python_path = pathlib.Path(__file__).resolve().parents[2] / "python"
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else str(python_path)
    )
    return env
