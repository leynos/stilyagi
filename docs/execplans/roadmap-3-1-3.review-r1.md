# Logisphere design review — roadmap 3.1.3, round 1

Verdict: 🔄 **Revise**. One structural blocker; several advisories. Status
remains DRAFT.

Citations verified against source in this worktree:

- `crates/stilyagi-markdown/src/suppression.rs` — grammar types/functions exist
  as described; `parse_comment_directive` is a pure function over stripped inner
  text. Hoist is a clean move.
- `crates/stilyagi-markdown/src/lib.rs:208-261` — `suppressions_from_candidates`
  assigns `s{n}` ids over accepted directives only; emits
  `suppression-blanket-forbidden` / `suppression-unknown-verb` /
  `suppression-span-invalid` as claimed.
- `crates/stilyagi-markdown/src/validation.rs:251-288` — origin/span validators
  produce `ir-suppression-origin-unresolved` / `ir-suppression-source-mismatch`
  and return `Result<(), Message>` (not `IrError`).
- `crates/stilyagi-ir/src/document.rs:30` — `suppressions` serializes
  unconditionally; `dump-ir` visibility is automatic. ✅
- `crates/stilyagi-tree-sitter/src/rust/helpers.rs:31-45` — `classify_doc_comment`
  returns `None` for plain `//`; filter is sound.
- Design §4 (lines 623-626) and developers-guide (lines 454-459) citations are
  accurate. Gate targets (`check-fmt`/`typecheck`/`lint`/`test`,
  `markdownlint`/`nixie`) match `Makefile` and `AGENTS.md`. ✅
- No standalone red-test commit is required; commit-after-green is compliant.
- No hand-written formatter file lists that could name nonexistent files.

## 🔴 BLOCKING — unconditional comment-node emission contradicts the plan's own no-churn invariant

WI-Python and WI-Rust instruct: for **each** swept comment node, emit a
source-backed `"comment"` IR node and build a candidate, **then** delegate to
`suppressions_from_candidates`. Node emission therefore happens *before* the
directive/`NotADirective` decision (that decision lives inside the shared
helper). As written this emits an IR node for **every** plain `#`/`//` comment,
not only directive-bearing ones.

This directly contradicts:

- Constraint: existing golden snapshots must not change.
- Risk mitigation: "Only fixtures that contain directives gain nodes ... files
  without directives are byte-for-byte unchanged."
- WI-Python acceptance: "existing Python snapshots unaffected."
- WI-Rust acceptance: "existing Rust snapshots for directive-free fixtures are
  unchanged."

It is concretely falsifiable: `crates/stilyagi-tree-sitter/src/rust/tests.rs:149`
shows an existing Rust fixture carrying `// stilyagi-disable-next-line …`, a
plain `//` line comment that is **not** a `stilyagi:` directive (no colon →
`NotADirective`). Under the described algorithm this comment — and any ordinary
`//`/`#` comment in any fixture — gains a new IR comment node, churning the
`stilyagi-extract` golden snapshots for directive-free files. Python/Rust do not
emit ordinary-comment IR nodes today, so this is also an unscoped change to IR
shape (extra nodes, altered node counts in `dump-ir`) beyond what design §4
requires.

Root cause is an interface coupling: `SuppressionCandidate` carries a
pre-assigned `origin` node id, which forces the caller to emit the origin node
before the grammar has classified the comment. Fix requires **gating node
emission on directive detection** so only comments whose trimmed inner text
begins with the canonical `stilyagi:` marker produce a comment node + candidate
(matching the grammar's own accept rule, so a non-directive like
`// see stilyagi: docs` still emits nothing). Reconcile this with the shared
interface — e.g. pre-detect the marker in the sweep, or have
`suppressions_from_candidates` report accepted candidates so the caller emits
origin nodes only for those. The plan must specify this precisely; the current
text is both internally contradictory and underspecified on the exact gate.

## 🟡 Advisories

1. **Parent linkage / `n0` assumption.** The sweep sets comment-node parent to a
   hard-coded `n0` and does not add the comment node to the parent's `children`
   vector. Confirm `n0` is guaranteed to be the emitted root for every input
   (including empty or malformed files where the module/root node may not be the
   first emitted id), and decide deliberately whether suppression comment nodes
   join `root.children`. This matters for the mixed-source `dump-ir` consumer
   (roadmap 3.2.3) that WI-Parity explicitly feeds: a node present in the flat
   `nodes` list but absent from the child tree renders inconsistently.

2. **Validation asymmetry.** `python/support.rs:54` `validate_ir_consistency` is
   a `debug_assert`-only harness (content hash, line index, region text). Wiring
   the shared `validate_suppression` there enforces the invariant only in
   debug/test builds, whereas Markdown validates in its real pipeline producing
   `Message`/IR errors. This is defensible (the builder controls origin and span
   by construction), but the plan should state that Python/Rust suppression
   validation is a build-time invariant check, not a runtime IR-error producer,
   so "same validation" is not mis-read as identical error surfacing.

3. **`suppression-span-invalid` scope.** Dropping `source` from the shared
   `suppressions_from_candidates` signature means the "span outside source"
   pre-check stays only in the Markdown adapter; Python/Rust never emit
   `suppression-span-invalid`. Acceptable (their spans come straight from nodes),
   but note it explicitly so the parity test does not assert that code
   cross-syntax.

4. **Parity fixture code choice.** WI-Parity proposes asserting `disable PUN201`
   across all three syntaxes. `PUN201` is a Markdown pun code; the grammar is
   code-agnostic so this works for a *shape* parity test, but using a neutral or
   per-language code would read less oddly. Cosmetic.

## Pre-mortem (Doggylump)

Most likely incident: implementer follows WI-Rust/WI-Python literally, emits a
node per comment, `cargo insta` shows churn across many directive-free
snapshots, and the churn is blessed to make gates green — silently changing IR
shape for every commented source file and defeating the "extracted once,
unchanged otherwise" contract. Prevention: the BLOCKING fix (gate emission on
the `stilyagi:` marker) plus the plan's existing instruction to treat unrelated
snapshot churn as a regression to investigate, not bless.

## Strongest alternative (Wafflecat)

Emit **no** IR comment node; instead let `IrSuppression.origin` reference the
nearest already-emitted enclosing node (or a documented sentinel) for
syntax-native directives. Trades away Markdown-identical origin semantics and
the source-byte origin guarantee, but sidesteps the node-emission/churn problem
entirely. The plan's chosen approach (real comment node) is better *provided*
emission is directive-gated — which is exactly the blocking fix. Recording the
alternative confirms the chosen path is sound once gated.
