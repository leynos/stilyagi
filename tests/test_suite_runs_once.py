"""Contracts that each event runs the test suites once, under coverage.

`make test` runs the format check, Clippy, nextest over the workspace with
``--all-features``, the Rust doctests, pytest, and the Python doctests. The
smoke workflow used to run it on every pull request and push, beside a
coverage run of the same suites: the smoke workflow's coverage step on a pull
request, and ``coverage-main.yml`` on a push. The format check and Clippy
already run as `make check-fmt` and `make lint` in the same job. Only the two
doctest runs were unique, so CI now runs `make test-doc` instead.

These tests hold the premises of that split:

- the smoke workflow runs `make test-doc`, unconditionally, in `lint-test`,
  and no command that repeats a suite coverage already runs;
- `test-doc` runs the two doctest commands and nothing else, and depends on
  `build` alone, since any other prerequisite would run first;
- both coverage steps run nextest with the doctests left off, so `test-doc`
  is not itself a repeat;
- no crate declares a feature, explicitly or through an optional
  dependency, which is what makes `make test`'s ``--all-features`` the same
  selection as the coverage run's default. A crate that gains features
  reopens that question, so this fails first.
"""

import pathlib
import re
import tomllib
import typing as typ

import pytest

from tests.support.assertions import assert_with_context
from tests.support.workflows import load_workflow, workflow_jobs, workflow_steps

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY_ROOT / ".github" / "workflows"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage@"
DOCTEST_COMMAND = "make test-doc"
#: A command that runs a suite the coverage step already runs.
#: Variable assignments and options may precede the target (`make -j2 test`).
REPEATED_SUITE = re.compile(
    r"\bmake\s+((?:\S+=\S+|-\S+)\s+)*test(-ci|-quick)?(?![-\w])"
    r"|\bnextest\s+run\b|\bcargo\s+test\b|\bpytest\b"
)
TEST_DOC_RECIPE = [
    (
        'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" '
        "$(CARGO_BUILD_ENV) $(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)"
    ),
    "$(RESOLVE_VENV_PYTHON); \\",
    '"$$VENV_PYTHON" -m pytest -v --doctest-modules $(PY_DOCTEST_PATHS)',
]


def _steps(workflow: str) -> list[dict[str, object]]:
    """Return every step of one repository workflow."""
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    return workflow_steps(load_workflow(text))


def _recipe(target: str) -> list[str]:
    """Return one Makefile target's recipe lines, without their tab."""
    lines = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"{target}:")]
    assert_with_context(len(starts) == 1, f"expected one {target} target")
    recipe = []
    for line in lines[starts[0] + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line[1:])
    return recipe


def _job_steps(workflow: str, job: str) -> list[dict[str, object]]:
    """Return the steps of one job in one repository workflow."""
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    jobs = workflow_jobs(load_workflow(text))
    steps = jobs[job].get("steps")
    assert_with_context(isinstance(steps, list), f"expected steps in {job}")
    return [step for step in typ.cast("list[object]", steps) if isinstance(step, dict)]


def _prerequisites(target: str) -> list[str]:
    """Return one Makefile target's prerequisites, in order."""
    lines = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    headers = [line for line in lines if line.startswith(f"{target}:")]
    assert_with_context(len(headers) == 1, f"expected one {target} target")
    return headers[0].removeprefix(f"{target}:").split("##")[0].split()


def test_smoke_runs_the_doctests_and_no_repeated_suite() -> None:
    """Require `make test-doc`, unguarded, and refuse every repeated suite."""
    steps = _steps("smoke.yml")
    repeated = [
        command
        for command in (str(step.get("run", "")).strip() for step in steps)
        if command != DOCTEST_COMMAND and REPEATED_SUITE.search(command)
    ]
    assert_with_context(not repeated, f"smoke.yml repeats a suite: {repeated!r}")

    doctest_steps = [
        step
        for step in _job_steps("smoke.yml", "lint-test")
        if step.get("run") == DOCTEST_COMMAND
    ]
    assert_with_context(
        len(doctest_steps) == 1, "expected one `make test-doc` step in lint-test"
    )
    assert_with_context(
        "if" not in doctest_steps[0], "the doctest step must run on every event"
    )


def test_test_doc_runs_only_the_doctests() -> None:
    """Hold the recipe to the two doctest commands, and `build` as its one prerequisite.

    A prerequisite runs before the recipe, so `test` or `test-ci` there would
    bring the whole suite back without changing a recipe line.
    """
    assert_with_context(
        _recipe("test-doc") == TEST_DOC_RECIPE,
        "test-doc must run the Rust and Python doctests and nothing else",
    )
    assert_with_context(
        _prerequisites("test-doc") == ["build"],
        f"test-doc may depend only on build, got {_prerequisites('test-doc')}",
    )


def test_coverage_runs_nextest_without_the_doctests() -> None:
    """Keep both coverage steps on nextest, with the doctests left to CI."""
    coverage_steps = [
        (workflow, step)
        for workflow in ("smoke.yml", "coverage-main.yml")
        for step in _steps(workflow)
        if str(step.get("uses", "")).startswith(COVERAGE_ACTION)
    ]
    assert_with_context(
        len(coverage_steps) == 2, f"expected two coverage steps: {coverage_steps!r}"
    )
    for workflow, step in coverage_steps:
        inputs = step.get("with")
        assert_with_context(isinstance(inputs, dict), f"{workflow}: expected inputs")
        inputs = typ.cast("dict[str, object]", inputs)
        assert_with_context(
            inputs.get("use-cargo-nextest") == "true",
            f"{workflow}: coverage must run nextest",
        )
        assert_with_context(
            inputs.get("doctests", "false") == "false",
            f"{workflow}: coverage running doctests would repeat make test-doc",
        )


DEPENDENCY_TABLES = ("dependencies", "dev-dependencies", "build-dependencies")


def _optional_dependencies(manifest: dict[str, object]) -> list[str]:
    """Return the optional dependencies a manifest declares, target tables included.

    Cargo turns each optional dependency into an implicit feature, so a
    crate with one has features even without a `[features]` table.

    Returns
    -------
    list[str]
        The names of the optional dependencies, in table order.
    """
    tables = [manifest.get(name) for name in DEPENDENCY_TABLES]
    targets = manifest.get("target")
    if isinstance(targets, dict):
        tables.extend(
            platform.get(name)
            for platform in targets.values()
            if isinstance(platform, dict)
            for name in DEPENDENCY_TABLES
        )
    return [
        name
        for table in tables
        if isinstance(table, dict)
        for name, spec in table.items()
        if isinstance(spec, dict) and spec.get("optional") is True
    ]


def _declares_features(manifest: dict[str, object]) -> bool:
    """Report whether a manifest has explicit or implicit features."""
    return bool(manifest.get("features")) or bool(_optional_dependencies(manifest))


def test_no_crate_declares_features() -> None:
    """Refuse any feature, which would split all-features from default."""
    root = REPOSITORY_ROOT / "Cargo.toml"
    members = tomllib.loads(root.read_text(encoding="utf-8"))["workspace"]["members"]
    manifests = [root] + [
        manifest
        for pattern in members
        for manifest in REPOSITORY_ROOT.glob(f"{pattern}/Cargo.toml")
    ]
    assert_with_context(len(manifests) > 1, "expected workspace member manifests")
    with_features = [
        str(path.relative_to(REPOSITORY_ROOT))
        for path in manifests
        if _declares_features(tomllib.loads(path.read_text(encoding="utf-8")))
    ]
    assert_with_context(
        not with_features,
        f"{with_features} declare features; recheck make test against coverage",
    )


def test_an_optional_dependency_counts_as_a_feature() -> None:
    """Treat optional dependencies, in any dependency table, as features."""
    optional = {"optional": True, "version": "1"}
    manifests = [
        {"dependencies": {"serde": optional}},
        {"dev-dependencies": {"serde": optional}},
        {"target": {"cfg(unix)": {"dependencies": {"libc": optional}}}},
        {"features": {"extra": []}},
    ]
    assert_with_context(
        all(_declares_features(manifest) for manifest in manifests),
        "expected every optional dependency and feature table to count",
    )
    assert_with_context(
        not _declares_features({"dependencies": {"serde": {"version": "1"}}}),
        "a required dependency is not a feature",
    )


@pytest.mark.parametrize(
    ("command", "repeats"),
    [
        ("make test", True),
        ("make -j2 test", True),
        ("make test-ci", True),
        ("make TEST_FLAGS=--lib test-quick", True),
        ("uv run pytest -q", True),
        ("make test-doc", False),
        ("make test-workflow-contracts", False),
    ],
)
def test_the_repeated_suite_pattern(command: str, *, repeats: bool) -> None:
    """Recognize every spelling of a repeated suite, and nothing longer."""
    assert_with_context(
        bool(REPEATED_SUITE.search(command)) is repeats, f"misread {command!r}"
    )
