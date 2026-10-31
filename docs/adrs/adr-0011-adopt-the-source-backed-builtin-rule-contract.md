# Architectural decision record (ADR) 0011: The source-backed builtin rule contract

## Status

Accepted. The first builtin Markdown pack runs inside one per-document
projection whose source-backed spans are verified against the original bytes,
tokenizes each eligible segment once, and reports findings under a policy layer
that decides selection, per-file exclusion, and suppression before any rule
sees a region.

## Date

2026-10-30.

## Context and problem statement

Roadmap item 2.3.1 asks for a starter pack of deterministic Markdown rules that
reuses the rule policy and source-backed diagnostic substrate later packs will
consume. Three concerns meet for the first time in that work, and each has a
plausible shortcut that is wrong in a way only an unlucky document reveals:

- **Where does a rule get its inputs?** RFC 0002 describes typed runtime
  objects, but the rule runner was an empty seam that received only a document
  and a configuration. Source bytes, the reported path, and the
  configuration-relative path all lived at the call site, so a rule could not
  produce a byte span or evaluate a per-file glob without widening the private
  boundary.
- **How much work happens per document?** A rule that walks the IR is simple to
  write. Five such rules walk the IR five times, and a sixth tokenizes prose
  that the fifth already tokenized. The cost is invisible in a unit test and
  linear in the number of selected rules in a repository.
- **When may a rule trust a span?** The extractor advertises byte spans it
  believes are source-backed. A stale extractor, a synthetic region, or a
  hand-built IR in a test can advertise a span whose bytes say something else.
  A rule that trusts the advertisement reports a span that does not contain the
  text it names, and the fix planner then splices the wrong bytes.

The pack also has to settle shared policy questions once, rather than per rule:
what `select` and `ignore` mean, which wins, how per-file globs are anchored,
what an empty `plugins` list does, and how suppression directives bind to
findings. Deciding these inside each rule would guarantee they diverge.

## Decision Drivers

- **Byte fidelity.** A diagnostic span is a promise about the original file.
  The promise must be checked, not assumed, and the check must happen before a
  rule can act on the segment.
- **One document, one index.** Adding a rule should add only its own matching
  cost, not another traversal of the IR or another tokenization of the prose.
- **Policy is not a rule concern.** Selection, exclusion, and suppression are
  decided once, before rules run, so every rule — builtin or third-party —
  observes the same world.
- **Deterministic, inspectable rules.** The starter pack must not import NLP
  components, download models, or make locale claims.
- **Reuse over new surface.** The projection and token model are private
  helpers beneath the existing runner; no new public API or persisted format is
  introduced.

## Requirements

- A rule receives typed canonical regions filtered by its declared target,
  immutable source bytes, the reported path, the configuration-relative path,
  and the effective configuration.
- A segment's advertised span is usable only when it lies inside the source
  and the addressed bytes decode to exactly the segment text. Otherwise the
  segment is synthetic with reason `source_mismatch`.
- The IR is projected once per document, and each eligible segment is
  tokenized once per document, regardless of how many text rules are selected.
- Selection follows `lint.select`, `lint.ignore`, and `lint.per-file-ignores`;
  `ALL` and code prefixes expand against the enabled builtin inventory; an
  ignore wins regardless of prefix length; a per-file glob is matched against
  the config-relative POSIX path; `plugins = []` disables the builtin pack.
- Suppression directives follow the RFC 0003 state machine: range toggles are
  per concrete code, repeated disables are idempotent, unmatched enables are
  no-ops, unclosed ranges last to end of file, `ignore-file` covers the whole
  document, and `ignore-next` consumes the next nonempty heading, paragraph, or
  table-cell unit even when no selected rule targets it.
- Filtering happens after rule state updates, so a suppressed heading still
  advances the heading-depth comparison.
- No new runtime dependency, no NLP import, and no Unicode normalization.

## Options considered

### Option A: Let each rule walk the IR and parse the policy it needs

Simplest to start, and the shortcuts compose badly. Traversal and tokenization
cost scale with the rule count; selection and suppression semantics drift
between rules; span verification is either duplicated or skipped. Rejected.

### Option B: Build a public rule-authoring API now

The long-term destination in RFC 0002. It would freeze public types for the
benefit of one pack, before a third-party pack exists to validate them.
Rejected for this slice; the private boundary preserves the option.

### Option C: One private projection, one policy resolution, typed rule packets

The runner projects the document once, resolves policy once, and hands each
selected rule a context carrying only what its target matches. Span
verification happens in the projection, so every rule inherits it. Chosen.

## Decision outcome / proposed direction

### Projection and verification

`stilyagi.engine.rule_projection` owns the single pass over the canonical IR.
It builds the node-id-to-span index and the inline-code span list from one walk
of `nodes`, then projects each region into a `RegionView` carrying its kind,
scope, attributes, and verified segments. A segment keeps its advertised span
only when [`_slice_matches`](../../python/stilyagi/engine/rule_projection.py)
proves the source slice decodes to the segment text; otherwise it becomes
`RegionSegment(span=None, ..., synthetic_reason="source_mismatch")`. The same
pass records the prose units that `ignore-next` may consume.

`stilyagi.engine.rule_view` remains the façade the rest of the engine imports.
It exposes `iter_regions`, `regions_for_target`, `ignore_next_units`,
`inline_code_spans`, and `raw_suppressions`; callers do not depend on the
projection module directly.

### Tokenization

`stilyagi.rules.tokens` defines the shared `Token` and `TokenizedSegment`
records so `RuleContext` can carry tokenized prose without importing the
builtin pack. `stilyagi.rules.builtin.text.tokenize_segments` tokenizes each
nonempty segment once, and the runner passes the result to rules that declare
`textual = True`. A second text rule reuses those tokens.

### The starter pack

- `MD001` (`heading-depth`) compares successive heading depths and reports a
  jump greater than one at the heading node's span. It carries a manual fix
  with no edits, because the `#` marker is not source-backed text and ADR 0009
  forbids editing it.
- `STY001` (`repeated-word`) finds maximal adjacent runs of the same
  alphabetic token within one segment, separated only by ASCII spaces or tabs.
  It reports the second token's span and offers one unsafe edit from the end of
  the first token through the end of the last, removing the suffix and leaving
  one word. Case, markup, line breaks, inline code, and synthetic text end a
  run rather than joining one.
- `TERM001` (`banned-term`) is opt-in, matches only whole configured
  single-word terms, folds case by default, offers an exact-case option, and
  never fixes. Malformed terms raise the established configuration error with
  the rule code and option name.

### Policy

Selection and suppression live in `stilyagi.rules.policy` and
`stilyagi.rules.suppression`. `resolve_policy` expands prefixes against the
enabled inventory (empty when `plugins` omits `builtin`), applies `ignore` after
`select`, and applies per-file globs to the config-relative path.
`resolve_suppressions` folds directives into per-code intervals, reusing the
projection's prose units for `ignore-next`. `filter_diagnostics` drops findings
whose primary span start falls in a suppressed interval.

## Goals and non-goals

Goals:

- Ship three deterministic rules with documented spans, severities, and fix
  applicability.
- Give later builtin and third-party packs one place to obtain verified
  regions, tokens, and policy decisions.
- Prove the pack runs without NLP and indexes the document once.

Non-goals:

- A public rule-authoring API, plugin loading, or a rule registry command.
- Frontmatter-aware heading policy, locale-aware terminology, or Unicode
  normalization.
- Auto-fixing heading depth or banned terms.
- A pack-level configuration table.

## Migration plan

None required. The pack runs behind the pre-release private runner boundary; no
public type, configuration key, or persisted format changes. Existing callers
keep using `check_execution` unchanged apart from the request object it now
constructs.

## Known risks and limitations

- Span verification costs one UTF-8 decode and comparison per segment. It is
  linear in document size and paid once per document, not once per rule.
- `ignore-next` binds to the next nonempty prose unit even when no selected
  rule targets it. That is deliberate — suppression must not depend on
  selection — but it can surprise a user who expected a no-op.
- `STY001` matches exact spelling only. Case-insensitive repetition remains a
  future policy decision, not an omission.
- The projection loads the whole region list into memory. Markdown documents in
  scope are prose-sized; a repository-sized single file would need streaming
  work this slice does not attempt.

## Architectural Rationale

The decision follows the repository's existing shape: the Rust extractor owns
canonical facts, Python owns policy and presentation, and the private boundary
between them carries typed values rather than dictionaries. Verifying spans in
the projection rather than in each rule means a new rule cannot accidentally
skip the check, and building the index once means the marginal cost of a rule
is its own matching logic. Keeping the façade (`rule_view`) stable while the
projection moved into its own module avoids a repository-wide change for an
internal improvement.

## References

- [RFC 0002: Stilyagi Python rule API](../rfcs/rfc-0002-stilyagi-python-rule-api.md)
- [RFC 0003: Stilyagi CLI contract](../rfcs/rfc-0003-stilyagi-cli-contract.md)
- [ADR 0009: Safe-fix planning and conflict resolution](adr-0009-safe-fix-planning-and-conflict-resolution.md)
- [Stilyagi design §7.2](../stilyagi-design.md#72-python-rule-api)
- [Roadmap item 2.3.1](../roadmap.md)
- [ExecPlan: Markdown rule starter pack](../execplans/2-3-1-markdown-rules-starter-pack.md)
