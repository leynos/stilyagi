"""Contract tests for Skylos dead-code detection in Make and CI.

Skylos requires scan options before a scan path and its standalone
``whitelist`` subcommand immediately after ``skylos``. The pinned Makeutil parser
prevents whitespace or neighbouring comments hiding a command-shape regression.
"""

import json
import os
import pathlib
import shlex
import shutil
import string
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- contract tests invoke a pinned local parser.
import typing as typ
from tempfile import TemporaryDirectory

import hypothesis as hyp
import hypothesis.strategies as st

from tests.support.workflows import load_workflow

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MAKEUTIL_COMMAND: typ.Final = ("makeutil", "parse", "Makefile")
_MAKEUTIL_REVISION: typ.Final = "29fc5a1634ffbaa18a773eed9dff1b2838a45d9c"
_MAKEUTIL_TOOLCHAIN: typ.Final = "nightly-2026-05-28"
_MAKE_EXECUTABLE: typ.Final = shutil.which("make") or "make"
_SHELL_ARGUMENT_TEXT: typ.Final = st.builds(
    lambda prefix, content, suffix: prefix + content + suffix,
    st.text(alphabet=" \t", max_size=4),
    st.text(
        alphabet=string.ascii_letters + string.digits + "_$;|&'\"()[]{}*?!\\`",
        min_size=1,
        max_size=40,
    ),
    st.text(alphabet=" \t", max_size=4),
)
_MAKEUTIL_INSTALL_TOKENS: typ.Final = (
    "rustup",
    "toolchain",
    "install",
    "${MAKEUTIL_TOOLCHAIN}",
    "--profile",
    "minimal",
    "RUSTFLAGS=-Zpolonius=next",
    "cargo",
    "+${MAKEUTIL_TOOLCHAIN}",
    "install",
    "--git",
    "https://github.com/leynos/makeutil",
    "--rev",
    "${MAKEUTIL_REVISION}",
    "--locked",
    "--force",
    "makeutil",
)


def _makefile_report() -> dict[str, object]:
    """Return Makeutil's complete, successfully parsed Makefile report."""
    completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed parser command.
        _MAKEUTIL_COMMAND,
        capture_output=True,
        check=True,
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    report = typ.cast("dict[str, object]", json.loads(completed.stdout))
    parse = _mapping(report.get("parse"), subject="parse report")
    assert parse.get("status") == "complete", (
        f"makeutil did not complete the Makefile parse: {parse!r}"
    )
    return report


def _mapping(value: object, *, subject: str) -> dict[str, object]:
    """Return a JSON object, naming the unexpected `subject` on failure."""
    assert isinstance(value, dict), f"expected {subject} to be a JSON object"
    return typ.cast("dict[str, object]", value)


def _objects(value: object, *, subject: str) -> list[dict[str, object]]:
    """Return a JSON object array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    return [_mapping(item, subject=f"{subject} item") for item in value]


def _text_sequence(value: object, *, subject: str) -> tuple[str, ...]:
    """Return a JSON string array, naming the unexpected `subject` on failure."""
    assert isinstance(value, list), f"expected {subject} to be a JSON array"
    assert all(isinstance(item, str) for item in value), (
        f"expected {subject} to contain only JSON strings"
    )
    return tuple(typ.cast("list[str]", value))


def _sole_variable(name: str) -> dict[str, object]:
    """Return Makeutil's sole variable fact for `name`."""
    variables = _objects(_makefile_report().get("variables"), subject="variables")
    matches = [variable for variable in variables if variable.get("name") == name]
    assert len(matches) == 1, (
        f"expected one Makefile variable named {name!r}, found {len(matches)}"
    )
    return matches[0]


def _sole_recipe_rule(target: str) -> dict[str, object]:
    """Return the only parsed rule for `target` that has recipes."""
    rules = _objects(_makefile_report().get("rules"), subject="rules")
    matches = [
        rule
        for rule in rules
        if target in _text_sequence(rule.get("targets"), subject="rule targets")
        and _objects(rule.get("recipes"), subject="rule recipes")
    ]
    assert len(matches) == 1, (
        f"expected one recipe-bearing Makefile rule named {target!r}, found "
        f"{len(matches)}"
    )
    return matches[0]


def _variable_tokens(name: str) -> tuple[str, ...]:
    """Return shell-like tokens from Makeutil's raw variable value."""
    value = _sole_variable(name).get("raw_value")
    assert isinstance(value, str), f"expected {name!r} to have a string value"
    return tuple(shlex.split(value))


def _recipe_tokens(target: str) -> tuple[tuple[str, ...], ...]:
    """Return shell-like tokens for every recipe in `target`."""
    recipes = _objects(
        _sole_recipe_rule(target).get("recipes"), subject=f"{target} recipes"
    )
    return tuple(
        tuple(shlex.split(recipe_text))
        for recipe in recipes
        if isinstance(recipe_text := recipe.get("text"), str)
    )


def _workflow_document(workflow_path: str) -> dict[str, object]:
    """Return a repository workflow while preserving scalar strings."""
    workflow = (REPOSITORY_ROOT / workflow_path).read_text(encoding="utf-8")
    return load_workflow(workflow)


def _workflow_job(workflow_path: str, job_name: str) -> dict[str, object]:
    """Return a named job from a repository workflow."""
    workflow = _workflow_document(workflow_path)
    jobs = _mapping(workflow.get("jobs"), subject=f"{workflow_path} jobs")
    return _mapping(jobs.get(job_name), subject=f"{workflow_path} job {job_name!r}")


def _sole_workflow_step(
    workflow_path: str, job_name: str, step_name: str
) -> dict[str, object]:
    """Return the sole named workflow step from `job_name`."""
    steps = _objects(
        _workflow_job(workflow_path, job_name).get("steps"),
        subject=f"{workflow_path} job {job_name!r} steps",
    )
    matches = [step for step in steps if step.get("name") == step_name]
    assert len(matches) == 1, (
        f"expected one {step_name!r} step in {workflow_path} job {job_name!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _run_skylos_allow(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the whitelist boundary for an invalid input."""
    environment = {**os.environ, "NAME": "wsl-hostname"}
    environment.pop("REASON", None)
    environment.pop("SYMBOL", None)
    environment.update(argument.split("=", maxsplit=1) for argument in arguments)
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed Make target and arguments.
        (_MAKE_EXECUTABLE, "skylos-allow"),
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
    )


def _assert_makeutil_installation(command: object, *, contract: str) -> None:
    """Assert that `command` installs the pinned Makeutil parser."""
    assert isinstance(command, str), (
        f"{contract} must provide a Makeutil installation shell command"
    )
    assert (
        tuple(shlex.split(command.replace("\\\n", ""))) == _MAKEUTIL_INSTALL_TOKENS
    ), f"{contract} must pin the Makeutil installation command"


def test_lint_recipe_runs_the_production_dead_code_gate() -> None:
    """`make lint` must scan production code with Skylos's strict gate."""
    assert _variable_tokens("SKYLOS_VERSION") == ("4.33.2",), (
        "Skylos version contract must pin 4.33.2"
    )
    assert _variable_tokens("SKYLOS_PRODUCTION_TARGETS") == ("python/stilyagi",), (
        "Skylos production-target contract must scan python/stilyagi"
    )
    assert _variable_tokens("SKYLOS_EXCLUDE_FOLDERS") == ("tests",), (
        "Skylos exclusion contract must omit tests"
    )
    expected_skylos_command = (
        "$(SKYLOS)",
        "$(SKYLOS_PRODUCTION_TARGETS)",
        "--exclude",
        "$(SKYLOS_EXCLUDE_FOLDERS)",
        "--category",
        "dead_code",
        "--gate",
        "--format",
        "concise",
        "--no-upload",
        "--no-provenance",
        "--no-grep-verify",
    )
    skylos_commands = [c for c in _recipe_tokens("lint") if c[:1] == ("$(SKYLOS)",)]
    assert skylos_commands == [expected_skylos_command], (
        "Skylos lint command contract must scan production dead code strictly"
    )


def test_whitelist_target_uses_the_command_only_skylos_cli() -> None:
    """The whitelist command must precede its arguments and scan options."""
    expected_skylos_cli = (
        "$(UV_ENV)",
        "$(UV)",
        "tool",
        "run",
        "--python",
        "3.14",
        "--from",
        "skylos==$(SKYLOS_VERSION)",
        "skylos",
    )
    assert _variable_tokens("SKYLOS_CLI") == expected_skylos_cli, (
        "Skylos CLI contract must pin Python 3.14 and its tool release"
    )
    assert _variable_tokens("SKYLOS") == (
        "$(SKYLOS_CLI)",
        "--config-file",
        "pyproject.toml",
    ), "Skylos scan command contract must add only the configuration file"
    expected_whitelist_command = (
        "$(SKYLOS_CLI)",
        "whitelist",
        "$${SKYLOS_SYMBOL}",
        "--reason",
        "$${SKYLOS_REASON}",
    )
    whitelist_commands = [
        c for c in _recipe_tokens("skylos-allow") if c[:1] == ("$(SKYLOS_CLI)",)
    ]
    assert whitelist_commands == [expected_whitelist_command], (
        "Skylos whitelist command contract must dispatch before --reason"
    )


@hyp.settings(max_examples=25, deadline=None)
@hyp.given(value=st.text(alphabet=" \t", min_size=1, max_size=8))
def test_skylos_allow_rejects_missing_or_whitespace_values(value: str) -> None:
    """The whitelist target must reject absent and whitespace-only inputs."""
    requests = (
        ((), "SYMBOL"),
        (("SYMBOL=handler",), "REASON"),
        ((f"SYMBOL={value}", "REASON=reason"), "SYMBOL"),
        (("SYMBOL=handler", f"REASON={value}"), "REASON"),
    )
    for arguments, missing_name in requests:
        completed = _run_skylos_allow(*arguments)
        assert completed.returncode == 2, (
            f"Skylos whitelist boundary must reject {missing_name}"
        )
        assert (
            f"Error: {missing_name} is required for a named whitelist exception"
            in completed.stderr
        ), f"Skylos whitelist boundary must name the missing {missing_name}"


@hyp.settings(max_examples=25, deadline=None)
@hyp.example(symbol="$(handler);*", reason='Loaded "$plugin" | registry')
@hyp.given(symbol=_SHELL_ARGUMENT_TEXT, reason=_SHELL_ARGUMENT_TEXT)
def test_skylos_allow_forwards_generated_argument_boundaries(
    symbol: str, reason: str
) -> None:
    """Every non-empty generated value reaches Skylos as one argument."""
    with TemporaryDirectory() as temporary_directory:
        recorded_arguments = pathlib.Path(temporary_directory, "arguments.json")
        recorder = pathlib.Path(temporary_directory, "skylos-recorder")
        recorder.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n\n"
            'Path(os.environ["SKYLOS_ARGUMENTS_PATH"]).write_text(\n'
            "    json.dumps(sys.argv[1:]), encoding='utf-8'\n"
            ")\n",
            encoding="utf-8",
        )
        recorder.chmod(0o755)
        environment = {
            **os.environ,
            "SKYLOS_ARGUMENTS_PATH": str(recorded_arguments),
            "SYMBOL": symbol,
            "REASON": reason,
        }
        completed = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true] -- fixed Make target and temporary recorder.
            (
                _MAKE_EXECUTABLE,
                "--no-print-directory",
                f"SKYLOS_CLI={recorder}",
                "skylos-allow",
            ),
            capture_output=True,
            check=False,
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(recorded_arguments.read_text(encoding="utf-8")) == [
            "whitelist",
            symbol,
            "--reason",
            reason,
        ], "Skylos must receive each generated value as exactly one argument"


def test_full_suite_workflows_provision_the_pinned_makefile_parser() -> None:
    """Every full-suite CI job must pin and install Makeutil independently."""
    lint_step = _sole_workflow_step(
        ".github/workflows/smoke.yml", "lint-test", "Lint and dead-code detection"
    )
    assert lint_step.get("run") == "make lint", (
        "Smoke lint-step contract must invoke the shared make lint target"
    )
    for workflow_path, job_name in (
        (".github/workflows/smoke.yml", "lint-test"),
        (".github/workflows/coverage-main.yml", "coverage-upload"),
    ):
        environment = _mapping(
            _workflow_document(workflow_path).get("env"),
            subject=f"{workflow_path} Makeutil environment",
        )
        assert environment.get("MAKEUTIL_REVISION") == _MAKEUTIL_REVISION, (
            f"{workflow_path} Makeutil revision contract must stay pinned"
        )
        assert environment.get("MAKEUTIL_TOOLCHAIN") == _MAKEUTIL_TOOLCHAIN, (
            f"{workflow_path} Makeutil toolchain contract must stay pinned"
        )
        parser_step = _sole_workflow_step(
            workflow_path, job_name, "Install Makefile parser"
        )
        _assert_makeutil_installation(
            parser_step.get("run"),
            contract=f"{workflow_path} {job_name} Makeutil-install contract",
        )
