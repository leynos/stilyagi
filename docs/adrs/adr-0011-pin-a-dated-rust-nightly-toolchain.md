# Architectural decision record (ADR) 0011: Pin a dated Rust nightly toolchain

## Status

Accepted. Stilyagi pins a dated Rust nightly and adopts the estate build
standard's `-Zthreads=8` compiler parallelism. The standard's Cranelift
development backend was trialled and is **rejected**: every build stays on the
default LLVM backend.

## Date

2026-10-30.

## Context and problem statement

Stilyagi is a Rust workspace of eight crates that exposes a PyO3 extension. The
Python package is the only consumer of that extension: `publish = false` on
every crate, and the wheels are built in CI by maturin. Nothing downstream
compiles against the crates or depends on a particular Rust release.

Issue #165 asks whether a stable toolchain is the right choice. Its opening
paragraph says the repository has no `rust-toolchain.toml`. That premise is
stale. PR #223 (`094c35c`) added `rust-toolchain.toml` pinning an exact stable
release and made Dependabot its owner, and PR #227 (`fb2e19f`) moved the pin
from `1.99.0` to `1.99.1`. The repository is therefore already on the issue's
Option 2 — a Dependabot-managed exact stable — so this ADR records whether to
keep it rather than whether to introduce a toolchain file.

The same history left `rust-version = "1.85"` in `[workspace.package]` and
`rust-version.workspace = true` in every crate. No CI job ever compiled with
1.85: the pins and every workflow used 1.99.x, three releases newer. The value
was an untested assertion, not a supported minimum.

The estate's Rust build standard (the `rust-build-defaults` concordat) asks
nightly-pinned repositories to use the parallel rustc frontend (`-Zthreads=8`)
and, where the full suite passes under it, the Cranelift codegen backend for
development builds. The concordat text was not reachable from this environment,
so its requirements are taken from the restatement in issue #165; the primary
text is not linked below. Stable rustc offers neither facility, so a repository
that stays on stable records a Cranelift exception and forgoes `-Zthreads=8`.
That is the choice under review.

## Decision drivers

- Adopt the parts of the estate build standard the workspace supports, and
  record an exception only where evidence requires one.
- Keep release artefacts, wheels and packaging on LLVM; the backend choice is a
  development-loop optimization, not a change to what ships.
- Keep CI deterministic and every toolchain movement reviewable in a pull
  request, with no silent drift.
- Preserve the fast local edit-build-test loop that a larger workspace would
  otherwise lose.
- Avoid inventing an MSRV contract that nothing tests and no consumer needs.

## Requirements

### Functional requirements

- `make build`, `make test`, the PyO3 extension, the Python suite, doctests and
  both trybuild suites must work on the pinned compiler.
- `make release` must build wheels on Ubuntu, macOS and Windows runners.
- Coverage must keep producing LLVM instrumentation.
- A toolchain bump must arrive as an ordinary pull request whose full CI run
  decides whether the bump is safe.

### Technical requirements

- The compiler channel is pinned to a dated night, not a moving `nightly` tag.
- `rustfmt` and `clippy` are installed with it.
- `-Zthreads=8` is the default in the Makefile and reaches every CI job that
  builds Rust through `setup-rust`.
- No profile selects the Cranelift codegen backend; a development backend that
  changes panic behaviour is not acceptable for this workspace.
- Coverage lanes need no backend override, because the default backend is the
  one they instrument.

## Options considered

### Option A: Pin a dated nightly

Set `rust-toolchain.toml` to `nightly-YYYY-MM-DD`, install the components the
build needs, and put `-Zthreads=8` in the Makefile default and the CI
`RUSTFLAGS`. The Cranelift development backend is part of this option as the
build standard states it; it was validated rather than assumed.

### Option B: Keep the Dependabot-managed exact stable

Retain the existing `1.99.1` pin and let Dependabot propose each stable
release. The repository keeps its Cranelift exception and does without
`-Zthreads=8`.

### Option C: Declare and test an MSRV with periodic review

Pick a minimum supported Rust version, add a CI lane that compiles with it, and
review the floor on a schedule.

### Option D: Pin a stable release and never move it

Freeze a stable compiler and do not accept bumps.

| Topic                         | Option A                       | Option B                   | Option C               | Option D             |
| ----------------------------- | ------------------------------ | -------------------------- | ---------------------- | -------------------- |
| `-Zthreads=8`                 | Yes                            | No                         | No                     | No                   |
| Cranelift development backend | Trialled; rejected on evidence | No                         | No                     | No                   |
| Release backend               | LLVM                           | LLVM                       | LLVM                   | LLVM                 |
| Movement is reviewable        | Yes, weekly Dependabot pull    | Yes, daily Dependabot pull | Manual, scheduled      | No                   |
| Compiler stability            | Nightly; may regress           | Stable                     | Stable                 | Stable               |
| MSRV contract                 | None asserted                  | None asserted              | Asserted and tested    | None asserted        |
| Extra maintenance             | trybuild snapshot review       | Minimal                    | An extra compiler lane | None, and silent rot |

_Table 1: Comparison of the toolchain options._

Option B is the status quo and is not wrong, but it permanently forgoes the
frontend parallelism for a repository with no stable-only constraint. Option C
would create an MSRV contract that no downstream consumer needs; the untested
`1.85` declaration already shows how such a value rots. Option D is the issue's
least-preferred outcome: it drifts behind and gains nothing an application
needs.

## Decision outcome

In the context of a PyO3 extension with no MSRV consumer, facing an estate
standard that reserves its compiler parallelism for nightly-pinned
repositories, the choice is **for** Option A: pin `nightly-2026-10-29`
(`rustc 1.101.0-nightly (92ffebece 2026-10-28)`) in `rust-toolchain.toml`,
install `rustfmt` and `clippy`, and set `-Zthreads=8` in the Makefile
`RUST_FLAGS` default and in every CI `setup-rust` call. The choice is
**against** the Cranelift development backend, which failed validation, and
**against** retaining the stable pin, declaring an MSRV, or freezing a stable
compiler. The cost accepted is that the compiler moves weekly under Dependabot
review and that trybuild diagnostics must be re-recorded when their wording
changes; release and coverage builds stay on LLVM by default.

### The Cranelift rejection

Cranelift was configured exactly as the build standard describes: the
`rustc-codegen-cranelift-preview` component installed,
`[unstable] codegen-backend = true` and
`[profile.dev] codegen-backend = "cranelift"` in a root `.cargo/config.toml`,
and the coverage steps overridden to LLVM. The workspace built, the trybuild
suites passed, and the Python extension imported. `make test` then failed in
`stilyagi-markdown`:

```text
tests::parser::markdown_parser_panics_are_contained_as_messages
```

The test forces a panic across the Python boundary and asserts that the caller
receives a message rather than an abort. Under the Cranelift development
backend the panic escaped the `catch_unwind` guard; the same test passed when
the identical tree was rebuilt with `CARGO_PROFILE_TEST_CODEGEN_BACKEND=llvm`.
The upstream `rustc_codegen_cranelift` README lists "Unwinding on panics" under
its unsupported features, which corroborates the mechanism: the backend enables
`-Cpanic=abort` and cannot honour the unwind-based containment this crate
relies on. A preview backend that changes a safety-relevant behaviour the suite
asserts is not a development-only detail, and a per-surface override would
leave every developer and every test run on the backend that failed. Cranelift
is therefore rejected outright rather than narrowed.

Component availability was not the obstacle: the manifest check found the
Cranelift component present for all three CI runner targets. The rejection is
behavioural.

### Component availability

The dated night was checked against the rustup distribution manifest for
2026-10-29 before adoption:

| Target                     | `rustfmt` | `clippy`  | `llvm-tools-preview` |
| -------------------------- | --------- | --------- | -------------------- |
| `x86_64-unknown-linux-gnu` | available | available | available            |
| `aarch64-apple-darwin`     | available | available | available            |
| `x86_64-pc-windows-msvc`   | available | available | available            |

_Table 2: Component availability in the 2026-10-29 nightly manifest._

The CI matrix runs `ubuntu-latest` (`x86_64-unknown-linux-gnu`), `macos-latest`
(`aarch64-apple-darwin`) and `windows-latest` (`x86_64-pc-windows-msvc`). The
toolchain file requests `rustfmt` and `clippy`; `llvm-tools-preview` is
installed by `setup-rust`'s own component list in CI, where the coverage
tooling needs it, and is not requested for local builds that do not instrument.

### Build surfaces

`pinned setup-rust` installs every item declared in `rust-toolchain.toml`
before adding the components passed to it, so CI and a developer's
`rustup`-driven checkout resolve the same compiler and the same two components.
`setup-rust` exports its `rustflags` input as `RUSTFLAGS`, which is how
`-Zthreads=8` reaches `make check-fmt`, `make lint`, `make test`,
`make release` and the coverage action.

`[profile.release]` is untouched and no profile names a codegen backend, so
wheels built by `make release` and the coverage lanes both use the default LLVM
backend. There is no root `.cargo/config.toml`; adding one purely to select a
backend was part of the rejected configuration.

### Validation evidence

The adoption was validated on the candidate night across every surface the
repository publishes:

| Surface                      | Where                        | Result                         |
| ---------------------------- | ---------------------------- | ------------------------------ |
| Workspace check, all targets | Local, nightly-2026-10-29    | Pass                           |
| Trybuild UI snapshots        | Local, nightly-2026-10-29    | Pass                           |
| Formatting, lint, typecheck  | CI `lint-test` (`smoke.yml`) | Pending                        |
| Rust and Python test suites  | CI coverage lane             | Pending                        |
| Coverage                     | CI pull-request lane         | Pending                        |
| Release build and wheel      | CI `release-smoke`, 3 OSes   | Pending                        |
| Mutation testing             | `workflow_dispatch`          | Pending                        |
| Cranelift development build  | Local, nightly-2026-10-29    | Fail: panic containment        |
| Cranelift coverage           | Local, nightly-2026-10-29    | Not run: rejection preceded it |

_Table 3: Validation evidence for the candidate night._

The local workspace check ran
`cargo check --workspace --all-targets --all-features` with
`RUSTFLAGS="-D warnings -Zthreads=8"` and exited 0. Both trybuild suites passed
without a `.stderr` change. The table is completed from the pull request's CI
run before merge; a "Pending" row is not evidence of success.

The night also demonstrated the cost this decision accepts. Its clippy promoted
lints that stable `1.99.1` did not enforce, failing `-D warnings` in files this
change does not otherwise touch: `try_from_instead_of_from_str` in
`stilyagi-ir` and `stilyagi-extract`, `missing_const_for_fn` in
`stilyagi-tree-sitter` and `stilyagi-test-support`, `collapsible_if` in
`stilyagi-tree-sitter`, and `map_unwrap_or` plus `used_underscore_items` in
`stilyagi-pyext`. The remediation was mechanical: a `FromStr` implementation
with the existing `TryFrom<&str>` left as a delegating shim, `const fn`,
let-chains, `map_or(0, ...)`, and a Rust function name without an underscore
whose exported Python module name is pinned with
`#[pyo3(name = "_stilyagi_rs")]`. No public surface or exported module name
changed. That is lint-remediation work a nightly pin can impose on unmodified
code; a stable pin would have deferred it until a stable release enforced the
same lints.

## Goals and non-goals

- Goals:
  - Adopt `-Zthreads=8` across the repository.
  - Keep release, wheel and coverage output on LLVM.
  - Keep toolchain movement explicit and reviewable.
  - Record why the build standard's Cranelift clause does not apply here.
- Non-goals:
  - Guaranteeing an MSRV, or making the crates build on older compilers.
  - Changing what ships in a wheel beyond the compiler that produces it.
  - Following the moving `nightly` tag.

## Migration plan

1. **Validate a dated night.** Exercise the full three-OS release matrix, the
   lint and test surfaces, coverage, the Cranelift development configuration
   and mutation testing on the candidate.
2. **Adopt the validated configuration.** Pin the night, add `rustfmt` and
   `clippy`, add `-Zthreads=8` to the Makefile default and the CI `setup-rust`
   calls, remove the untested `rust-version` declarations, and add contract
   tests over all of it. Ship no `.cargo/config.toml` and no Cranelift
   component.
3. **Record the decision.** Publish this ADR, link it from the contents index,
   and update the developers' guide and README.

## Known risks and limitations

- Nightly compilers regress. The dated pin limits exposure to one night, the
  seven-day Dependabot cooldown lets a bad night settle, and the full CI run
  decides each bump. A bump that fails is skipped, not forced.
- The repository is compiled by two nightlies: the project pin, and the separate
  nightly the Whitaker Dylint driver forces for `make lint`. Code must build on
  both, so an API stabilized only after Whitaker's night is unavailable. The
  candidate night surfaced this with `Option::map_or_default`, which compiles
  under the project pin but is still gated under Whitaker's; `map_or` works on
  both.
- The trybuild `.stderr` files record rustc's exact wording, so a nightly bump
  can fail `compile_time_ui` for a diagnostic change that is not a code defect.
  Every bump pull request reviews the snapshot diff and re-records only genuine
  wording changes.
- `-Zthreads=8` is an unstable flag. On this night rustc accepts it without a
  warning under `-D warnings`, but rustc 1.101's help text already points at
  `--jobs-frontend` behind `-Zunstable-options`. A future night may remove it;
  the bump pull request will surface that, and the replacement is a small
  Makefile and CI change.
- Removing `rust-version` means Cargo no longer refuses a manually selected
  older compiler. Building with `cargo +<version>` is unsupported;
  `rust-toolchain.toml` is the only supported channel.
- The Cranelift rejection is evidence about this workspace, not a claim that
  the backend is unusable generally. A future attempt should start from a
  passing `catch_unwind` test under the backend and revisit the panic-boundary
  tests before anything else.

## Architectural rationale

The decision follows the repository's actual constraints rather than the
default of "stable is safer". Stability protects consumers who compile against
a library; Stilyagi's only consumer is the wheel it builds itself. The frontend
parallelism applies to every local and CI build in a workspace of eight crates,
while release and coverage keep the LLVM backend that gives them their known
behaviour.

The Cranelift clause is the part of the standard that the workspace cannot
honour. Adopting it on the strength of "the suite is green" would have meant
discovering the panic-boundary failure later, in a developer's loop rather than
in this validation. Recording the failed test, the control run that isolates
the backend as its cause, and the upstream limitation is what turns a
preference into a decision.

## References

- [Issue #165: Investigate whether a stable toolchain is the right
  choice](https://github.com/leynos/stilyagi/issues/165).
- [PR #223: Pin the Rust toolchain exactly and let Dependabot move
  it](https://github.com/leynos/stilyagi/pull/223), the change that introduced
  `rust-toolchain.toml`.
- [PR #227: Bump rust-toolchain from 1.99.0 to
  1.99.1](https://github.com/leynos/stilyagi/pull/227), the last stable bump
  before this decision.
- `leynos/shared-actions` `setup-rust` at
  `2f47859bcf82ae8b5bc10b457683fbd589ca2e41`, the pinned action that installs
  the toolchain and exports `RUSTFLAGS`:
  <https://github.com/leynos/shared-actions/blob/2f47859bcf82ae8b5bc10b457683fbd589ca2e41/.github/actions/setup-rust/action.yml>.
- `actions-rust-lang/setup-rust-toolchain` at
  `9d7e65c320fdb52dcd45ffaa68deb6c02c8754d9`, which documents that every item
  in a toolchain file is installed before the action's own components:
  <https://github.com/actions-rust-lang/setup-rust-toolchain/blob/9d7e65c320fdb52dcd45ffaa68deb6c02c8754d9/README.md>.
- [Dependabot options reference: `rust-toolchain`
  ecosystem](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories),
  which lists `rust-toolchain.toml` and dated channels.
- [`rustc_codegen_cranelift`
  README](https://github.com/rust-lang/rustc_codegen_cranelift/blob/main/Readme.md),
  whose "Unwinding on panics" entry under unsupported features explains the
  validation failure.
- The estate `rust-build-defaults` concordat (BD-001 to BD-006) was not
  reachable from this environment; its requirements are taken from issue #165.
