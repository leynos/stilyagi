MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
MDFORMAT_ALL ?= mdformat-all
CARGO ?= cargo
export PATH := $(HOME)/.cargo/bin:$(HOME)/.local/bin:$(HOME)/.bun/bin:$(PATH)
WORKSPACE_MANIFEST ?= Cargo.toml
PYEXT_MANIFEST ?= crates/stilyagi-pyext/Cargo.toml
BUILD_JOBS ?=
RUST_FLAGS ?=
RUST_FLAGS := -D warnings $(RUST_FLAGS)
RUSTDOC_FLAGS ?=
RUSTDOC_FLAGS := -D warnings $(RUSTDOC_FLAGS)
CARGO_FLAGS ?= --manifest-path $(WORKSPACE_MANIFEST) --workspace --all-targets --all-features
CLIPPY_FLAGS ?= $(CARGO_FLAGS) -- $(RUST_FLAGS)
DOC_FLAGS ?= --manifest-path $(WORKSPACE_MANIFEST) --workspace --all-features --no-deps
UV ?= $(shell command -v uv 2>/dev/null || printf '%s/.local/bin/uv' "$$HOME")
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools
UV_RUN = $(UV_ENV) $(UV) run --group dev
PYLINT_PYTHON ?= pypy
PYLINT_TARGETS ?= python/stilyagi tests
PYLINT_PYPY_SHIM_REF ?= 726d09f968b4d729ee4b29c71fc732e744854f3b
PYLINT_PYPY_SHIM = git+https://github.com/leynos/pylint-pypy-shim.git@$(PYLINT_PYPY_SHIM_REF)
PYLINT = $(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) --from '$(PYLINT_PYPY_SHIM)' pylint-pypy
INTERROGATE ?= interrogate
INTERROGATE_TARGETS ?= python/stilyagi tests
INTERROGATE_FLAGS ?= --fail-under 100
CARGO_BUILD_ENV ?= PYO3_USE_ABI3_FORWARD_COMPATIBILITY=0
TEST_FLAGS ?= --manifest-path $(WORKSPACE_MANIFEST) --workspace --all-features
RESOLVE_VENV_PYTHON = VENV_PYTHON=".venv/bin/python"; if [ ! -x "$$VENV_PYTHON" ]; then VENV_PYTHON=".venv/Scripts/python.exe"; fi

.PHONY: help all clean build build-release lint fmt check-fmt \
        markdownlint nixie test test-ci test-quick typecheck tools \
        tools-check tools-docs tools-lint release release-artifact smoke \
        smoke-release

.DEFAULT_GOAL := all

all: ## Run commit gates
	$(MAKE) check-fmt
	$(MAKE) typecheck
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) markdownlint
	$(MAKE) nixie

.venv: pyproject.toml uv.lock $(WORKSPACE_MANIFEST) Cargo.lock
	UV_VENV_CLEAR=1 $(UV_ENV) $(UV) venv
	$(CARGO_BUILD_ENV) $(UV_ENV) $(UV) sync --group dev

build: .venv ## Build dev artifact and install into venv
	$(CARGO_BUILD_ENV) $(UV_RUN) maturin develop --manifest-path $(PYEXT_MANIFEST)
	$(MAKE) smoke

release: release-artifact smoke-release ## Build and smoke-test the release artifact

release-artifact: ## Build the release artifact
	rm -rf dist
	$(CARGO_BUILD_ENV) $(UV_RUN) maturin build --release --manifest-path $(PYEXT_MANIFEST) --out dist

build-release: release ## Backward-compatible alias for release

smoke: .venv ## Smoke-test the development install through the Rust bridge
	$(RESOLVE_VENV_PYTHON); \
	"$$VENV_PYTHON" -m stilyagi.smoke

smoke-release: .venv release-artifact ## Smoke-test the release wheel through the Rust bridge
	rm -rf .venv-release-smoke
	$(RESOLVE_VENV_PYTHON); \
	"$$VENV_PYTHON" -m venv .venv-release-smoke
	release_python=".venv-release-smoke/bin/python"; \
	if [ ! -x "$$release_python" ]; then release_python=".venv-release-smoke/Scripts/python.exe"; fi; \
	"$$release_python" -m pip install --no-index --find-links dist stilyagi
	release_python="$(CURDIR)/.venv-release-smoke/bin/python"; \
	if [ ! -x "$$release_python" ]; then release_python="$(CURDIR)/.venv-release-smoke/Scripts/python.exe"; fi; \
	release_tmp="$$("$$release_python" -c 'import pathlib, tempfile; print(pathlib.Path(tempfile.gettempdir()).as_posix())')"; \
	cd "$$release_tmp" && "$$release_python" -m stilyagi.smoke

clean: ## Remove build artifacts
	$(CARGO) clean --manifest-path $(WORKSPACE_MANIFEST)
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv .venv-release-smoke
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf
	find . -type f -name '*.log' -not -path './crates/stilyagi-pyext/target/*' -delete

define ensure_tool
$(if $(shell command -v $(1) >/dev/null 2>&1 && echo y),,\
$(error $(1) is required but not installed))
endef

tools:
	$(call ensure_tool,$(MDFORMAT_ALL))
	$(MAKE) tools-check

tools-check:
	$(call ensure_tool,$(CARGO))
	$(call ensure_tool,rustfmt)
	$(call ensure_tool,uv)

tools-docs:
	$(call ensure_tool,$(MDLINT))
	$(call ensure_tool,$(NIXIE))

tools-lint: tools-check
	$(call ensure_tool,whitaker)
	$(call ensure_tool,$(INTERROGATE))

fmt: tools ## Format sources
	$(UV_RUN) ruff format
	$(UV_RUN) ruff check --select I --fix
	$(MDFORMAT_ALL)
	$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all

check-fmt: tools-check ## Verify formatting
	$(UV_RUN) ruff format --check
	$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check

lint: tools-lint ## Run linters
	$(UV_RUN) ruff check
	$(INTERROGATE) $(INTERROGATE_FLAGS) $(INTERROGATE_TARGETS)
	$(PYLINT) $(PYLINT_TARGETS)
	RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)
	$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) whitaker --all -- $(CARGO_FLAGS)

typecheck: build tools-check ## Run typechecking
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) check $(CARGO_FLAGS)
	$(UV_RUN) ty --version
	$(UV_RUN) ty check

markdownlint: tools-docs ## Lint Markdown files
	find . -type f -name '*.md' -not -path './.venv/*' -not -path './.venv-release-smoke/*' -not -path './crates/stilyagi-pyext/target/*' -print0 | xargs -0 $(MDLINT)

nixie: tools-docs ## Validate Mermaid diagrams
	find . -type f -name '*.md' -not -path './.venv/*' -not -path './.venv-release-smoke/*' -not -path './crates/stilyagi-pyext/target/*' -print0 | xargs -0 $(NIXIE) --no-sandbox

test: build tools-lint ## Run tests (nextest if available, otherwise cargo test)
	$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check
	$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)
	@if $(CARGO) nextest --version >/dev/null 2>&1; then \
		RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile default --no-tests pass $(TEST_FLAGS) $(BUILD_JOBS); \
	else \
		echo "cargo-nextest not installed, falling back to cargo test"; \
		RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) test $(TEST_FLAGS) $(BUILD_JOBS); \
	fi
	RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)
	# Run pytest through the venv interpreter so the maturin-developed extension
	# remains installed instead of being replaced by the uv_build wheel.
	$(RESOLVE_VENV_PYTHON); \
	"$$VENV_PYTHON" -m pytest -v

test-ci: build tools-lint ## Run Rust tests with the CI nextest profile
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile ci --no-tests pass $(TEST_FLAGS) $(BUILD_JOBS)
	RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) test $(TEST_FLAGS) --doc $(BUILD_JOBS)

test-quick: build tools-lint ## Run Rust library tests only with nextest
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile default --no-tests pass --lib $(TEST_FLAGS) $(BUILD_JOBS)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
