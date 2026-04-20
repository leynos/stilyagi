# Architectural decision record (ADR) 003: Ratify the v1 contract scope

## Status

Accepted.

## Date

2026-04-20.

## Context and problem statement

ADR 002 settled how Stilyagi crosses the Rust and Python boundary: one Python
package with an in-process PyO3 extension built through `maturin`.[^1] That
still left three narrower v1 contract questions open:

- which syntaxes Stilyagi v1 formally supports;
- whether JavaScript Object Notation (JSON) is the only allowed
  Rust-to-Python transport or the canonical debug and compatibility
  representation; and
- whether v1 formally supports English only or claims broader locale support.

Those questions matter because later roadmap slices depend on them
immediately.[^2] The first extractor, rule, and command-line interface (CLI)
work needs one stable answer for which surfaces are in scope on day one, what
`dump-ir` must emit, and which natural-language assumptions the first
sentence-aware rules may rely on without reopening contract debates in every
subsequent change.[^2]

The design document already recommends narrower answers than the current
Request for Comments (RFC) drafts in a few places. It recommends MDX remain
preview-only in v1, recommends JSON as the canonical debug and fixture form
rather than the mandatory hot-path transport, and gives only English a clear
v1 performance and support story.[^2] This ADR exists to make those answers
explicit and accepted before roadmap item 1.1.3 aligns the RFC text to match.

The main question is therefore:

Which syntax, IR transport, and locale promises should Stilyagi v1 make so the
remaining foundational work can converge on one coherent product contract?

## Decision drivers

- Keep the v1 promise narrow enough that early slices can ship without
  over-claiming unproven extractor and natural-language features.[^2]
- Preserve the distinction between the logical IR schema and any particular
  in-process transport implementation.[^2]
- Keep `dump-ir`, golden fixtures, and contract review deterministic and easy
  to diff through one canonical serialization format.[^2]
- Let the Rust-to-Python hot path stay efficient inside the accepted in-process
  PyO3 boundary rather than forcing JSON serialization on every call.[^1][^2]
- Give maintainers and users one explicit answer about whether MDX is part of
  the stable v1 support matrix.[^2]
- Avoid implying multi-locale natural-language support before the product has
  rules, test corpora, and performance evidence beyond English.[^2]
- Keep the architecture ready for later locale expansion without requiring an
  IR redesign when that work eventually lands.[^2]

## Options considered

### Option A: narrow v1 contract with preview-only MDX, canonical JSON, and English-only support

This option keeps the stable v1 syntax promise to Markdown, Python
docstrings, and Rust documentation comments. MDX remains preview-only. JSON is
the canonical debug, fixture, and compatibility form for the IR, but not the
mandatory transport for every in-process Rust-to-Python call. English is the
only formally supported locale in v1.

The strongest argument for this option is that it matches the design's stated
recommendation and keeps the first meaningful release narrow enough to prove
its architecture before promising more.[^2] It preserves a simple story for
`dump-ir`, golden fixtures, and contract tests without forcing serialization
overhead into every ordinary extension call. It also avoids implying that
later locale work is already supported merely because the architecture has a
place for locale metadata.

The main cost is that some attractive future-facing capabilities remain
explicitly out of the stable v1 promise. Users and maintainers must live with a
clear distinction between supported Markdown, Python, and Rust prose surfaces
and preview-only or deferred extensions.

### Option B: broader v1 syntax promise with full MDX support and JSON as the only transport contract

This option would treat MDX as a day-one supported syntax and keep JSON as the
only formal transport contract between Rust and Python.

The strongest argument for this option is conceptual simplicity. One transport
format and one broad Markdown-family promise are easy to describe.

The main weakness is that it over-claims what the current design says v1 has
earned. Full MDX support would create support expectations before the extractor
tests and recovery story exist, and mandatory JSON transport would turn a
useful debug and compatibility format into a hot-path performance tax even
inside the accepted in-process extension boundary.[^1][^2]

### Option C: best-effort multi-locale support in v1

This option would describe English as the default or best-tested locale while
leaving the door open for broader, unofficial support in other languages.

The strongest argument for this option is marketing breadth: it sounds less
restrictive than an English-only policy.

The main weakness is that it turns architectural possibility into a support
promise. The current design only defines concrete v1 performance expectations
and rule-planning assumptions for an already installed English model.[^2]
Calling broader locale support "best effort" would still create user and
maintainer expectations that the project cannot yet validate consistently.

| Topic | Option A: narrow v1 contract | Option B: broad syntax plus JSON-only transport | Option C: best-effort multi-locale |
| --- | --- | --- | --- |
| Matches the current design recommendation | Yes | No | No |
| Keeps MDX out of the stable day-one promise | Yes | No | Yes |
| Preserves JSON as canonical debug form without forcing hot-path serialization | Yes | No | Yes |
| Gives one explicit, testable locale promise for v1 | Yes | Partial | No |
| Minimizes rework risk for roadmap slices 1.2 and 2.x | Yes | No | No |

_Table 1: Candidate v1 contract scopes after ADR 002 fixed the packaging boundary._

## Decision outcome

Adopt the narrow v1 contract described in Option A.

Stilyagi v1 formally supports these prose surfaces:

- Markdown documents;
- Python docstrings; and
- Rust documentation comments.

Markdown with JSX (MDX) remains preview-only in v1. It is not part of the
stable day-one support promise.

The logical IR schema is the extractor contract. Canonical JSON remains
required for `dump-ir`, golden fixtures, compatibility checks, and contract
review, but it is not the only permitted in-process transport between the Rust
extension and Python runtime.[^2]

English is the only formally supported locale in v1. The architecture keeps
explicit locale and natural-language fields so additional locales can land
later without redesign, but broader locale support is deferred rather than
implied as best effort.

## Consequences

### Positive consequences

- Roadmap items 1.2 and 2.x can implement the mixed Rust and Python build
  spine, Markdown slice, and early docstring support against one explicit
  syntax matrix rather than a moving target.
- `dump-ir` and extraction fixtures keep one canonical, reviewable JSON form
  even if the hot path uses richer in-process objects.
- Users get a clear statement that MDX is not yet a stable v1 promise.
- Early rule and performance work can assume English without implying that
  unvalidated locales are supported already.

### Negative consequences

- The repository must explain the difference between stable syntax support and
  preview-only MDX rather than collapsing them into one broad marketing claim.
- Maintainers must carry a temporary mismatch between accepted ADR language and
  the older RFC wording until roadmap item 1.1.3 lands.
- Any future decision to make MDX stable or to claim broader locale support
  will require fresh evidence and an explicit contract update.

### Neutral or clarifying consequences

- This ADR does not define the exact in-memory object types or PyO3 signatures
  used for fast Rust-to-Python exchange.
- This ADR does not settle the final owner-metadata shape, grammar debug
  schema, or cache encoding details. Those remain later implementation
  questions.[^2]
- This ADR narrows the stable v1 promise; it does not prevent preview
  experiments or internal parser exploration so long as they are not presented
  as supported product behaviour.

## Goals and non-goals

### Goals

- Freeze the remaining v1 contract scope after the packaging boundary.
- Align the design, roadmap, user's guide, and developer's guide around one
  explicit answer.
- Keep MDX, transport details, and locale support narrow enough that later
  slices can build without contract churn.

### Non-goals

- This ADR does not amend RFC 0001, RFC 0002, RFC 0003, or RFC 0005. That
  alignment belongs to roadmap item 1.1.3.
- This ADR does not implement MDX parsing, extraction, or test coverage.
- This ADR does not add new locales, models, or language-specific rules.
- This ADR does not choose a specific non-JSON in-process transport shape.

## Known risks and limitations

- The RFC set still contains language that is broader or sharper than this ADR
  in a few places, so maintainers must treat this ADR and the design as the
  current source of truth until 1.1.3 lands.
- "English-only in v1" may disappoint some users, but an explicit limit is
  safer than implying support the project has not validated.
- MDX preview status still requires careful wording in user-facing
  documentation so preview exploration is not confused with stable support.

## Architectural rationale

These three decisions belong together because they define the remaining outer
edge of the v1 promise after packaging.

Syntax scope answers what Stilyagi commits to parse and lint. IR transport
policy answers how maintainers inspect and regression-test that extracted
contract. Locale policy answers what natural-language assumptions rules and
performance expectations may rely on in v1.

Taken together, they keep the product disciplined: narrow enough to ship,
inspectable enough to debug, and explicit enough that later roadmap items can
extend the system deliberately instead of inheriting fuzzy promises.

## Follow-on work

- Use this ADR as the normative answer for roadmap item 1.1.2.[^2]
- Amend RFC 0001, RFC 0002, RFC 0003, and RFC 0005 in roadmap item 1.1.3 so
  the narrower contract language matches this ADR and the design.[^2]
- Carry the stable syntax scope, JSON debug contract, and English-only locale
  promise into the mixed-package build spine and the first Markdown and source
  extraction slices.[^2]

## References

[^1]: [ADR 002: Ratify the packaging boundary](adr-002-packaging-boundary.md)
[^2]: [Stilyagi design](stilyagi-design.md)
