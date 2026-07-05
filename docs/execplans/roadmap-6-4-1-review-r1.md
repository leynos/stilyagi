# Logisphere design review — roadmap 6.4.1 ExecPlan (round 1)

Status: **Revise** (not approved). Two blocking defects; plan is otherwise
strong, correct on the design boundary, and design-conformant.

Verified against source in this worktree:

- `stilyagi_ir::RegionKind` — 11 variants, `pub const fn as_str`, `pub const ALL`,
  `TryFrom<&str>` (`crates/stilyagi-ir/src/region.rs`). No `document` variant.
  Matches the plan and RFC 0001 §6 / ADR 005. ✔
- `stilyagi_extract::RegionKind` — `#[non_exhaustive]`, three variants, hand-written
  `as_str`/`TryFrom` (`crates/stilyagi-extract/src/lib.rs:152–193`). ✔
- Tree-sitter literals at `python/mod.rs:318` (`"python_docstring"`) and
  `rust/builder.rs:246` (`"rust_doc_comment"`); `rust/builder.rs` import group
  matches the plan verbatim. ✔
- Behavioural-test shape is real: `document.ir().expect(...)` then `ir.regions`
  (public field on `IrDocument`), demonstrated in `ir_identity.rs:185–221` with
  `shared_python_source` / `shared_rust_source` fixtures. ✔
- `RustDocComment` spelling-coverage gap is real (`spelling_display.rs`, only
  `Document` + `PythonDocstring` cases). ✔
- Gate set (`check-fmt`/`typecheck`/`lint`/`test` + `markdownlint`/`nixie`) matches
  AGENTS.md §72–84, §156–184. ✔ No standalone red-test commit (mutate-observe-revert
  only; never commit a mutation). ✔

## Blocking defects

### B1 — Work item 2 names a non-existent test-registration file

The plan says to register the new `region_vocabulary.rs` in
`crates/stilyagi-extract/tests/extract/mod.rs`, "follow the existing `mod …;`
registrations there". **That file does not exist.** Module registration for this
crate's integration tests lives in `crates/stilyagi-extract/tests/extract_integration.rs`
and uses `#[path = "extract/<file>.rs"] mod <name>;` attributes, **not** bare `mod`.
A new file dropped into `tests/extract/` without an entry in `extract_integration.rs`
is **not compiled or run** — so the plan's core deliverable (the drift cross-check)
would silently never execute in `make test`.

Fix: register `region_vocabulary.rs` by adding
`#[path = "extract/region_vocabulary.rs"] mod region_vocabulary;` to
`crates/stilyagi-extract/tests/extract_integration.rs`; correct the file name
and the "bare `mod`" description.

### B2 — Work item 1 Red evidence names a guard that cannot fail under the prescribed mutation

Given the WI1 `as_str` implementation (`match self.ir_region_kind() {`
`Some(kind) => kind.as_str(), None => "document" }`),
the assertion in `shared_bridge_spelling_comes_from_ir` — for `Some(ir)`,
`k.as_str() == ir.as_str()` — is definitionally true whenever `as_str` forwards,
because `k.as_str()` *is* `ir.as_str()` by construction. The WI1 Red-evidence step
(mutate `stilyagi_ir::RegionKind::PythonDocstring`'s spelling, then "observe both
`shared_bridge_spelling_comes_from_ir` **and** the extract round-trip tests fail")
is wrong: a consistent IR rename propagates through the forward to *both* sides
of that equality, so `shared_bridge_spelling_comes_from_ir` keeps passing. Only
the extract `region_kind_*_round_trips_*` tests (forwarded `as_str` vs extract's
still hand-written `TryFrom`) actually fail under that mutation.

The named guard *does* have value as a regression guard against a future edit that
un-forwards `as_str` (reintroduces a hand-written literal) — but that is a different
mutation than the one the plan prescribes. As written, the implementer cannot
produce the claimed Red transcript for `shared_bridge_spelling_comes_from_ir`, which
breaks the plan's own "prove each guard bites" discipline.

Fix: correct the WI1 mutate-observe-revert step so the mutation that is recorded
actually makes the *named* test fail — i.e. either (a) attribute the IR-spelling
mutation only to the extract round-trip tests (the true guard for a consistent IR
rename), or (b) give `shared_bridge_spelling_comes_from_ir` a mutation that bites
it (hand-write a divergent literal into extract `as_str`, un-forwarding it), and
state which mutation exercises which guard.

## Advisory

- WI2 behavioural test: the shorthand `document.ir().regions` needs
  `document.ir().expect(...).regions` (accessor returns `Option<&IrDocument>`);
  mirror `ir_identity.rs:192`.
- WI2 coverage-gap fix: `ExpectedSpelling::RustDocComment => "rust_doc_comment"`
  already exists in `spelling_display.rs`; the region cases can reuse it rather
  than adding a new `RustDocCommentRegion` arm. Either is fine; the plan's
  "if reused" phrasing is loose.

Signposts: `logisphere-design-review` skill; `execplans` skill (novice-followable
standard); RFC 0001 §6; ADR 003/005; AGENTS.md §65–84, §156–184. Source verified
via direct inspection in the worktree (Memtrace/Leta not required for this
branch-local verification).
