# Architectural decision record (ADR) 0013: Prove the lint policy through readers and compiled fixtures

## Status

Accepted.

## Date

2026-11-07.

## Context and problem statement

Stilyagi's lint policy is spread across three files that no single tool reads
together: `Cargo.toml` declares the workspace `[lints]` tables, `clippy.toml`
declares the `disallowed-methods` restrictions, and the `Makefile` declares the
`RUSTDOC_FLAGS` default and the routes that apply it. A gate can pass while the
policy is wrong in ways no tool reports: a table can name a lint that does not
exist, a restriction can never match, a member can stop inheriting the tables,
or a recipe can stop passing the flags it computes.

The tests that guard this policy therefore have to answer two different
questions. Is the policy declared as intended, and is the declared policy
effective? Answering the second question means compiling code that violates the
policy, which is slow, needs a toolchain, and must not disturb the repository's
own build.

The first attempt at these tests read the three files directly in each test
module. That duplicated the parsing, let the contract test and the behavioural
test disagree about what the policy said, and turned every unreadable or
malformed file into an incidental traceback that looked like a broken test
rather than a broken policy.

## Decision drivers

- One interpretation of the policy, shared by every test that reads it.
- A failure to read the policy must be reported as a policy finding, with the
  reader and the path, not as an `OSError` or parser traceback.
- The behavioural proof must compile real code under the real policy, and must
  not depend on the repository's own build state.
- The proof must be safe to run twice at once in the same worktree.
- Diagnostics must be asserted on a stable contract, not on wording that
  changes between toolchain releases.

## Options considered

- **Read the files in each test module.** Rejected: it duplicates parsing and
  lets the two proofs drift apart.
- **Assert the policy text with snapshots.** Rejected: a snapshot of a manifest
  or a recipe churns on harmless formatting and does not prove the policy is
  effective.
- **Compile fixtures inside the repository workspace.** Rejected: a fixture
  that violates a denied lint would fail the repository's own gates, and a
  fixture that joins the workspace changes the member set the policy is about.
- **Compile fixtures in scratch crates that copy the workspace tables.**
  Adopted. Each crate declares an empty `[workspace]`, so it is detached from
  the repository, and copies the tables, so it compiles under the same policy
  the real members inherit.

## Decision outcome

The policy is read through one set of readers in
`tests/support/lint_policy.py`. Every reader takes a path and defaults to the
repository's file, and all file access goes through `_read_text` and
`_read_toml`, which convert an unreadable, undecodable or malformed file into a
`ReadingError` naming the reader and the path. The undecodable, missing and
unreadable cases are parameterized over every public reader that takes a path,
so each reader proves its own route to the shared helper rather than inheriting
a sibling's proof.

The workspace member set is not read from the `members` patterns. It comes from
`cargo metadata --no-deps --locked --offline` through `MetadataRunner`, a
callable seam, because a path dependency inside the workspace directory is a
member even when no pattern matches it. The invocation compiles nothing, writes
no lockfile and fetches nothing. A decoding failure at that seam is a
`ReadingError` too, so output that is not valid UTF-8 is a finding rather than a
`UnicodeDecodeError`. The selection over the returned document is pure and
lives in `tests/support/cargo_metadata_document.py`, which keeps the command
boundary and the untrusted-document boundary apart.

The policy is proved effective by compiling scratch crates that copy the
workspace `[lints]` tables. The fixtures are written by
`tests/support/lint_policy_fixtures.py`, which owns the source of each
violating binary and the libraries the binaries link, and writes them into a
caller-supplied base directory. The test module supplies a directory unique to
the run under `target/` and removes it afterwards, so two runs in the same
worktree cannot share a crate. Diagnostics are asserted by lint code, not by a
verbatim `.stderr` snapshot, because rustc's wording changes between releases
and the project rejects snapshots that churn on toolchain bumps.

The Make route is proved separately by evaluating the real recipe with
`--dry-run` against recording probes, so the `RUSTDOCFLAGS` a case asserts is
the value Make computes rather than a value the test restates.

## Consequences

- A new reader must be added to the parameterized failure cases, or its
  file-failure contract is unproven. The parameter list is the checklist.
- A new lint entry that the behavioural proof should cover needs a fixture in
  `lint_policy_fixtures.py`; the test module only selects and asserts.
- The behavioural proof needs a working toolchain and a compile slot. It is
  skipped when `cargo` is absent, and its per-invocation timeout is generous
  because a cold build waits in the shared admission pool.
- Scratch crates are written under `target/`, which Cargo ignores and Git does
  not track, and are removed when the module finishes.

## References

- [ADR 0004: Adopt layered Python linting](adr-0004-adopt-layered-python-linting.md)
  records the lint tiers this policy configures.
- [ADR 0011: Pinned nightly and the development build standard](adr-0011-pinned-nightly-and-build-standard.md)
  records the toolchain the behavioural proof compiles with.
- The `cargo metadata` reference:
  <https://doc.rust-lang.org/cargo/commands/cargo-metadata.html>
- The rustdoc lint reference:
  <https://doc.rust-lang.org/rustdoc/lints.html>
