MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
MDFORMAT_ALL ?= mdformat-all
CARGO ?= cargo
WHITAKER ?= whitaker
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
DF12_PYTHON ?= 3.14
PYLINT = $(UV_ENV) $(UV) tool run --python $(PYLINT_PYTHON) \
	--from '$(PYLINT_PYPY_SHIM)' pylint-pypy --load-plugins=
DF12_PYLINT_MESSAGES = R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,R9112,C9112
DF12_PYLINT = $(UV_RUN) --python $(DF12_PYTHON) pylint \
	--disable=all --load-plugins=df12_python_lints \
	--enable=$(DF12_PYLINT_MESSAGES)
AMBRLEAKS = $(UV_RUN) --python $(DF12_PYTHON) ambrleaks
SKYLOS_VERSION = 4.33.2
# Skylos parses source using its own Python AST, so Python 3.14 prevents
# phantom dead-code findings from syntax older tool runtimes cannot parse.
SKYLOS_CLI = $(UV_ENV) $(UV) tool run --python 3.14 --from 'skylos==$(SKYLOS_VERSION)' skylos
SKYLOS = $(SKYLOS_CLI) --config-file pyproject.toml
SKYLOS_PRODUCTION_TARGETS ?= python/stilyagi
SKYLOS_EXCLUDE_FOLDERS ?= tests
INTERROGATE ?= $(UV_RUN) interrogate
INTERROGATE_TARGETS ?= python/stilyagi tests
INTERROGATE_FLAGS ?= --fail-under 100
# Single source of truth for the ty version; CI consumes it through the
# typecheck target, so the Makefile and CI cannot drift apart.
TY_VERSION ?= 0.0.72
TY = env $(UV_ENV) $(UV) tool run ty@$(TY_VERSION)
# Single source of truth for the typos version; CI consumes it through the
# markdownlint target, so the Makefile and CI cannot drift apart.
TYPOS_VERSION ?= 1.48.0
PATHSPEC_VERSION ?= 1.1.1
PYTEST_VERSION ?= 9.1.1
CMD_MOX_VERSION ?= 0.2.0
CYCLOPTS_VERSION ?= 4.21.1
PLUMBUM_VERSION ?= 2.0.1
TYPOS_CONFIG_BUILDER_COMMIT := b604f198797fdd36a567dd0f8f07b13f9539b241
TYPOS_CONFIG_BUILDER_SOURCE := \
	git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_COMMIT)
TYPOS_CONFIG_BUILDER := $(UV_ENV) $(UV) tool run --python 3.14 \
	--from "$(TYPOS_CONFIG_BUILDER_SOURCE)" typos-config-builder
# The env prefix lets xargs execute the command despite the leading
# variable assignments in UV_ENV.
TYPOS = env $(UV_ENV) $(UV) tool run typos@$(TYPOS_VERSION)
SPELLING_PY_ENV := PYTHONDONTWRITEBYTECODE=1
SPELLING_PY_SRCS := \
	scripts/typos_rollout_check.py scripts/tests/typos_rollout_check_testcases.py
SPELLING_HELPER_PYTEST := PYTHONPATH=scripts $(SPELLING_PY_ENV) \
	$(UV_ENV) $(UV) run --no-project --python 3.14 \
	--with cmd-mox==$(CMD_MOX_VERSION) --with cyclopts==$(CYCLOPTS_VERSION) \
	--with pathspec==$(PATHSPEC_VERSION) --with plumbum==$(PLUMBUM_VERSION) \
	--with pytest==$(PYTEST_VERSION) \
	python -m pytest
MD_FILES_FIND = find . -type f -name '*.md' -not -path './.venv/*' -not -path './.venv-release-smoke/*' -not -path './.uv-cache/*' -not -path './.uv-tools/*' -not -path './target/*' -not -path './crates/stilyagi-pyext/target/*' -print0
CARGO_BUILD_ENV ?= PYO3_USE_ABI3_FORWARD_COMPATIBILITY=0
TEST_FLAGS ?= --manifest-path $(WORKSPACE_MANIFEST) --workspace --all-features
RESOLVE_VENV_PYTHON = VENV_PYTHON=".venv/bin/python"; if [ ! -x "$$VENV_PYTHON" ]; then VENV_PYTHON=".venv/Scripts/python.exe"; fi

.PHONY: help all clean build build-release lint fmt check-fmt \
        markdownlint nixie spelling spelling-config spelling-config-write \
        spelling-helper-test spelling-phrase-check test test-ci test-quick \
        typecheck tools skylos-allow \
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
	$(call ensure_tool,uv)

tools-lint: tools-check
	$(call ensure_tool,$(WHITAKER))

fmt: tools ## Format sources
	$(UV_RUN) ruff format
	$(UV_RUN) ruff check --select I --fix
	$(MDFORMAT_ALL)
	$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all

check-fmt: tools-check ## Verify formatting
	$(UV_RUN) ruff format --check
	$(CARGO) fmt --manifest-path $(WORKSPACE_MANIFEST) --all -- --check

lint: tools-lint ## Run linters, including the Whitaker Dylint suite
	$(UV_RUN) ruff check
	$(INTERROGATE) $(INTERROGATE_FLAGS) $(INTERROGATE_TARGETS)
	$(PYLINT) $(PYLINT_TARGETS)
	$(DF12_PYLINT) $(PYLINT_TARGETS)
	$(AMBRLEAKS) tests
	RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) doc $(DOC_FLAGS)
	$(CARGO_BUILD_ENV) $(CARGO) clippy $(CLIPPY_FLAGS)
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(WHITAKER) --all -- $(CARGO_FLAGS)
	$(SKYLOS) $(SKYLOS_PRODUCTION_TARGETS) --exclude $(SKYLOS_EXCLUDE_FOLDERS) --category dead_code --gate --format concise --no-upload --no-provenance --no-grep-verify

skylos-allow: export SKYLOS_SYMBOL = $(value SYMBOL)
skylos-allow: export SKYLOS_REASON = $(value REASON)
skylos-allow: ## Document one named Skylos exception, not an entry point
	@case "$${SKYLOS_SYMBOL}" in *[![:space:]]*) ;; *) printf "Error: SYMBOL is required for a named whitelist exception\\n" >&2; exit 2;; esac
	@case "$${SKYLOS_REASON}" in *[![:space:]]*) ;; *) printf "Error: REASON is required for a named whitelist exception\\n" >&2; exit 2;; esac
	$(SKYLOS_CLI) whitelist "$${SKYLOS_SYMBOL}" --reason "$${SKYLOS_REASON}"

typecheck: build tools-check ## Run typechecking
	RUSTFLAGS="$(RUST_FLAGS)" $(CARGO_BUILD_ENV) $(CARGO) check $(CARGO_FLAGS)
	$(TY) --version
	$(TY) check

markdownlint: tools-docs spelling ## Lint Markdown files and enforce en-GB-oxendict spelling
	$(MD_FILES_FIND) | xargs -0 $(MDLINT)

spelling: spelling-phrase-check ## Enforce en-GB-oxendict spelling
	$(MD_FILES_FIND) | xargs -0 $(TYPOS) --config typos.toml --force-exclude --

spelling-phrase-check: spelling-config ## Enforce shared exact-phrase corrections
	PYTHONPATH=scripts $(SPELLING_PY_ENV) $(UV_ENV) $(UV) run --no-project \
		--python 3.14 --with pathspec==$(PATHSPEC_VERSION) \
		scripts/typos_rollout_check.py --repository .

spelling-config: spelling-helper-test ## Check generated spelling configuration
	$(TYPOS_CONFIG_BUILDER) --repository . --check

spelling-config-write: spelling-helper-test ## Regenerate spelling configuration
	$(TYPOS_CONFIG_BUILDER) --repository .

spelling-helper-test: ## Validate the standalone spelling phrase helper
	$(UV_RUN) ruff format --check $(SPELLING_PY_SRCS)
	$(UV_RUN) ruff check $(SPELLING_PY_SRCS)
	$(SPELLING_HELPER_PYTEST) scripts/tests/typos_rollout_check_testcases.py \
		-c /dev/null --rootdir=. -p no:cacheprovider

nixie: tools-docs ## Validate Mermaid diagrams
	$(MD_FILES_FIND) | xargs -0 $(NIXIE) --no-sandbox

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
