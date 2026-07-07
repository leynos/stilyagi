"""Shared subprocess environment helper for CLI end-to-end tests.

Both the stdin and end-to-end CLI tests spawn ``python -m stilyagi`` in a
temporary working directory and need the repository's ``python/`` source tree
on ``PYTHONPATH``. Centralising the environment build keeps that setup in one
place instead of duplicating it per test module.
"""

import os
import pathlib


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
