# Architectural decision record (ADR) 004: Adopt two-tier Python linting

## Status

Accepted.

## Date

2026-05-15.

## Context and problem statement

Stilyagi is a mixed Rust and Python project. The Python side owns
configuration, rule execution, plugin loading, diagnostics, and output
rendering, so regressions in Python code quality can directly affect the
maintainer-facing development workflow and the future user-facing rule
surface.[^1]

The project already relied on Ruff for formatting, import ordering, and fast
Python lint feedback. That remained necessary, but it left a useful class of
review checks out of the normal gate: selected Pylint diagnostics for logging
templates, pattern matching, simplification, resource handling, file encoding,
environment helpers, subprocess safety, and broad design pressure.

The immediate question is therefore:

Which Python linting architecture should Stilyagi adopt so maintainers get fast
local feedback without losing the higher-level review signals that Ruff does
not currently cover?

## Decision drivers

- Keep the first Python lint tier fast enough that `make lint` remains a
  normal local command, not a heavyweight special case.
- Reuse the lint policy already proven in `leynos/episodic` rather than
  inventing a project-local rule taxonomy from scratch.[^2]
- Keep Pylint focused on explicitly selected diagnostics so it complements
  Ruff instead of duplicating Ruff's whole rule surface.
- Run Pylint through PyPy using the pinned `pylint-pypy-shim` wrapper so the
  second tier follows the established Episodic execution model.[^3]
- Keep the Rust lint tiers in the same `make lint` target so contributors have
  one canonical code-quality command for the mixed workspace.
- Preserve deterministic tool resolution through `uv`, the lockfile, and
  Makefile variables.

## Options considered

### Option A: Ruff first, focused Pylint second, then Rust lint tiers

This option keeps Ruff as the first Python lint tier. Ruff handles fast syntax,
style, import, documentation, naming, security, type-import, and
complexity-adjacent checks. Pylint then runs as a focused second tier with all
messages disabled except the explicit policy in `pyproject.toml`.

The strongest argument for this option is complementarity. Ruff provides speed
and broad editor-aligned feedback; Pylint provides selected semantic-style and
review-oriented diagnostics. Keeping Pylint focused avoids turning it into a
second general-purpose lint regime.

The main cost is operational complexity. Contributors must understand the
second Python lint runner, the PyPy shim, and the Makefile variables that
control it.

### Option B: Ruff only

This option would keep the lint workflow simple and fast by relying only on
Ruff for Python code.

The strongest argument for this option is simplicity. One Python linter is easy
to explain and easy to cache.

The main weakness is coverage. Ruff does not cover every selected diagnostic
the project wants from Pylint, especially the review-oriented messages around
logging, resource handling, subprocess calls, environment helpers, and some
design constraints.

### Option C: Pylint as the primary Python lint gate

This option would make Pylint the main Python linting tool and use Ruff only
for formatting and import sorting.

The strongest argument for this option is centralization around one
configuration-heavy analysis tool.

The main weakness is developer feedback speed and signal shape. Pylint is most
useful here as a narrower second pass. Making it the primary gate would
duplicate many Ruff findings and make routine linting heavier than it needs to
be.

| Topic                                      | Option A: Ruff then focused Pylint | Option B: Ruff only | Option C: Pylint primary |
| ------------------------------------------ | ---------------------------------- | ------------------- | ------------------------ |
| Fast first feedback                        | Yes                                | Yes                 | Weak                     |
| Covers selected Pylint-only diagnostics    | Yes                                | No                  | Yes                      |
| Avoids broad duplicate Python lint regimes | Yes                                | Yes                 | No                       |
| Matches the imported Episodic policy       | Yes                                | No                  | No                       |
| Keeps one mixed-workspace lint command     | Yes                                | Yes                 | Yes                      |

_Table 1: Python linting architecture options._

## Decision outcome

Adopt Option A.

`make lint` SHALL run these tiers in order:

1. Ruff through `uv run --group dev`.
2. Focused Pylint through `uv tool run --python pypy` and the pinned
   `pylint-pypy-shim` wrapper.
3. Rust `cargo clippy` with warnings denied.
4. Whitaker from `crates/stilyagi-pyext/`.

The Python lint policy SHALL live in `pyproject.toml`:

- `[tool.ruff]` and `[tool.ruff.lint]` define the Ruff target version,
  preview mode, selected rule families, ignored docstring conflicts, per-file
  test suppressions, import-convention aliases, banned deprecated `typing.*`
  APIs, pydocstyle convention, McCabe threshold, and Ruff's Pylint
  compatibility thresholds.
- `[tool.pylint.main]`, `[tool.pylint.design]`, and
  `[tool.pylint."messages control"]` define the focused Pylint pass. The pass
  disables all messages by default and enables only the explicitly selected
  diagnostics.

The Makefile SHALL expose variables for the Pylint runner:

- `PYLINT_PYTHON` selects the interpreter used by `uv tool run`; it defaults
  to `pypy`.
- `PYLINT_TARGETS` selects the Python paths checked by Pylint; it defaults to
  `python/stilyagi tests`.
- `PYLINT_PYPY_SHIM_REF` pins the shim commit.
- `PYLINT_PYPY_SHIM` expands the pinned Git URL.
- `PYLINT` builds the full `uv tool run` command used by `make lint`.

## Consequences

### Positive consequences

- Contributors can run one command, `make lint`, to exercise Python and Rust
  linting in the intended order.
- Ruff remains the fast first pass and catches most routine Python issues
  before Pylint starts.
- Pylint contributes higher-level checks without importing its whole default
  opinion set.
- The imported lint policy has one auditable home in `pyproject.toml`.
- The pinned PyPy shim makes the second tier reproducible and easy to update
  deliberately.

### Negative consequences

- `make lint` now depends on network or cache availability the first time
  `uv tool run` resolves the pinned shim.
- Pylint's PyPy runtime may lag the project's CPython target. The lint policy
  disables `syntax-error` so the PyPy-backed pass can still be useful on files
  it can parse.
- Contributors must understand that Ruff and Pylint suppressions use
  different inline mechanisms.

### Neutral or clarifying consequences

- This ADR does not make Pylint part of `make check-fmt`; formatting remains a
  Ruff and Cargo concern.
- This ADR does not remove Rust linting from `make lint`; the Makefile remains
  the mixed-workspace gate.
- This ADR does not require every future Episodic lint-policy change to be
  imported automatically. Future updates should be deliberate and gated.

## Operational notes

Run the full lint gate with:

```bash
make lint
```

Run only the Python tiers manually when diagnosing a failure:

```bash
UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools uv run --group dev ruff check
UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools uv tool run --python pypy \
  --from 'git+https://github.com/leynos/pylint-pypy-shim.git@726d09f968b4d729ee4b29c71fc732e744854f3b' \
  pylint-pypy python/stilyagi tests
```

Prefer changing `PYLINT_TARGETS`, `PYLINT_PYTHON`, or `PYLINT_PYPY_SHIM_REF`
through Makefile variables for one-off local experiments. Commit changes to
those defaults only when the project-wide policy is intentionally changing.

## Follow-on work

- Keep the developer's guide aligned with this ADR whenever lint runner
  variables, rule groups, or execution order change.
- Review future `leynos/episodic` lint-policy updates explicitly rather than
  assuming all upstream rule additions suit Stilyagi.
- Revisit the `syntax-error` Pylint disable when the managed PyPy interpreter
  catches up with the project's CPython syntax target.

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [leynos/episodic](https://github.com/leynos/episodic)
[^3]: [leynos/pylint-pypy-shim](https://github.com/leynos/pylint-pypy-shim)
