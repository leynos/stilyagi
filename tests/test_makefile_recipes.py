"""Direct unit tests for Makefile recipe contracts."""

import pathlib

import pytest

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


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


def test_makefile_lint_target_runs_expected_recipe(makefile_text: str) -> None:
    """Lint must run Python and Rust lint tiers in the Makefile recipe."""
    header, recipe = _make_target(makefile_text, "lint")

    assert "tools-lint" in header
    assert "$(UV_RUN) ruff check" in recipe
    assert "$(PYLINT) $(PYLINT_TARGETS)" in recipe
    assert (
        'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)'
        in recipe
    )
    assert "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)" in recipe
    assert (
        'RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) whitaker --all -- $(CARGO_FLAGS)'
        in recipe
    )


def test_makefile_typecheck_target_runs_expected_recipe(makefile_text: str) -> None:
    """Typecheck must build first, then run Rust and Python type checks."""
    header, recipe = _make_target(makefile_text, "typecheck")

    assert "build" in header
    assert "tools-check" in header
    assert (
        'RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) check $(CARGO_FLAGS)'
        in recipe
    )
    assert "$(UV_RUN) ty --version" in recipe
    assert "$(UV_RUN) ty check" in recipe


def test_makefile_test_target_runs_expected_recipe(makefile_text: str) -> None:
    """Test must run formatting, lint-adjacent checks, Rust tests, and pytest."""
    header, recipe = _make_target(makefile_text, "test")
    joined_recipe = "\n".join(recipe)

    assert "build" in header
    assert "tools-lint" in header
    assert (
        "$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check" in recipe
    )
    assert "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)" in recipe
    assert "nextest run --profile default --no-tests pass" in joined_recipe
    assert "cargo-nextest not installed, falling back to cargo test" in joined_recipe
    assert "$(CARGO) test $(TEST_FLAGS) $(BUILD_JOBS)" in joined_recipe
    assert "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)" in joined_recipe
    assert '"$$VENV_PYTHON" -m pytest -v' in recipe


def test_makefile_test_ci_target_runs_expected_recipe(makefile_text: str) -> None:
    """CI test must use the CI nextest profile and Rust doc tests."""
    header, recipe = _make_target(makefile_text, "test-ci")
    joined_recipe = "\n".join(recipe)

    assert "build" in header
    assert "tools-lint" in header
    assert "nextest run --profile ci --no-tests pass" in joined_recipe
    assert "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)" in joined_recipe
    assert "pytest" not in joined_recipe
