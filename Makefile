MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
MDFORMAT_ALL ?= mdformat-all
CARGO ?= cargo
export PATH := $(HOME)/.cargo/bin:$(HOME)/.local/bin:$(HOME)/.bun/bin:$(PATH)
WORKSPACE_MANIFEST ?= Cargo.toml
PYEXT_MANIFEST ?= crates/stilyagi-pyext/Cargo.toml
BUILD_JOBS ?=
RUST_FLAGS ?=
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools
UV_RUN = $(UV_ENV) uv run --group dev
CARGO_BUILD_ENV ?= PYO3_USE_ABI3_FORWARD_COMPATIBILITY=0
TEST_FLAGS ?= --manifest-path $(WORKSPACE_MANIFEST) --workspace

.PHONY: help all clean build build-release lint fmt check-fmt \
        markdownlint nixie test test-ci test-quick typecheck tools \
        tools-check tools-docs tools-lint release release-artifact smoke \
        smoke-release

.DEFAULT_GOAL := all

all: release ## Build the release artifact

.venv:
	UV_VENV_CLEAR=1 $(UV_ENV) uv venv
	$(CARGO_BUILD_ENV) $(UV_ENV) uv sync --group dev

build: .venv ## Build dev artifact and install into venv
	$(CARGO_BUILD_ENV) $(UV_RUN) maturin develop --manifest-path $(PYEXT_MANIFEST)
	$(MAKE) smoke

release: release-artifact smoke-release ## Build and smoke-test the release artifact

release-artifact: ## Build the release artifact
	rm -rf dist
	$(CARGO_BUILD_ENV) $(UV_RUN) maturin build --release --manifest-path $(PYEXT_MANIFEST) --out dist

build-release: release ## Backward-compatible alias for release

smoke: .venv ## Smoke-test the development install through the Rust bridge
	.venv/bin/python -m stilyagi.smoke

smoke-release: .venv release-artifact ## Smoke-test the release wheel through the Rust bridge
	rm -rf .venv-release-smoke
	.venv/bin/python -m venv .venv-release-smoke
	.venv-release-smoke/bin/python -m pip install --no-index --find-links dist stilyagi
	cd /tmp && "$(CURDIR)/.venv-release-smoke/bin/python" -m stilyagi.smoke

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
	$(CARGO_BUILD_ENV) $(CARGO) clippy --manifest-path $(WORKSPACE_MANIFEST) --workspace --all-targets -- -D warnings
	# Whitaker resolves cargo metadata from the crate directory in this repo.
	cd crates/stilyagi-pyext && RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) whitaker --all

typecheck: build tools-check ## Run typechecking
	$(UV_RUN) ty --version
	$(UV_RUN) ty check

markdownlint: tools-docs ## Lint Markdown files
	find . -type f -name '*.md' -not -path './.venv/*' -not -path './.venv-release-smoke/*' -not -path './crates/stilyagi-pyext/target/*' -print0 | xargs -0 $(MDLINT)

nixie: tools-docs ## Validate Mermaid diagrams
	find . -type f -name '*.md' -not -path './.venv/*' -not -path './.venv-release-smoke/*' -not -path './crates/stilyagi-pyext/target/*' -print0 | xargs -0 $(NIXIE) --no-sandbox

test: build tools-lint ## Run tests (nextest if available, otherwise cargo test)
	$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check
	$(CARGO_BUILD_ENV) $(CARGO) clippy --manifest-path $(WORKSPACE_MANIFEST) --workspace --all-targets -- -D warnings
	@if $(CARGO) nextest --version >/dev/null 2>&1; then \
		RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile default --no-tests pass $(TEST_FLAGS) $(BUILD_JOBS); \
	else \
		echo "cargo-nextest not installed, falling back to cargo test"; \
		RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) test $(TEST_FLAGS) $(BUILD_JOBS); \
	fi
	# Run pytest through the venv interpreter so the maturin-developed extension
	# remains installed instead of being replaced by the uv_build wheel.
	.venv/bin/python -m pytest -v

test-ci: build tools-lint ## Run Rust tests with the CI nextest profile
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile ci --no-tests pass $(TEST_FLAGS) $(BUILD_JOBS)

test-quick: build tools-lint ## Run Rust library tests only with nextest
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) nextest run --profile default --no-tests pass --lib $(TEST_FLAGS) $(BUILD_JOBS)

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
