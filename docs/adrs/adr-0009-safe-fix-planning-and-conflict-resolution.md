# Architectural decision record (ADR) 0009: Safe-fix planning and conflict resolution

## Status

Accepted. Admissibility is bounded by a merged source-backed segment span; a
conflict aborts the whole file; the machine artefact owns standard output
alone; refusals travel on a separate channel from rule diagnostics; source is
read, spliced, and written as bytes; and the `--fix` exit status comes from a
verification re-lint rather than from the plan.

## Date

2026-09-28.

## Context and problem statement

Roadmap item 2.2.2 asks for safe-fix planning, conflict resolution, `--diff`,
and `--fix` over Markdown source-backed edits. The extractor already publishes
a canonical intermediate representation (IR) whose regions carry half-open
UTF-8 byte spans into the original source, and RFC 0003 §10 promises
`stilyagi check --fix` plus `--unsafe-fixes` and `--diff`. What none of those
documents settle is the set of questions that decide whether an automatic edit
is safe to apply at all:

- Which byte ranges may a rule offer to rewrite?
- When two rules want the same bytes, does one win or does the file lose?
- Where does a patch go when the user's pipeline reads it, and where do the
  diagnostics go instead?
- How is a refusal to fix reported, given that the diagnostic that prompted it
  was reported by a rule and remains well-formed?
- What does a byte offset mean when the file on disk is CRLF, carries a
  byte-order mark, or lacks a final newline?
- After `--fix` writes files, what is the exit status measured against?

Each has a plausible-looking shortcut that is wrong in a way no test notices
until a user is affected. A fix that edits bytes it cannot trace back to the
source silently corrupts prose. A fix that resolves conflicts by dropping the
losing edit makes a re-run produce different output from the first run. A
diagnostic summary printed onto standard output turns
`stilyagi check --diff | git apply` into a command that fails on a clean
repository, which the user will "fix" with `|| true` and permanently disarm. A
refusal published as a rule code becomes `--select`-able, letting a user
silence the evidence that a rule emits bad edits while the file still is not
fixed. And an exit status read off the plan assumes that applying a fix removes
its diagnostic — an assumption nothing tests and which a partial fix falsifies.

This record decides all six, together, because they are not independent. The
conflict rule only makes sense given the admissibility bound; the output-stream
split only makes sense given that a stream input is never written; and the exit
status only makes sense given the refusal channel.

## Decision Drivers

- **Safety over utility.** A refused edit costs a user one manual fix; a wrong
  automatic edit costs them their prose. Where the two conflict, refuse.
- **Byte fidelity is the whole contract.** RFC 0001's IR offsets are byte
  offsets into the original source. Any stage that re-reads, re-encodes, or
  newline-normalizes the source between extraction and writing breaks that
  contract silently.
- **Configurability must not become a suppression channel.** `--select` and
  `--ignore` exist so users can choose which rules run. They must not be
  reusable to hide the fact that a rule no longer works.
- **Rejection is the relaxable direction.** A rejected flag combination can be
  given meaning in a later release; one accepted with silent precedence cannot
  be withdrawn without breaking scripts that relied on the winner.
- **Proportional cost.** Re-linting the whole repository after `--fix` would
  double the cost of a run to answer a question about only the files it wrote.
- **Auditable output.** A large file with a defective rule must produce one
  line a reviewer can act on, not one line per paragraph.

## Requirements

### Functional requirements

- Only byte ranges that lie wholly inside a single source-backed segment of the
  original file may be rewritten.
- Touching source-backed spans are merged before admissibility is judged, so
  an edit spanning the join is admissible on the same terms as one inside
  either half.
- An edit that is out of bounds, cuts a UTF-8 sequence, targets a synthetic
  region, or whose segment text disagrees with the source is refused.
- Two non-identical edits that overlap cause the whole file to be left
  completely unmodified.
- Every refusal is reported, naming the rule codes responsible, and states that
  the file was not modified.
- `--diff` prints a patch `git apply` accepts and changes no source byte.
- `--fix` applies safe fixes; `--fix --unsafe-fixes` also applies unsafe ones.
- Refusals are reported on a channel that rule selection cannot reach.

### Technical requirements

- Source is read as bytes, decoded explicitly once, spliced on bytes, and
  written as bytes.
- Under `--diff`, and under `--fix` reading standard input, the machine
  artefact owns standard output alone and every diagnostic goes to standard
  error.
- A file read from standard input is never written to disk.
- `--fix` plans every file before writing any file.
- A write is conditional on the target still holding the bytes the plan was
  derived from.
- The `--fix` exit status is derived from re-linting the files this run
  actually mutated.

## Options considered

### Option A: Segment-contained edits, file-atomic conflict abort

Admissibility is containment within one merged source-backed segment span. Any
overlapping non-identical pair aborts the whole file. Diagnostics move to
standard error whenever standard output carries a machine artefact. Refusals
travel on a `fix_errors` sibling array in JSON and a distinct prefix in text.

This is the implemented option. Its cost is blast radius: one conflicting pair
blocks every unrelated safe fix in that file, and a heading-depth rule cannot
be expressed at all, because the source-backed segment of `## Section` is
`Section` and the `##` marker lies outside it.

### Option B: Node-span admissibility

Widen the bound from segment spans to intermediate-representation node spans,
so an edit may target any node. This was considered and rejected as vacuous:
the root node spans the entire document, so the "bound" admits every edit and
constrains nothing. A rule computing an offset in region-text coordinates
rather than source coordinates would pass this check and corrupt the file,
which is exactly the hazard the bound exists to catch.

### Option C: Skip the losing edit and keep the rest

On conflict, sort deterministically, drop the losing edit, and apply the
survivors. This preserves more of a file's available fixes than Option A. It
was rejected because it is only safe in the presence of a fixpoint loop, which
this slice does not have: a survivor that shifts the spans after it can make
the next run's plan differ from this one, and a tool whose output depends on
how many times it has been run is not auditable. Its determinism is also weaker
than it appears — it is achievable, but only by making the sort key the edit's
content rather than its meaning.

### Option D: Refusals as reserved rule codes

Report planning refusals as `FIX001`-style rule codes so they flow through the
existing diagnostic channel with no new plumbing. Rejected on three counts:
those numbers collide with Ruff's flake8-fixme, `FIX` is unreserved in RFC 0002
§12, and as rule codes the refusals would become `--select`-able and would have
to appear in `stilyagi rule CODE` and `stilyagi rules`, which RFC 0003
§§3.2-3.3 define in terms no engine report can satisfy.

| Topic                      | A: Segment bound | B: Node spans | C: Skip the loser | D: Rule codes |
| -------------------------- | ---------------- | ------------- | ----------------- | ------------- |
| Bounds a rule's offsets    | Yes              | No            | Yes               | Yes           |
| File left byte-identical   | Always           | N/A           | Never             | N/A           |
| Fixes preserved per file   | None on conflict | All           | Most              | All           |
| Stable across re-runs      | Yes              | Yes           | Only with a loop  | Yes           |
| Headings-autofixable       | No               | Yes, unsafely | No                | Inherited     |
| Refusals resist `--ignore` | Yes              | Yes           | Yes               | No            |

_Table 1: Safe-fix planning options compared across safety and auditability._

## Decision outcome / proposed direction

In the context of automatic Markdown source edits for v1, facing admissibility,
conflict handling, stream ownership, refusal reporting, byte fidelity, and exit
status, we decided for segment-contained admissibility with merged touching
spans, file-atomic conflict abort, machine-artefact ownership of standard
output, a dedicated refusal channel, byte-faithful read-decode-splice-write,
and a verification re-lint of mutated files, and against node-span bounds,
skip-the-loser resolution, and rule-code refusals, to achieve edits that are
always traceable to the original bytes and always auditable, accepting the
downside that a conflicting pair blocks a whole file and that heading-depth
rules cannot be auto-fixed at all.

**Admissibility.** An edit is admissible when its byte span is bounded by the
source, aligned to UTF-8 boundaries, wholly contained in one source-backed
segment, and when that segment's text equals the bytes the span covers. The
last condition is a cross-check of the extractor against the planner: a rule
computing an offset in the wrong coordinate system produces a span whose
containing segment does not match, and the check turns a silent corruption into
a refusal. Touching segments are merged before the test, so an edit across a
join is admissible exactly as one inside either half.

**A heading-depth rule cannot be auto-fixed under this model.** The
source-backed segment of `## Section` is `Section`, spanning bytes 3 to 10; the
`##` marker itself belongs to no source-backed segment. Any rule that adds or
removes heading markers therefore proposes an edit that no admissible span can
express, and must ship `manual` — reported, never applied. This is a
consequence of the model, not a gap in it, and it is recorded here so that
roadmap 2.3.1 is reviewed against the constraint before it starts rather than
discovering it mid-slice. Widening to node spans was considered (Option B) and
rejected as vacuous, so there is no configuration or flag that lifts this
restriction in v1.

**Conflicts abort the file.** Two non-identical edits that overlap leave the
file entirely unmodified, and every unrelated safe fix in that file is withheld
with it. Skip-the-loser (Option C) was rejected because it is only safe
alongside a fixpoint loop this slice does not have. The cost is blast radius,
and it is accepted deliberately: the conservative direction is the one a user
can recover from by fixing one thing by hand, where a nondeterministic plan is
not recoverable at all.

**Standard output belongs to the machine artefact.** Under `--diff`, the patch
goes to standard output and diagnostics and the summary move to standard error.
Under `--fix` reading standard input, the fixed document goes to standard
output and the report moves to standard error, because appending a report to
the bytes a user piped out would corrupt the one thing the command produces.
This is what keeps `stilyagi check --diff | git apply` usable; without it that
pipeline receives `0 diagnostics found` and fails on a clean repository.

**Refusals are not rule codes.** They travel in a `fix_errors` array beside
`diagnostics` in JSON, and in text output under a distinct non-rule prefix of
the form `identifier: path: rule_codes: message`. The identifiers are namespaced
`fix-error/` and are exempt from selection and suppression by construction, so
no user can silence the evidence that a rule emits bad edits. All but one carry
no exit-code weight of their own: the unfixed diagnostic already forces exit 1.
The exception is `write-failed`, an environmental failure rather than a
planning decision, which forces exit 2. The implemented set is:

| Identifier                    | Meaning                                         |
| ----------------------------- | ----------------------------------------------- |
| `fix-error/invalid-span`      | The span is out of bounds.                      |
| `fix-error/non-utf8-boundary` | The span cuts a UTF-8 sequence.                 |
| `fix-error/synthetic-span`    | The span is not inside source-backed text.      |
| `fix-error/source-mismatch`   | The segment's text disagrees with the source.   |
| `fix-error/overlapping-edits` | Two non-identical edits overlap.                |
| `fix-error/standard-input`    | The input was a stream, which is never written. |
| `fix-error/changed-on-disk`   | The file changed between planning and writing.  |
| `fix-error/write-failed`      | The filesystem refused the write.               |

_Table 2: The `fix-error/` identifiers and what each refusal means._

`fix-error/malformed-span` was the planning-time name for what implementation
split into `invalid-span` and `non-utf8-boundary`, so that a user can tell an
out-of-range span from a mid-character one; `source-mismatch` was added by the
extractor cross-check above.

`write-failed` is the one identifier that is not a planning decision. A
conflict refusal leaves the diagnostic standing and the run exits 1; a rejected
write is an environment fault -- a full or read-only filesystem -- so the run
exits 2, mirroring how the command already treats an unreadable source. The
distinction is why the executor marks it separately rather than folding it into
the refusal count.

**Source is bytes.** A file is read as bytes, decoded explicitly once into text
for extraction, spliced on bytes, and written as bytes. Byte-order marks, CRLF
line endings, and a missing final newline all survive a `--fix` run unchanged
except where an admitted edit touched them, and the byte offsets the IR
publishes remain meaningful end to end. Re-reading or re-encoding anywhere
after extraction would break that, so no stage does.

**Selection is orthogonal to fixing.** `lint.fixable` and `lint.unfixable` are
code-prefix lists that decide which diagnostics may contribute edits;
`--select` and `--ignore` decide which rules run at all. They are independent:
a rule excluded by `--ignore` produces no diagnostic and therefore no edit,
while a code excluded by `lint.unfixable` still produces its diagnostic and
still exits 1 — it is simply never planned. Keeping these separate is what
stops a fix setting from becoming a way to hide a finding.

**Exit status is measured, not assumed.** `--fix` performs one planning pass,
writes, then re-lints only the files it actually mutated and derives the exit
code from that re-lint. "0 when all found violations were fixed" (RFC 0003 §12)
is not computable in one pass without assuming that applying a fix removes its
diagnostic. This is deliberately not a fixpoint loop: if the re-lint surfaces
new fixable diagnostics they are reported, not applied, and the run says so.

## Goals and non-goals

- Goals:
  - Automatic edits that are always traceable to the original bytes.
  - A single documented answer to each of admissibility, conflict, streams,
    refusals, byte fidelity, and exit status.
  - Determinism: the same input produces the same plan on every run.
  - Refusals a reviewer can act on, at one line per file per identifier.
- Non-goals:
  - A fixpoint loop that re-plans until no diagnostic remains.
  - Auto-fixing markup outside source-backed segment text, including heading
    markers, list markers, and emphasis delimiters.
  - Per-edit conflict resolution, or any rule that lets the user choose a
    conflict winner.
  - Fixing non-Markdown surfaces; Python docstrings and Rust doc comments are
    extracted but not planned over in this slice.
  - Meaning-aware edit ordering; ordering is byte-positional only.

## Migration plan

The decision was implemented in five phases, each independently gateable.

1. **Kernel and admission.** `engine/fix_planning/splice.py` becomes the
   normative byte-splice kernel, with `admissibility.py` classifying each edit
   and `ir_view.py` providing the read-only typed view over the extractor's IR.
   Deliverable: an admitted edit set produces the fixed bytes, and each named
   refusal is reachable in a test.
2. **Selection and planning.** `selection.py` partitions a file's diagnostics
   by why each cannot contribute an edit, and `plan.py` merges touching spans,
   detects conflicts, and produces a `PlannedFile`. Deliverable: a plan carries
   its own refusals and its own replacement bytes, or no replacement at all.
3. **Preview.** `--diff` renders a Git-applicable unified patch from a plan and
   writes no file. Deliverable: `stilyagi check --diff | git apply` succeeds.
4. **Execution.** `fix_execution.py` performs the two-phase plan-then-write,
   with each write conditional on the target's bytes, and the command boundary
   re-lints what changed. Deliverable: `--fix` exit statuses follow the re-lint
   and a clean tree is never reported as modified.
5. **Documented contract.** RFC 0003 §10 records the `--fix --diff` rejection;
   the user's and developer's guides describe the flags, the refusal
   identifiers, and the stream contract. Deliverable: this record and the
   amended documents, reviewed together.

Phase 4 depends on 2 and 3; phase 5 depends on all of them. No phase changes
the extractor, so phase 1 can be reviewed against a frozen IR.

## Known risks and limitations

- **Blast radius.** One conflicting pair leaves the whole file unmodified,
  including fixes that had nothing to do with the conflict. Accepted; the
  counter `files_aborted_on_conflict` is reported so the user can tell this
  apart from a file with nothing to fix.
- **Heading-depth rules ship `manual`.** Recorded above. Roadmap 2.3.1 lists
  heading depth among its candidate rules and must be reviewed against this
  constraint before it starts.
- **The bound is a lossy proxy.** Containment in a segment span approximates
  the real hazard, which is a rule computing an offset in region-text
  coordinates. It is therefore paired with the segment-text cross-check rather
  than relied on alone, and both are needed: neither catches what the other
  does.
- **No fixpoint loop.** A single `--fix` run may leave fixable diagnostics that
  only appear once its edits shift the spans after them. The run prints a
  re-run note rather than converging.
- **Refusal messages are not machine-stable contract.** The `fix-error/`
  identifiers are; the surrounding prose is not, and the collapsed count
  `(N refused edit(s))` is presentation.
- **A stream input under `--fix` still exits 1.** Its planning diagnostic
  stands because the file was never written (see the exit-status decision). A
  user expecting a repaired document to exit 0 needs to capture standard output
  instead.

## Architectural Rationale

The decision keeps the fix workflow inside the boundary the rest of the system
already draws. Every rule that governs it is a statement about bytes and
provenance, not about modules: the IR publishes byte spans, so admissibility
asks what a span covers; the design document states the failure path as
"conflict or invalid edit yields diagnostics without mutation", so a conflict
aborts the file. Where a shortcut would have required amending a ratified
contract to look safe, the contract won.

The layering follows the same principle. `splice.apply_edits` is a narrow
kernel that assumes its input is already validated and does nothing but give
admitted edits deterministic byte semantics; admissibility, conflict detection,
and planning sit above it and can be tested without it. The command boundary
owns the exit status because the exit status is a statement about a run, not
about a file, and the reporting module that describes a mutating run computes
no status and writes no file — a reporter that could write would be a second
mutation path beside the executor.

Finally, the refusal channel exists because configurability and correctness are
different concerns. Selection flags let a user decide which opinions apply to
their repository; they must not let a user decide whether a rule is broken.
Putting refusals on a `fix_errors` sibling preserves that distinction, and it
is why the exit-2 usage error for `--fix --diff` is documented in the RFC
rather than left to the flag's help text: an undocumented exit path is a
contract violation even when the behaviour is right.

## References

- [Stilyagi design](../stilyagi-design.md) §4 and §7.3 — the failure path this
  record implements.
- [RFC 0001: Stilyagi IR](
  ../rfcs/rfc-0001-stilyagi-intermediate-representation.md) — the byte-span
  contract admissibility is defined against.
- [RFC 0002: Stilyagi Python rule API](../rfcs/rfc-0002-stilyagi-python-rule-api.md)
  §10 and §12 — identical-edit handling and the reserved code namespace.
- [RFC 0003: Stilyagi CLI contract](../rfcs/rfc-0003-stilyagi-cli-contract.md)
  §§10, 12 — the fix surface and the exit codes.
- [ADR 0005: Scope Markdown region vocabulary](adr-0005-scope-markdown-region-vocabulary.md)
  — which regions are source-backed.
