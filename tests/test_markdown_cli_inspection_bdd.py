"""Process-boundary acceptance for Markdown inspection and cache commands.

The scenarios live in ``features/markdown_cli_inspection.feature``. Most of
them invoke the package through its Python module entry point in disposable
projects, which is what proves the installed command line works end to end.

The frontmatter repair scenario is the exception: it calls `cli.run_check`
in-process over a prepared component file. That boundary is deliberate. The
scenario's subject is that a real mutating run rewrites the body and leaves the
metadata bytes alone, and calling the entry point in-process keeps the
diagnostics and the repaired bytes observable in the test rather than
recovered from a child process's exit status and files.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_markdown_cli_inspection_bdd.py
"""

from pytest_bdd import scenarios

pytest_plugins = (
    "tests.steps.markdown_cli_inspection",
    "tests.steps.markdown_cli_cleanup",
    "tests.steps.markdown_frontmatter_repair",
)

scenarios("../features/markdown_cli_inspection.feature")
