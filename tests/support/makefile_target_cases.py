"""Expected recipe contracts for the Makefile targets the suite pins.

The table is data, not logic: each case names a target, the header and recipe
fragments its recipe must keep, and whether the pytest suite takes part. It
lives beside the other shared fixtures rather than inside the test module
because the table is longer than the code that consumes it, and because any
future reader of the same contract should read one table rather than a copy.
"""

import dataclasses as dc
import typing as typ


@dc.dataclass(frozen=True, slots=True)
class MakefileTargetCase:
    """Expected recipe contract for one Makefile target."""

    target: str
    expected_header_fragments: tuple[str, ...]
    expected_recipe_fragments: tuple[str, ...]
    should_include_pytest: bool


#: One entry per reviewed target, keyed by the target each case names.
MAKEFILE_TARGET_CASES: typ.Final[tuple[MakefileTargetCase, ...]] = (
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
    MakefileTargetCase(
        target="lint-clippy",
        expected_header_fragments=("check-build-tools", "tools-lint"),
        expected_recipe_fragments=(
            "$(RUFF) check",
            "$(INTERROGATE) $(INTERROGATE_FLAGS) $(INTERROGATE_TARGETS)",
            "$(PYLINT) $(PYLINT_TARGETS)",
            "$(DF12_PYLINT) $(PYLINT_TARGETS)",
            "$(AMBRLEAKS) $(AMBRLEAKS_TARGETS)",
            (
                'RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" '
                "$(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)"
            ),
            (
                'RUSTFLAGS="$(RUST_FLAGS)" '
                "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)"
            ),
        ),
        should_include_pytest=False,
    ),
    MakefileTargetCase(
        target="lint-whitaker",
        expected_header_fragments=("lint-clippy",),
        expected_recipe_fragments=(
            (
                'RUSTFLAGS="$(WHITAKER_RUST_FLAGS)" '
                "$(CARGO_BUILD_ENV) $(WHITAKER) $(WHITAKER_LIBRARIES) "
                "-- $(CARGO_FLAGS)"
            ),
        ),
        should_include_pytest=False,
    ),
    MakefileTargetCase(
        target="typecheck",
        expected_header_fragments=("check-build-tools", "build", "tools-check"),
        expected_recipe_fragments=(
            (
                'RUSTFLAGS="$(RUST_FLAGS)" '
                "$(CARGO_BUILD_ENV) $(CARGO) check $(CARGO_FLAGS)"
            ),
            "$(TY) --version",
            "$(TY) check --python .venv",
        ),
        should_include_pytest=False,
    ),
    MakefileTargetCase(
        target="test",
        expected_header_fragments=(
            "check-build-tools",
            "build",
            "tools-lint",
        ),
        expected_recipe_fragments=(
            ("$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check"),
            (
                'RUSTFLAGS="$(RUST_FLAGS)" '
                "$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)"
            ),
            "nextest run --profile default --no-tests pass",
            "cargo-nextest not installed, falling back to cargo test",
            "$(CARGO) test $(TEST_FLAGS) $(BUILD_JOBS)",
            "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)",
            '"$$VENV_PYTHON" -m pytest -v',
        ),
        should_include_pytest=True,
    ),
    MakefileTargetCase(
        target="test-ci",
        expected_header_fragments=("check-build-tools", "build", "tools-lint"),
        expected_recipe_fragments=(
            "nextest run --profile ci --no-tests pass",
            "$(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)",
        ),
        should_include_pytest=False,
    ),
)
