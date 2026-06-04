# Architectural decision record (ADR) 002: Ratify the packaging boundary

## Status

Accepted.

## Date

2026-04-20.

## Context and problem statement

Stilyagi is intended to ship as a mixed Rust and Python tool: Rust owns
source-faithful extraction, spans, and intermediate representation (IR)
construction, while Python owns configuration, rule execution, plugin loading,
diagnostics, and output rendering.[^1]

The design document already recommends a Python-distributed application with a
Rust extension built through PyO3 and `maturin`.[^1] The current repository
also already reflects that recommendation operationally. `make build` runs
`maturin develop`, `make release` runs `maturin build`, and the developer's
guide describes `crates/stilyagi-pyext/` as the bridge crate that compiles the
package-scoped `stilyagi._stilyagi_rs` module.[^2][^3]

What the repository lacks is an accepted decision record that says this
boundary is not merely a recommendation. That gap matters because later roadmap
steps depend on one stable answer to the build and runtime boundary question:
should Stilyagi v1 run as one Python package with an in-process PyO3 extension,
or should Python cross the boundary by invoking a separate Rust helper binary?

The main question is therefore:

Which packaging boundary should Stilyagi v1 adopt for its build and runtime
model, so later work can assume one coherent architecture without re-opening
the transport choice in every slice?

## Decision drivers

- Preserve a strict in-process boundary between Rust-owned extraction and
  Python-owned analysis.[^1]
- Keep development and release builds aligned with one packaging workflow
  rather than separate local and production paths.[^2][^3]
- Support Python plugin discovery and virtual-environment alignment without
  separate helper-binary lifecycle management.[^1]
- Keep the product offline after installation, without runtime process
  bootstrapping or external helper orchestration.[^1]
- Produce one cross-platform distribution story for Linux, macOS, and
  Windows wheels.[^1]
- Keep JSON as the canonical debug and test representation for `dump-ir`,
  golden fixtures, and contract review without forcing JSON to be the only
  hot-path transport.[^1]
- Avoid a packaging model that would blur which side owns spans, source maps,
  and extraction failures.

## Options considered

### Option A: Python package with an in-process PyO3 extension built by `maturin`

This option keeps the Rust and Python boundary in-process. Rust is compiled
into the Python distribution as the `_stilyagi_rs` extension module, with
`maturin` handling local development installs and wheel builds.[^1][^2][^3]

The strongest argument for this option is architectural and operational
alignment. It matches the current design, the current Makefile, and the current
developer workflow. It also keeps Python plugin loading, configuration
discovery, and environment selection in the same Python runtime that executes
rules, while still letting Rust own extraction, byte accounting, and IR
construction.[^1][^2][^3]

The main cost is mixed-package complexity. Contributors must manage both Python
and Rust toolchains, and wheel-building remains part of normal release work.
That cost is already accepted elsewhere in the design.[^1]

### Option B: Python package that shells out to a separate Rust helper binary

This option would keep the Python rule engine as the primary package surface,
but move extraction across a process boundary. Python would invoke a Rust
binary, most likely through JSON or another serialized transport, for every
extraction request or batch.

The strongest argument for this option is separation of failure domains. A
helper process can be debugged independently, and it avoids Python extension
linkage concerns during early development.

The main weaknesses are operational rather than theoretical. This option would
create a second artefact to build, package, locate, and version. It would make
virtual-environment alignment harder, complicate entry-point-backed plugin
workflows, and turn an internal build-boundary question into runtime helper
process management. It would also push Stilyagi toward JSON-as-mandatory
transport when the design explicitly recommends keeping JSON canonical for
debugging and tests rather than for every in-process call.[^1]

### Option C: Rust-first executable embedding Python

This option would move the primary entrypoint to Rust and embed Python for
rules and plugins.

The main strength is a single native executable entrypoint. The main weakness
is that it works against Stilyagi's stated product shape: a Python-distributed
tool with Python-authored rules and plugins. It would make plugin discovery,
virtual-environment alignment, and Python packaging materially harder for v1,
which is why the design already rejects it.[^1]

| Topic                                                             | Option A: PyO3 plus `maturin` | Option B: helper binary | Option C: Rust executable embedding Python |
| ----------------------------------------------------------------- | ----------------------------- | ----------------------- | ------------------------------------------ |
| Matches current repository workflow                               | Yes                           | No                      | No                                         |
| Keeps one Python package install surface                          | Yes                           | Partial                 | No                                         |
| Keeps plugin discovery in the active Python environment           | Yes                           | Partial                 | Weak                                       |
| Requires runtime helper-process management                        | No                            | Yes                     | No                                         |
| Keeps JSON as canonical debug form rather than mandatory hot path | Yes                           | Weak                    | Partial                                    |
| Fits the current design recommendation                            | Yes                           | No                      | No                                         |

_Table 1: Packaging-boundary trade-offs for Stilyagi v1._

## Decision outcome

Adopt a Python-distributed package with an in-process PyO3 extension, built and
released with `maturin`, as the Stilyagi v1 packaging boundary.

Stilyagi v1 will not rely on a separate helper binary for normal extraction or
analysis execution. The runtime boundary is one Python process importing one
compiled Rust extension module.

JSON remains the canonical debug, test, and contract representation for IR
output, especially for `dump-ir`, golden fixtures, and contract review, but it
is not the required hot-path transport between Rust and Python.[^1]

## Consequences

### Positive consequences

- Later roadmap items may assume that Rust-to-Python calls cross an extension
  boundary, not a subprocess boundary.
- `make build` and `make release` remain the canonical local and release
  workflows, rather than temporary stand-ins for a future helper-binary path.
- Python plugin discovery continues to operate in the same environment that
  loads and runs the application.
- Documentation can make a simple user-facing promise: install one Python
  package, not a Python wrapper plus a separately managed extractor binary.

### Negative consequences

- Mixed-language build complexity is now a deliberate part of the project
  rather than a provisional inconvenience.
- Wheel-building and extension compatibility are release-critical concerns from
  the start.
- Contributors cannot treat the Rust side as an independently deployable tool
  without proposing a later architectural change.

### Neutral or clarifying consequences

- This ADR does not decide the exact in-memory transport types used between the
  extension and Python. It only rejects helper-binary transport as the normal
  v1 runtime boundary.
- This ADR does not settle the remaining v1 contract questions about syntax
  scope, locale policy, or the exact debug-versus-runtime transport semantics.
  Those remain roadmap item 1.1.2 work.[^4]
- This ADR does not force immediate repository reshaping into the long-term
  multi-crate layout from the design document. That work starts in roadmap item
  1.2.x.[^4]

## Goals and non-goals

### Goals

- Freeze the v1 packaging boundary so later work does not revisit it
  piecemeal.
- Align the roadmap, design, developer guidance, and user-facing packaging
  promise around one accepted answer.
- Reject helper-binary transport for normal v1 execution.

### Non-goals

- This ADR does not implement the mixed-package skeleton from roadmap item
  1.2.1.
- This ADR does not define the final IR transport details for every internal
  call site.
- This ADR does not amend the RFCs beyond what later roadmap steps may do.
- This ADR does not introduce any new build commands, binaries, or helper
  services.

## Known risks and limitations

- The repository still carries the operational cost of a mixed Rust and Python
  toolchain, and this ADR makes that cost explicit rather than provisional.
- Cross-platform wheel support remains a release risk that later validation
  work must cover.[^1]
- If future evidence shows that the extension boundary cannot satisfy the
  project's packaging or performance needs, changing course will require a new
  ADR because later slices will build on this accepted boundary.

## Architectural rationale

This decision fits Stilyagi's architecture in four ways.

First, it preserves the intended ownership split: Rust stays close to source
fidelity and extraction, while Python stays close to rule execution, plugin
loading, and output rendering.[^1]

Second, it matches the already-adopted build spine. The repository is not
choosing a new path here; it is ratifying the path already encoded in
`make build`, `make release`, and the developer guide.[^2][^3]

Third, it keeps JSON in the right place. Stilyagi still needs canonical JSON for
`dump-ir`, contract review, and regression fixtures, but it does not need to
pay serialization costs for every ordinary Rust-to-Python call merely to
preserve a subprocess boundary.[^1]

Fourth, it keeps the user-facing story simple. Stilyagi installs as one Python
package with an embedded extension instead of as a Python wrapper that must
discover, launch, and version a second runtime artefact.

## Follow-on work

- Use this ADR as the packaging assumption for roadmap item 1.2, which creates
  the mixed-package skeleton and first bridge call.[^4]
- Resolve the remaining v1 contract questions called out in roadmap item 1.1.2,
  especially IR transport policy details and locale policy.[^4]
- Update RFCs in roadmap item 1.1.3 so their narrower contract language agrees
  with the accepted boundary.[^4]

## References

[^1]: [Stilyagi design](stilyagi-design.md)
[^2]: [Makefile](../Makefile)
[^3]: [Developer's guide](developers-guide.md)
[^4]: [Roadmap](roadmap.md)
