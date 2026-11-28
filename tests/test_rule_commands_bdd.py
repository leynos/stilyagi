"""Process-boundary acceptance for builtin rule discovery.

The scenarios live in ``features/rule_discovery.feature``. They run the
package's module entrypoint in disposable projects, including one whose
discovered configuration cannot be parsed, and execute the documented TERM001
example through ``check``.

Run them with:

    make test

or, for this module alone:

    .venv/bin/python -m pytest tests/test_rule_commands_bdd.py
"""

from pytest_bdd import scenarios

pytest_plugins = ("tests.steps.rule_discovery",)

scenarios("../features/rule_discovery.feature")
