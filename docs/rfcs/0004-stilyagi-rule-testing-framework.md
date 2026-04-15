# RFC 0004: Stilyagi rule testing framework

## Preamble

- **RFC number:** 0004
- **Status:** Proposed
- **Created:** 2026-04-14

## Summary

Stilyagi SHOULD ship a pytest plugin, alongside the main Python package, for
testing rules, fixtures, extraction behaviour, and diagnostic contracts against
the real engine.

The plugin SHOULD combine two proven ideas:

- `valedate`'s isolated sandbox and assertion-helper model for exercising a
  real linter without touching global configuration, and
- `pytest-flake8-path`'s path-like `tmp_path` wrapper with one deliberate
  runner method and a normalised result object.[^1][^2][^3]

The result SHOULD not be a giant domain-specific language (DSL). It SHOULD be a
thin test harness that makes the common case easy:

- write files into a temporary project root,
- optionally synthesize a temporary rule pack,
- run `stilyagi` in isolation,
- assert on typed diagnostics, fixes, or IR output.

## Problem

Rule authors and Stilyagi maintainers need end-to-end tests that exercise the
real product surface, not a half-fictional internal mock.

Without a dedicated framework, every rule-pack test suite must rebuild the same
plumbing:

- create temporary repositories and config files,
- arrange Python import paths or distribution metadata for test-only rule packs,
- invoke `stilyagi` in a subprocess with the right isolation flags,
- parse JSON output,
- normalise paths across Linux, macOS, and Windows,
- write repetitive assertions for "diagnostic exists", "only these codes
  fired", or "no diagnostics were emitted",
- and debug failures caused by hidden user config, stale caches, or path
  differences rather than by the rule under test.

That is unnecessary friction. Worse, it encourages two bad outcomes:

1. brittle copy-pasted subprocess helpers that silently diverge between rule
   packs, and
2. overuse of unit tests that bypass the CLI, packaging, entry-point
   discovery, and extraction layers that real users depend on.

Stilyagi needs a first-party testing harness because rule authoring is a
first-party feature, not an afterthought.

## Current state

Stilyagi already has the architectural ingredients a rule-testing framework can
rely on:

- a Python CLI contract with `check`, `dump-ir`, JSON output, explicit config
  discovery, and `--stdin-filename` semantics,
- a Python rule API built around typed diagnostics, fixes, and entry-point
  discovery, and
- a stable IR model intended to be inspectable and testable.[^4][^5][^6]

What it does not yet have is a defined testing surface for rule authors.

Two existing tools point in the right direction.

`valedate` provides an isolated temporary sandbox plus assertion helpers so a
Vale rule author can write tests against a real `vale` binary without mutating
global styles trees or user config.[^1] That is the right philosophy for
Stilyagi: real execution, isolated state, thin helpers.

`pytest-flake8-path` wraps pytest's `tmp_path` fixture in a path-like object
with one runner method, and returns a parsed result object with normalised
output lines.[^2] That is the right ergonomics lesson for Stilyagi: tests
should feel like ordinary file-based pytest tests, not like a framework inside
the framework.

The Stilyagi design should borrow the shape, not the implementation baggage.
Stilyagi does not need a Vale-style temporary styles tree, but it does need a
temporary project root and a way to synthesize entry-point-backed rule packs.

## Goals and non-goals

- Goals:
  - Provide a pytest fixture for running Stilyagi against temporary on-disk
    projects using pytest's `tmp_path` model.[^3]
  - Provide a typed result model for diagnostics, fixes, process output, and
    IR dumps.
  - Make rule-pack tests hermetic by default: no user config, no persistent
    cache, and no reliance on system-site mutation.
  - Support testing of temporary third-party rule packs and capability
    providers using the same entry-point discovery contract as production.
  - Provide a small set of assertion helpers for the most common diagnostic
    expectations.
  - Keep test output stable across operating systems through path
    normalisation.
- Non-goals:
  - Replace unit tests for low-level Rust or Python internals.
  - Provide a full declarative fixture DSL for writing projects without files.
  - Hide Python packaging completely from advanced rule-pack tests.
  - Sandbox untrusted rule code.
  - Introduce a second independent diagnostic schema just for tests.

## Proposed design

### 1. Packaging and discovery

The pytest plugin SHOULD ship in the main Stilyagi distribution under a module
such as `stilyagi.pytest_plugin`.

It SHOULD be installable via an optional extra, for example:

```toml
[project.optional-dependencies]
pytest = ["pytest>=8"]

[project.entry-points.pytest11]
stilyagi = "stilyagi.pytest_plugin"
```

This keeps versioning aligned with the main product and avoids the version-skew
mess that would come with a separate `pytest-stilyagi` distribution.

Pytest discovers external plugins through the `pytest11` entry-point group, and
the PyPA entry-point specification makes clear that consumer-defined groups
should use project-owned names and unique names within a group.[^7][^8]

The package SHOULD also register assert rewriting for helper modules that
contain assertion helpers, for example:

```python
import pytest

pytest.register_assert_rewrite("stilyagi.testing")
```

Pytest's plugin documentation explicitly calls this out for helper modules that
are imported by a plugin but are not themselves the `pytest11` entry-point
module.[^7]

### 2. Primary fixture: `stilyagi_path`

The plugin SHOULD provide a fixture named `stilyagi_path`.

`stilyagi_path` SHOULD wrap pytest's built-in `tmp_path` fixture, which already
provides a unique per-test temporary directory as a `pathlib.Path` object.[^3]
The wrapper SHOULD preserve the feel of working with a path while adding
exactly the Stilyagi-specific helpers that rule authors need.

The fixture object SHOULD be named `StilyagiPath` and SHOULD expose:

- path-like behaviour, including `__fspath__`, `/`, `joinpath()`, `iterdir()`,
  and `.path` for the underlying `Path`,
- `run_stilyagi(...)` as the generic runner,
- `run_check(...)` as a convenience wrapper around `stilyagi check`,
- `run_dump_ir(...)` as a convenience wrapper around `stilyagi dump-ir`,
- `install_rule_pack(...)` for temporary entry-point-backed packs,
- `write_config(...)` as a convenience helper for `pyproject.toml` or
  `.stilyagi.toml` when the caller does not want to hand-write the file.

The fixture SHOULD remain intentionally small. Tests SHOULD still write real
files directly using normal `Path` methods.

Example:

```python
from stilyagi.testing import assert_has_diagnostic


def test_serial_comma_rule(stilyagi_path):
    stilyagi_path.write_config(
        """
        [tool.stilyagi]
        plugins = ["builtin"]

        [tool.stilyagi.lint]
        select = ["PUN201"]
        """
    )
    (stilyagi_path / "doc.md").write_text(
        "Apples, bananas and pears.\n",
        encoding="utf-8",
    )

    result = stilyagi_path.run_check("doc.md")

    diag = assert_has_diagnostic(result.diagnostics, code="PUN201")
    assert diag.path == "./doc.md"
    assert diag.fix is not None
    assert diag.fix.applicability == "safe"
```

### 3. Execution model

The plugin SHOULD execute Stilyagi in a subprocess by default.

That is the right default because it exercises:

- the installed command surface,
- config loading,
- plugin discovery,
- CLI exit codes,
- JSON rendering,
- and Rust-extension import behaviour.

An in-process fast path MAY be explored later, but it SHOULD NOT be the default
contract in v1 because it would invite global-state leakage and test a
different execution model from what users actually run.

The default subprocess form SHOULD be:

```python
[sys.executable, "-m", "stilyagi", ...]
```

This avoids shell-specific quoting issues and does not depend on a console
script being on `PATH`.

The runner SHOULD force a hermetic baseline by default:

- `--isolated`
- `--no-cache`
- caller-provided working directory rooted at `stilyagi_path`
- `PYTHONUTF8=1`

`run_check(...)` SHOULD default to `--output-format json` so tests receive a
parsed diagnostic model without reimplementing JSON parsing in every suite.
Callers SHOULD still be able to request raw text or SARIF when the renderer
itself is under test.

### 4. Result model

The subprocess runner SHOULD return a typed `StilyagiRunResult`.

It SHOULD include at least:

- `command: list[str]`
- `cwd: Path`
- `exit_code: int`
- `stdout: str`
- `stderr: str`
- `stdout_lines: list[str]`
- `stderr_lines: list[str]`
- `diagnostics: list[Diagnostic] | None`
- `diagnostics_by_path: dict[str, list[Diagnostic]] | None`
- `ir_documents: list[dict] | None`

The result object SHOULD normalise paths into a stable Unix-like form such as
`./path/to/file.md`, following the same cross-platform testing principle that
`pytest-flake8-path` uses for flake8 output.[^2]

The plugin SHOULD NOT invent a separate test-only diagnostic type if the main
package already exposes a suitable parsed JSON model. Reuse is preferable.

### 5. Assertion helpers

The plugin SHOULD provide a small helper module, for example
`stilyagi.testing`, with helpers modelled on the best parts of `valedate`.[^1]

v1 SHOULD include at least:

- `assert_has_diagnostic(diagnostics, *, code=None, path=None, message=None)`
- `assert_no_diagnostics(diagnostics)`
- `assert_only_codes(diagnostics, expected_codes)`
- `assert_has_fix(diagnostics, *, code, applicability=None)`
- `assert_ir_region(ir_documents, *, kind=None, text_contains=None)`

These helpers SHOULD return the matched object where useful, so callers can
make more specific assertions without re-searching collections.

The helpers SHOULD stay deliberately dumb. They exist to remove repetitive test
noise, not to become a mini assertion language.

### 6. Temporary rule packs and capability providers

This is the one place where Stilyagi needs more than `pytest-flake8-path`.

Because Stilyagi discovers third-party packs and providers through entry
points, the testing plugin MUST make it possible to synthesize temporary
distributions that look installed enough for `importlib.metadata` to see them.

`install_rule_pack(...)` SHOULD:

- create a temporary package tree under the test root,
- write Python modules supplied by the test,
- create a `.dist-info` directory with `METADATA` and `entry_points.txt`,
- register `stilyagi.rules` and optionally `stilyagi.capabilities` entries,
- prepend the temporary site-packages root to `PYTHONPATH` for subprocess
  execution.

This is lighter and faster than creating a virtual environment or invoking
`pip install` for every test, while still exercising the same entry-point
metadata format described by the PyPA specification.[^8]

Example:

```python
def test_custom_rule_pack(stilyagi_path):
    stilyagi_path.install_rule_pack(
        name="demo-pack",
        modules={
            "demo_pack/rules.py": """
                from stilyagi.api import Capability, Diagnostic, RegionTarget, Rule

                class NoFooRule(Rule[None]):
                    code = "DEMO001"
                    name = "no-foo"
                    summary = "Reject foo."
                    targets = [RegionTarget(kind={"paragraph"})]
                    requires = {Capability.STRUCTURE}

                    def visit_region(self, ctx, region):
                        if "foo" in region.text:
                            yield Diagnostic(
                                code=self.code,
                                message="Avoid foo.",
                                span=region.span,
                            )
            """,
        },
        rule_entry_points={"demo": "demo_pack.rules"},
    )
    stilyagi_path.write_config(
        """
        [tool.stilyagi]
        plugins = ["demo-pack"]

        [tool.stilyagi.lint]
        select = ["DEMO"]
        """
    )
    (stilyagi_path / "doc.md").write_text("foo appears here\n", encoding="utf-8")

    result = stilyagi_path.run_check("doc.md")

    assert_has_diagnostic(result.diagnostics, code="DEMO001")
```

### 7. `dump-ir` and extractor tests

The framework SHOULD treat extraction and rule testing as related but distinct.

`run_dump_ir(...)` SHOULD return parsed IR documents so tests can assert on:

- extracted region kinds,
- owner metadata,
- synthetic segment handling,
- suppression discovery,
- and parse anomalies.

That matters because a false positive may be caused by a bad rule or by a bad
extractor. The testing framework should make both failure classes easy to
distinguish.

### 8. Stdin support

The runner SHOULD make stdin tests ergonomic.

`run_check(...)` SHOULD accept:

- `stdin: str`
- `stdin_filename: str | None`

When `stdin` is provided, the helper SHOULD pass `-` and require or strongly
encourage `stdin_filename`, because the CLI contract uses that filename for
syntax inference and per-file config selection.[^5]

### 9. Scope and performance

The plugin SHOULD be safe for ordinary pytest and `pytest-xdist` runs.

Using `tmp_path` gives each test a unique directory, and pytest's temporary
directory machinery is already designed for per-test isolation and concurrent
execution when configured appropriately.[^3]

The framework SHOULD avoid heavyweight per-test environment creation. That is
why synthetic `dist-info` trees are preferred over creating a new virtual
environment for every rule-pack test.

Session-scoped factories MAY be added later if Stilyagi needs to benchmark
large corpora or reuse expensive fixture material, but function-scoped
isolation should be the default.

## Requirements

### Functional requirements

- The plugin MUST provide a fixture for running Stilyagi against a temporary
  project root.
- The fixture MUST support writing ordinary files using normal `Path`
  operations.
- The fixture MUST provide an isolated Stilyagi runner with sane defaults for
  rule and extractor tests.
- The fixture MUST support `check` and `dump-ir` workflows in v1.
- The framework MUST provide a typed result object.
- The framework MUST provide a minimal assertion-helper surface.
- The framework MUST support temporary rule-pack installation through entry
  points.
- The framework MUST support temporary capability-provider installation through
  entry points.
- The framework MUST normalise paths in parsed output for cross-platform test
  stability.

### Technical requirements

- The default runner MUST use a subprocess, not in-process execution.
- The default runner MUST use `sys.executable -m stilyagi`.
- The default runner MUST pass `--isolated` and `--no-cache` unless explicitly
  overridden.
- The helper that synthesizes temporary packs MUST write compliant
  `entry_points.txt` metadata for `stilyagi.rules` and
  `stilyagi.capabilities`.[^8]
- JSON diagnostics returned by the test harness MUST be parsed using the same
  schema the product itself documents.
- The plugin MUST not mutate user-level config, global caches, or the caller's
  system environment outside subprocess environment variables.

### Safety and operational requirements

- The framework MUST document that temporary rule packs run arbitrary Python
  code and are not sandboxed.
- The framework MUST not auto-download NLP models.
- Tests that need a spaCy model MUST fail clearly when the model is missing.
- The framework SHOULD preserve raw stdout and stderr for debugging failed
  subprocess runs.

## Compatibility and migration

The plugin SHOULD be additive. Projects MAY continue to invoke Stilyagi
manually in tests if they want, but the first-party plugin should become the
recommended approach for rule-pack tests.

Migration from ad hoc helpers should be straightforward:

- replace hand-written `tmp_path` plus subprocess glue with `stilyagi_path`,
- replace JSON-search boilerplate with assertion helpers,
- replace test-only editable installs with `install_rule_pack(...)` where
  entry-point testing is needed.

The plugin SHOULD live in the same versioned distribution as Stilyagi so that
rule authors do not have to match a separate helper package version to the
engine version.

## Alternatives considered

### Option A: no pytest plugin, only helper functions

Rejected.

This would avoid pytest-plugin packaging, but every test suite would still need
to wire up `tmp_path`, subprocess defaults, and path normalisation manually.
That is precisely the repetition this RFC is trying to eliminate.

### Option B: separate `pytest-stilyagi` distribution

Rejected for v1.

It sounds tidy until versions drift. The testing harness is tightly coupled to
CLI flags, JSON schemas, and plugin-discovery semantics. Splitting the package
would create a compatibility problem for little gain.

### Option C: in-process engine invocation by default

Rejected for v1.

It would be faster, but it would test the wrong thing by default. Stilyagi
users run the installed tool, with config discovery, subprocess environment,
and entry-point resolution. The harness should exercise that path first.

### Option D: snapshot-only testing over fixture corpora

Rejected as the primary model.

Snapshots are useful, but they are not enough. Rule authors still need direct,
explicit assertions such as "this code fired" or "no diagnostics were emitted".

## Open questions

- Should the pytest plugin auto-register through `pytest11`, or should Stilyagi
  require explicit `pytest_plugins = ["stilyagi.pytest_plugin"]` to reduce
  surprise in environments that happen to install `stilyagi[pytest]`?
- Should `install_rule_pack(...)` expose low-level metadata knobs in v1, or
  should it only expose the narrow interface needed for rules and capability
  providers?
- Should the framework add diff-specific assertion helpers once autofix
  behaviour settles?
- Should large integration suites get a session-scoped `stilyagi_factory`
  fixture later, or is function-scoped isolation enough?

## Recommendation

Adopt a first-party pytest plugin in the main Stilyagi distribution, exposed
through an optional pytest extra.

Build the smallest testing surface that can carry real rule-author workflows:

- `stilyagi_path`,
- `StilyagiRunResult`,
- a handful of assertion helpers,
- and temporary entry-point-backed rule-pack installation.

Take `valedate`'s isolation model and `pytest-flake8-path`'s fixture ergonomics
seriously, but stop there. Do not build a huge bespoke testing DSL. If Stilyagi
is genuinely programmable, then ordinary pytest plus a thin first-party harness
should be enough.

## References

[^1]: [leynos/valedate](https://github.com/leynos/valedate)
[^2]: [adamchainz/pytest-flake8-path](https://github.com/adamchainz/pytest-flake8-path)
[^3]: [pytest `tmp_path` fixture documentation](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
[^4]: [RFC 0001: Stilyagi Intermediate Representation](0001-stilyagi-intermediate-representation.md)
[^5]: [RFC 0003: Stilyagi CLI contract](0003-stilyagi-cli-contract.md)
[^6]: [RFC 0002: Stilyagi Python rule API](0002-stilyagi-python-rule-api.md)
[^7]: [pytest plugin documentation](https://docs.pytest.org/en/stable/how-to/writing_plugins.html)
[^8]: [PyPA entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/)
