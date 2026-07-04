"""Direct unit tests for Makefile recipe contracts."""

import dataclasses as dc
import pathlib

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


@dc.dataclass(frozen=True)
class MakefileTargetCase:
    """Expected recipe contract for one Makefile target."""

    target: str
    expected_header_fragments: tuple[str, ...]
    expected_recipe_fragments: tuple[str, ...]
    should_include_pytest: bool


def _collect_recipe_lines(lines: list[str], start: int) -> tuple[str, ...]:
    """Return the tab-indented recipe lines immediately after position *start*."""
    recipe: list[str] = []
    for recipe_line in lines[start + 1 :]:
        if recipe_line.startswith("\t"):
            recipe.append(recipe_line.strip())
            continue
        if recipe_line:
            break
    return tuple(recipe)


def _make_target(makefile: str, target: str) -> tuple[str, tuple[str, ...]]:
    """Return a Makefile target header and its recipe lines."""
    lines = makefile.splitlines()
    for line_number, line in enumerate(lines):
        if line.startswith(f"{target}:"):
            return line, _collect_recipe_lines(lines, line_number)
    msg = f"target {target!r} not found"
    raise AssertionError(msg)


@pytest.fixture(scope="module")
def makefile_text() -> str:
    """Return the repository Makefile as text, loaded once per module."""
    return (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            MakefileTargetCase(
                target="all",
                expected_header_fragments=("## Run commit gates",),
                expected_recipe_fragments=(
                    "$(MAKE) check-fmt",
                    "$(MAKE) typecheck",
                    "$(MAKE) lint",
                    "$(MAKE) test",
                    "$(MAKE) markdownlint",
                    "$(MAKE) nixie",
                ),
                should_include_pytest=False,
            ),
            id="all",
        ),
        pytest.param(
            MakefileTargetCase(
                target="lint",
                expected_header_fragments=("tools-lint",),
                expected_recipe_fragments=(
                    "$(UV_RUN) ruff check",
                    "$(INTERROGATE) $(INTERROGATE_FLAGS) $(INTERROGATE_TARGETS)",
                    "$(PYLINT) $(PYLINT_TARGETS)",
                    (
                        'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" '
                        "$(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)"
                    ),
                    "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)",
                    (
                        'RUSTFLAGS="$(RUST_FLAGS)" '
                        "$(CARGO_BUILD_ENV) whitaker --all -- $(CARGO_FLAGS)"
                    ),
                ),
                should_include_pytest=False,
            ),
            id="lint",
        ),
        pytest.param(
            MakefileTargetCase(
                target="typecheck",
                expected_header_fragments=("build", "tools-check"),
                expected_recipe_fragments=(
                    (
                        'RUSTFLAGS="$(RUST_FLAGS)" '
                        "$(CARGO_BUILD_ENV) $(CARGO) check $(CARGO_FLAGS)"
                    ),
                    "$(UV_RUN) ty --version",
                    "$(UV_RUN) ty check",
                ),
                should_include_pytest=False,
            ),
            id="typecheck",
        ),
        pytest.param(
            MakefileTargetCase(
                target="test",
                expected_header_fragments=("build", "tools-lint"),
                expected_recipe_fragments=(
                    (
                        "$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) "
                        "--all -- --check"
                    ),
                    "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)",
                    "nextest run --profile default --no-tests pass",
                    "cargo-nextest not installed, falling back to cargo test",
                    "$(CARGO) test $(TEST_FLAGS) $(BUILD_JOBS)",
                    "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)",
                    '"$$VENV_PYTHON" -m pytest -v',
                ),
                should_include_pytest=True,
            ),
            id="test",
        ),
        pytest.param(
            MakefileTargetCase(
                target="test-ci",
                expected_header_fragments=("build", "tools-lint"),
                expected_recipe_fragments=(
                    "nextest run --profile ci --no-tests pass",
                    "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)",
                ),
                should_include_pytest=False,
            ),
            id="test-ci",
        ),
    ],
)
def test_makefile_targets_run_expected_recipes(
    makefile_text: str,
    case: MakefileTargetCase,
) -> None:
    """Makefile targets must keep their reviewed recipe contracts."""
    header, recipe = _make_target(makefile_text, case.target)
    joined_recipe = "\n".join(recipe)

    for expected_header_fragment in case.expected_header_fragments:
        assert expected_header_fragment in header
    for expected_recipe_fragment in case.expected_recipe_fragments:
        assert expected_recipe_fragment in joined_recipe
    if case.should_include_pytest:
        assert '"$$VENV_PYTHON" -m pytest -v' in recipe
    else:
        assert "pytest" not in joined_recipe
