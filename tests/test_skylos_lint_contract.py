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
import subprocess  # noqa: S404 -- contract tests invoke a pinned local parser.
import tomllib
import typing as typ

import hypothesis as hyp
import hypothesis.strategies as st

from tests.support.workflows import load_workflow

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
_MAKEUTIL_COMMAND: typ.Final = ("makeutil", "parse", "Makefile")
_MAKEUTIL_REVISION: typ.Final = "29fc5a1634ffbaa18a773eed9dff1b2838a45d9c"
_MAKEUTIL_TOOLCHAIN: typ.Final = "nightly-2026-05-28"
_REQUIRED_SKYLOS_WHITELIST_NAMES: typ.Final = frozenset((
    "InvalidSpacyModelError",
    "_coerce_path",
    "_coerce_string_to_string_tuple_map",
    "_copy_mapping",
    "_require_strict_int",
    "reset_extraction_state_for_tests",
    "extract_document",
))
_SHELL_ARGUMENT_TEXT: typ.Final = st.text(
    alphabet=string.ascii_letters + string.digits + " _$;|&'\"()[]{}*?!\\",
    max_size=48,
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
    completed = subprocess.run(  # noqa: S603 -- fixed parser command.
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


def _run_skylos_allow(
    *arguments: str, dry_run: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run the whitelist boundary without invoking Skylos on valid input."""
    environment = {**os.environ, "NAME": "wsl-hostname"}
    environment.pop("REASON", None)
    environment.pop("SYMBOL", None)
    environment.update(argument.split("=", maxsplit=1) for argument in arguments)
    dry_run_option = ("--dry-run",) if dry_run else ()
    return subprocess.run(  # noqa: S603 -- fixed Make target and arguments.
        (_make_executable(), *dry_run_option, "skylos-allow"),
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
    )


def _make_executable() -> str:
    """Return the resolved Make executable required by the contract tests."""
    executable = shutil.which("make")
    assert executable is not None, "Skylos contract tests require make on PATH"
    return executable


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


def test_skylos_configuration_requires_strict_documented_exceptions() -> None:
    """Skylos must enable strict mode and explain each named exception."""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as configuration_file:
        configuration = tomllib.load(configuration_file)
    tool = _mapping(configuration.get("tool"), subject="tool configuration")
    skylos = _mapping(tool.get("skylos"), subject="Skylos configuration")
    gate = _mapping(skylos.get("gate"), subject="Skylos gate configuration")
    assert gate.get("strict") is True, (
        "Skylos gate configuration must enable strict mode"
    )
    whitelist = _mapping(skylos.get("whitelist"), subject="Skylos whitelist")
    names = _text_sequence(whitelist.get("names"), subject="Skylos whitelist names")
    documented = _mapping(
        whitelist.get("documented"), subject="Skylos documented whitelist"
    )
    assert set(names) == _REQUIRED_SKYLOS_WHITELIST_NAMES, (
        "Skylos must retain the verified non-empty allow list"
    )
    assert set(documented) == _REQUIRED_SKYLOS_WHITELIST_NAMES, (
        "Skylos must document every verified allow-list exception"
    )
    assert all(isinstance(reason, str) and reason for reason in documented.values()), (
        "Skylos documented whitelist reasons must be non-empty strings"
    )


def test_skylos_allow_requires_symbol_without_accepting_wsl_name() -> None:
    """The whitelist target must reject a missing symbol despite `NAME`."""
    completed = _run_skylos_allow()
    assert completed.returncode == 2, (
        "Skylos whitelist boundary must reject a missing SYMBOL argument"
    )
    assert (
        "Error: SYMBOL is required for a named whitelist exception" in completed.stderr
    ), "Skylos whitelist boundary must name the missing SYMBOL argument"


def test_skylos_allow_requires_reason() -> None:
    """The whitelist target must reject a missing rationale without scanning."""
    completed = _run_skylos_allow("SYMBOL=handler")
    assert completed.returncode == 2, (
        "Skylos whitelist boundary must reject a missing REASON argument"
    )
    assert (
        "Error: REASON is required for a named whitelist exception" in completed.stderr
    ), "Skylos whitelist boundary must name the missing REASON argument"


def test_skylos_allow_dry_run_preserves_whitelist_argument_order() -> None:
    """A complete dry run must reveal the command without writing an entry."""
    completed = _run_skylos_allow(
        "SYMBOL=handler",
        "REASON=Loaded by plugin registry",
        dry_run=True,
    )
    assert completed.returncode == 0, (
        "Skylos whitelist dry-run contract must accept complete input"
    )
    assert (
        'skylos whitelist "${SKYLOS_SYMBOL}" --reason "${SKYLOS_REASON}"'
        in completed.stdout
    ), "Skylos whitelist dry-run contract must preserve subcommand argument order"


@hyp.settings(deadline=None)
@hyp.example(symbol="$(handler);*", reason='Loaded "$plugin" | registry')
@hyp.given(symbol=_SHELL_ARGUMENT_TEXT, reason=_SHELL_ARGUMENT_TEXT)
def test_skylos_allow_validates_argument_boundaries(symbol: str, reason: str) -> None:
    """Validate missing values and preserve shell-significant argument boundaries."""
    has_symbol, has_reason = bool(symbol.strip()), bool(reason.strip())
    completed = _run_skylos_allow(
        f"SYMBOL={symbol}", f"REASON={reason}", dry_run=has_symbol and has_reason
    )
    if not has_symbol:
        assert completed.returncode == 2, "A missing SYMBOL must fail with exit 2"
        assert "Error: SYMBOL is required" in completed.stderr, (
            "A missing SYMBOL must report its validation error"
        )
    elif not has_reason:
        assert completed.returncode == 2, "A missing REASON must fail with exit 2"
        assert "Error: REASON is required" in completed.stderr, (
            "A missing REASON must report its validation error"
        )
    else:
        assert completed.returncode == 0, (
            "A complete whitelist request must support a non-mutating dry run"
        )
        assert completed.stdout.count("skylos whitelist") == 1, (
            "A dry run must emit exactly one Skylos whitelist command"
        )
        assert (
            'skylos whitelist "${SKYLOS_SYMBOL}" --reason "${SKYLOS_REASON}"'
            in completed.stdout
        ), "The Skylos subcommand must precede --reason without shell interpolation"


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
