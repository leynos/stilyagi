# Architectural decision record (ADR) 0011: Pinned nightly and the development build standard

## Status

Accepted. The repository pins a dated Rust nightly, declares no minimum
supported Rust version (MSRV), applies the parallel `rustc` frontend and the
`mold` linker to every bare development `cargo` run, and records a reproduced
exception for the Cranelift codegen backend. Release, coverage, and Whitaker
routes exclude the development flags.

## Date

2026-10-19.

## Context and problem statement

Two open issues asked for decisions the repository had never recorded:

- Issue #165 asked whether a stable toolchain is the right choice for a
  repository whose only consumer of its Rust code is a Python package.
- Issue #145 observed that neither the Cranelift backend nor the `mold` linker
  was in effect, and that nothing in the repository recorded the gap.

The estate's `rust-build-defaults` canon gives a nightly-pinned repository the
parallel frontend (`-Zthreads=8`), the `mold` linker on Linux, and the
Cranelift backend for development builds where the full suite passes under it.
The parallel frontend needs a nightly compiler. This repository had a stable pin
(`1.99.1`) and a workspace `rust-version = "1.85"` that no consumer required.

The PyO3 extension adds two constraints. `maturin` builds the `cdylib` for both
`make build` (dev profile) and the published wheel (release profile), so
whatever lands must select a backend per profile and leave the wheel on LLVM.
And PyO3 wraps every `#[pyfunction]` entry in `catch_unwind` and turns a panic
into `PanicException`, so a backend that cannot unwind would abort the Python
interpreter instead of raising.

## Decision drivers

- The only consumer of the Rust crates is the Python package, so no downstream
  user relies on a stable compiler version.
- Every crate is `publish = false`. A declared MSRV that CI does not exercise
  is a claim nothing checks, and stable 1.85 cannot build a tree whose Cargo
  configuration names nightly-only flags.
- A green gate must prove the standard was used. Cargo selects exactly one
  `rustflags` source and an assigned `RUSTFLAGS` displaces them all, so a
  recipe that assigns only `-D warnings` silently drops the standard.
- A missing prerequisite must produce an actionable installation error, never
  a silent fallback to a slower or different build shape.
- A backend exception needs a reproduced incompatibility with a precise scope,
  not a copied explanation.

## Options considered

### Option A: Pinned dated nightly with the full standard (chosen)

Pin `nightly-YYYY-MM-DD` in `rust-toolchain.toml`, let Dependabot's
`rust-toolchain` entry move the pin, and adopt `-Zthreads=8`, `mold`, and
Cranelift where it qualifies.

### Option B: Floating stable managed by Dependabot

Keeps stable, but forgoes `-Zthreads=8` for good, which issue #165 ranks below
option A.

### Option C: Stable pin with an MSRV and periodic review

Needs a pressing platform constraint. None exists: the Python wheel is the only
consumer.

### Option D: Stable pin that never changes

Drifts silently and gains nothing an application needs.

| Topic                | A: nightly | B: floating stable | C: MSRV  | D: frozen |
| -------------------- | ---------- | ------------------ | -------- | --------- |
| `-Zthreads=8`        | Yes        | No                 | No       | No        |
| Moves with CI review | Yes        | Yes                | Reviewed | No        |
| Needs an MSRV claim  | No         | No                 | Yes      | No        |
| Snapshot churn       | Per bump   | Per release        | Rare     | None      |

_Table 1: Toolchain options compared._

## Decision outcome

Option A.

### The pin and the MSRV

`rust-toolchain.toml` pins `nightly-2026-10-18` with the components `clippy`,
`llvm-tools-preview`, `rust-analyzer`, `rustc-codegen-cranelift-preview`, and
`rustfmt`. The dated 2026-10-18 distribution manifest reports every component
available for the Linux, macOS, and Windows targets in the release matrix. The
Cranelift component stays in the pin for future backend requalification;
installing it does not select the backend (see the exception below).

`rust-version` is removed from `[workspace.package]` and from every crate. No
crate is published, so the concordat `rust-toolchain-policy` rule that confines
`rust-version` to publishable libraries does not apply, and a declared MSRV
would also have to be exercised by CI.

Dependabot's `rust-toolchain` entry proposes each newer nightly daily. Each
bump pull request may need `TRYBUILD=overwrite` to re-record the compile-fail
`.stderr` snapshots (see the developer's guide, section 4.1), and may surface
new Clippy lints that the strict workspace lint set turns into errors; both are
fixed in the bump pull request.

### The build standard

`.cargo/config.toml` carries, for every bare `cargo build`, `test`, `check`, and
`clippy` run:

```toml
[build]
rustflags = ["-Zthreads=8"]

[target.'cfg(target_os = "linux")']
rustflags = ["-Zthreads=8", "-Clink-arg=-fuse-ld=mold"]
```

The Linux table repeats `-Zthreads=8` because Cargo does not merge sources.
`mold` is named under `cfg(target_os = "linux")` only, so macOS and Windows
keep their default linkers.

The Makefile restates the same flags (`STANDARD_RUSTFLAGS`) in every recipe
that assigns `RUSTFLAGS`: `typecheck`, `lint` (rustdoc and Clippy), `test`,
`test-doc`, `test-ci`, `test-quick`, `build`, and the `.venv` editable install.
`make install-build-tools` installs the pinned `mold` (checksum-verified) and
the pinned toolchain, and `make check-build-tools` is a prerequisite of every
route that compiles under the standard, so a missing tool fails with an
installation hint.

### Excluded routes

| Route            | Mechanism                                                                                                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Release wheel    | `make release-artefact` and the maturin build in `tests/test_maturin_build.py` assign `RUSTFLAGS` from the caller alone, displacing the configuration.                                                 |
| Wheel workflow   | Every `maturin-action` step in `build-wheels.yml` assigns `RUSTFLAGS: ""`. A manylinux container is the host's own target triple, so no `cfg()` selector can exclude it, and the images carry no mold. |
| Coverage         | The coverage step assigns `RUSTFLAGS: -D warnings`, displacing the flags and keeping instrumentation; the shared action selects LLVM itself.                                                           |
| Whitaker         | `WHITAKER_RUST_FLAGS` is `-D warnings` alone; the installer-managed toolchain and `cranelift: true` input are unchanged.                                                                               |
| Mutation testing | The shared workflow's setup-rust exports `-D warnings`, which displaces the flags; `cargo-mutants` reaches no Make goal.                                                                               |

_Table 2: Routes that exclude the development standard, and how._

`make release` is not wholly free of the standard's tooling: `smoke-release`
takes its base interpreter from `.venv`, whose `uv sync` is a compile (a
release-profile editable build, verified with `cargo rustc --profile release`)
that restates the development flags and runs after the preflight. The wheel it
smoke-tests still comes from `release-artefact`, which excludes them, and the
`release-smoke` job installs the pinned tools because it reaches the preflight.

### Cranelift: a recorded exception

Cranelift is not selected. The adoption test was the full Rust suite plus a
probe of the paths that depend on unwinding, because no test panics through
PyO3 or a spawned thread and only a few reach `catch_unwind`, so a green suite
alone would prove little about unwinding through the extension.

(Superseded on 14 November 2026: the estate abandoned Cranelift for now, so the
probe file was removed; this section is kept as history.)

`crates/stilyagi-pyext/tests/unwind_probe.rs` covered the PyO3 trampoline
(`#[pyfunction]` panic to `PanicException`), a bare `catch_unwind`, a panic in
a spawned thread, a panic in a thread spawned from detached Python state, and
`#[should_panic]`.

Reproduced on `nightly-2026-10-18`, `x86_64-unknown-linux-gnu`, with
`[unstable] codegen-backend = true` and
`[profile.dev] codegen-backend = "cranelift"` added to `.cargo/config.toml`
(rustc reports `with cranelift 0.135.0` in the `.comment` section of the
resulting `cdylib`, and the verbose rustc lines carry
`-Z codegen-backend=cranelift`):

- `cargo nextest run -p stilyagi-pyext --test unwind_probe` fails four of five
  cases. `bare_catch_unwind_catches_a_panic` fails: `catch_unwind` does not
  catch. `pyfunction_panic_surfaces_as_panic_exception` fails: the panic
  escapes PyO3's `catch_unwind` instead of becoming `PanicException`. The two
  thread cases abort the process with
  `fatal runtime error: failed to initiate panic, error 5, aborting`. Only
  `#[should_panic]` passes, which is why one successful panic test is not
  evidence.
- The full workspace under Cranelift (362 tests) also fails three existing
  tests that depend on contained panics: `stilyagi-markdown`
  `tests::parser::markdown_parser_panics_are_contained_as_messages` and
  `stilyagi-test-fixtures`
  `expect_valid::tests::option_failure_reports_the_fixture_call_site` and
  `expect_valid::tests::shared_helper_attributes_the_panic_to_the_calling_test`.
  (Two `trybuild` UI tests exceeded nextest's 600 s ceiling while queued
  behind other builds and are not attributed to the backend.)
- The control, the same nightly and flags with the default LLVM backend, passes
  all five probe cases and those three tests.

In a Cranelift-built development extension a panic would therefore abort the
Python interpreter, or escape PyO3's wrapper, instead of raising
`PanicException`. Production code relies on unwinding too: `stilyagi-markdown`
contains Markdown parser panics with `catch_unwind`
(`crates/stilyagi-markdown/ src/lib.rs`), so the incompatibility reaches
shipped behaviour and not only tests. (`proptest` also reports failing cases
through `catch_unwind`.)

The exception is scoped by:

- channel `nightly-2026-10-18` (`rustc 1.101.0-nightly (8006091eb 2026-10-17)`)
  and its `rustc-codegen-cranelift-preview` component;
- platform `x86_64-unknown-linux-gnu`, the only platform measured;
- surface: the dev and test profiles' `codegen-backend = "cranelift"`
  selection through `[unstable] codegen-backend = true`. Release, coverage, and
  Whitaker never selected it.

The exception goes stale on every pin move. A bump pull request that wants to
retire it re-runs the probe: add the two keys to `.cargo/config.toml`, run
`cargo nextest run -p stilyagi-pyext --test unwind_probe` (the probe aborts the
process when unwinding fails, so nextest's per-test processes isolate each
case), and, if every case passes and the full suite passes, keep the keys and
replace this section. `tests/test_build_standard_config.py` refuses a
`codegen-backend` key while this exception stands, and fails if the exception
is removed from the developer's guide without the keys appearing.

## Goals and non-goals

- Goals: record the toolchain decision; make the standard observable from bare
  Cargo and from Make; keep release, coverage, and Whitaker free of it; prove
  both with contracts that fail when the standard is dropped or leaks.
- Non-goals: publishing a crate, an MSRV, a per-repository replica of the
  estate-wide policy tests, or enabling Polonius-next (a separate decision).

## Known risks and limitations

- Source builders on Linux need `mold` and `rustup`: any non-Make Cargo build,
  including `pip install` from a git checkout, reads `.cargo/config.toml`. The
  README states the prerequisites. A release-scoped `rustflags` design would
  avoid this but would not satisfy the estate's `[build]`/`[target]` reading of
  the standard, so it is rejected.
- Daily nightly bumps churn the `trybuild` snapshots. This is accepted rather
  than weakening the UI tests.
- `uv run` re-syncs the project when `pyproject.toml` or `uv.lock` change, and
  that release-profile build reads the configuration. The preflight guarantees
  `mold` exists on every route that reaches `uv run`.
- Whitaker's installer-managed toolchain is independent of the pin.

## Architectural rationale

The decision keeps one source of truth for each fact: the pin lives in
`rust-toolchain.toml`, the flags live in `.cargo/config.toml`, Make restates
them only where an assignment would otherwise displace them, and contracts hold
the three equal. Exclusions use the mechanism each route actually has, so none
depends on an action's default.
