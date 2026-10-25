"""Process-boundary acceptance for Markdown inspection and cache commands.

The scenarios live in ``features/markdown_cli_inspection.feature`` and invoke
the package through its Python module entry point in disposable projects.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_markdown_cli_inspection_bdd.py
"""

from pytest_bdd import scenarios

pytest_plugins = (
    "tests.steps.markdown_cli_inspection",
    "tests.steps.markdown_cli_cleanup",
)

scenarios("../features/markdown_cli_inspection.feature")
