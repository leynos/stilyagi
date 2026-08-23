# RFC 0006: Editorial policy vertical slices

## Preamble

- RFC number: 0006
- Status: Proposed
- Created: 2026-08-15
- Target: Stilyagi 0.2 and later
- Depends on:
  - [RFC 0001](0001-stilyagi-intermediate-representation.md)
  - [RFC 0002](0002-stilyagi-python-rule-api.md)
  - [RFC 0003](0003-stilyagi-cli-contract.md)
  - [RFC 0005](0005-grammar-capability-and-syntactic-api-extensions.md)
  - [ADR 001](../adr-001-spell-checking-provider.md)
  - [ADR 003](../adr-003-v1-contract-scope.md)

## 1. Summary

Stilyagi should treat bespoke editorial law as policy layered over source-
faithful extraction, provider-neutral language annotations, and conservative
fix planning. The core should not hard-code one grammar officiant's taste into
the extractor, the intermediate representation (IR), or the grammar provider.
Instead, the roadmap should include `df12-editorial-style`, a first-party lint
pack whose vertical slices prove Stilyagi can host opinionated spelling,
punctuation, person, imperative, and phrase-style rules
without losing the structural fast path.

`df12-editorial-style` serves two purposes:

- enforce the df12 house style; and
- demonstrate how the `astroid`-like API supports opinionated and logic-driven
  grammatical rules.

Every rule in the pack should ship disabled by default, like Clippy's
`pedantic` and `restriction` lint groups. Selecting the pack or an individual
rule should be an explicit project decision. Where a rule has an easily
identifiable inverse or variants, the rule should expose the choice as
configuration rather than hard-code only the df12 preference.

This RFC uses the following policy targets as the motivating pack:

- an opinionated dictionary override, using `en-GB-oxendict` as the example and
  including spellings such as `minimize`, `analyse`, `neighbour`, `compelled`,
  `enrol`, and `artefact`;
- a necessary-serial-comma rule that inserts an Oxford comma only when it aids
  understanding;
- comma rules for configured postposed subordinate clauses and for fronted
  dependent clauses introduced by subordinating conjunctions;
- a prose policy that prohibits first person, second person, and imperative
  mood in configured prose contexts; and
- six `write-good` gap probes: passive voice, E-Prime, lexical illusion,
  sentence-initial existential `there is` or `there are`, weasel words, and
  wordy phrases.

The RFC also proposes roadmap amendments that make these slices explicit. Those
amendments keep the current phase order, but add a policy showcase after the
grammar and spelling provider slices.

## 2. Problem

Can Stilyagi support deliberately opinionated editorial policies without making
those policies part of the core model?

The answer should be yes. The important distinction is between grammar facts
and policy decisions. A `CoordinationNode` can expose the items in a
coordination and whether a serial comma is present. It should not decide
whether a project requires a serial comma in every list. A `ClauseNode` can
expose a subordinate marker, clause span, and comma adjacency. It should not
decide that one project's "strong subordinate clause" category is universal
English. A spelling provider can check words against a dictionary. It should
not assume that `en-GB`, `en-GB-oxendict`, and project-specific house spellings
are interchangeable.

Without an explicit policy slice, Stilyagi risks three bad outcomes:

- bespoke rules reach through the public API and depend on backend objects;
- editorial rules duplicate source-mapping, clause, coordination, and phrase
  logic in each rule; or
- the core starts to encode one house style as if it were grammar.

This RFC proposes a route that avoids all three.

## 3. Current State

The current roadmap correctly builds Stilyagi from source-faithful extraction
toward richer language-aware rules. That sequence is necessary, but it does not
yet make the policy question explicit.

## 4. Goals and Non-goals

### 4.1. Goals

- Define vertical slices that let Stilyagi host opinionated editorial policy
  packs over Markdown, Python docstrings, and Rust documentation comments.
- Keep arbitrary non-doc code comments out of scope for now while allowing a
  post-v1 roadmap item to expand the extraction surface deliberately.
- Identify which requested policies need spelling, token, sentence, morphology,
  dependency, clause, coordination, lexicon, and phrase-matching support.
- Add roadmap amendments that prove the policy substrate through real rules
  rather than another horizontal abstraction layer.
- Preserve source-backed diagnostics and safe-fix discipline.
- Preserve the structural fast path when grammar and spelling rules are not
  selected.
- Treat uncertain grammar decisions as configurable diagnostics rather than
  claims of perfect grammatical truth.
- Ship every `df12-editorial-style` rule disabled by default, while permitting
  profiles to select rules explicitly.
- Make easily identifiable inverse policies and rule variants configurable.

### 4.2. Non-goals

- This RFC does not define a universal English grammar checker.
- This RFC does not enable any `df12-editorial-style` rule by default.
- This RFC does not add arbitrary non-doc comments to the current syntax scope;
  a post-v1 proposal may bring them into scope.
- This RFC does not require LLM-backed decisions in the deterministic core.
- This RFC does not require automatic rewrites for tone, voice, or mood.
- This RFC does not distribute Hunspell dictionaries, or equivalent supported
  dictionaries, with Stilyagi.
- This RFC does not make `write-good` compatibility a product promise. The six
  `write-good` rules are used as gap probes and acceptance examples.

## 5. Terminology

**Policy rule** means a rule that encodes project or team style rather than a
syntax, spelling, or grammar invariant.

**Policy profile** means a named bundle of selected rules and default
configuration, for example `editorial-strict` or `oxendict-docs`.

**`df12-editorial-style`** means the first-party, disabled-by-default lint pack
that both enforces the df12 house style and demonstrates rule authoring through
the `astroid`-like API.

**Necessary serial comma** means a serial comma required only when a configured
ambiguity heuristic says the comma helps understanding.

**Strong subordinate clause** is a policy label, not a grammar-node type. In
this RFC it means a postposed subordinate clause whose marker or construction
is configured as contrastive, concessive, causal, or otherwise rhetorically
strong enough to require a preceding comma.

**Source-backed fix** has the same meaning as in the existing RFC set: the edit
targets original source bytes, not synthetic flattened text.

## 6. Proposed Design

### 6.1. Capability alignment

| Policy target                                                    | Minimum Stilyagi surface                                                                    | Main missing work                                                                              |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Opinionated dictionary override, exemplified by `en-GB-oxendict` | Markdown, Python docstring, and Rust doc-comment regions; spelling provider; locale profile | Dictionary acquisition, provenance, locale mapping, acceptance fixtures, personal dictionaries |
| Necessary serial comma                                           | Tokens, POS, dependencies, `CoordinationNode`, source-backed comma insertion                | Ambiguity heuristics, confidence policy, preview diagnostics                                   |
| Comma before strong subordinate clauses                          | Tokens, POS, dependencies, `ClauseNode`, policy marker lists                                | Definition of strong clause policy, conservative fix applicability                             |
| Comma after fronted dependent clauses                            | Tokens, POS, dependencies, `ClauseNode`, source-backed insertion points                     | Clause boundary fidelity across Markdown and doc-comment flattening                            |
| First and second person prohibition                              | Tokens, POS, morphology, configured region targets                                          | Possessive determiners, quoted examples, procedural sections                                   |
| Imperative prohibition                                           | Sentences, tokens, POS, fine POS, lemmas, dependencies                                      | Imperative root heuristics, context targeting, manual-only fixes                               |
| `write-good` gap probes                                          | Mixed: lexicon, phrases, sentences, dependencies, morphology                                | Phrase-table primitives, disabled defaults, duplicate diagnostic control                       |

_Table 1: Capability alignment for the proposed editorial policy targets._

### 6.2. Proposed vertical slices

#### 6.2.1. Slice A: policy-rule substrate

This slice should make project-specific editorial policy pleasant to express
without grammar enrichment. It is the thin courtroom where later rules can
appear with their evidence.

Required work:

- Extend rule configuration so builtin and external rules can expose stable
  options such as `mode`, `severity`, `fix`, `ignored_contexts`, and
  `allowed_owner_kinds`.
- Require rules with an easily identifiable inverse or variants to expose that
  choice through `mode` or another typed option. A policy rule should not make
  the df12 preference its only enforceable behaviour.
- Ensure `RegionTarget` can target Markdown paragraphs, headings, list items,
  Python docstrings, Rust documentation comments, owner kinds, and natural
  language where known.
- Ensure suppressions apply consistently across all v1 prose surfaces.
- Make phrase, word, and token diagnostics report spans through `segments`, not
  through re-scanned source text.
- Extend rule metadata so `stilyagi rule CODE` can explain policy mode,
  fixability, capabilities, preview status, examples, and limitations.
- Keep structural-only policy rules from starting the grammar provider.

Representative rules for this slice:

- repeated word or lexical illusion;
- banned terms and weasel-word lists;
- simple wordy-phrase diagnostics;
- first-pass first-person and second-person lexical checks where morphology is
  not yet available.

Roadmap impact:

- Amend 2.3.1 so the Markdown starter pack includes policy substrate probes,
  not only structural rules.
- Amend 2.3.2 so rule metadata includes policy configuration and preview
  status.
- Amend 3.2.2 so docstring and documentation-comment rules reuse the same
  policy targeting model.

#### 6.2.2. Slice B: locale-aware spelling policy

This slice proves that Stilyagi can enforce an opinionated prose dictionary
override without merging spelling and grammar into one provider.

Required work:

- Add a `spelling` capability behind the provider planner, as described by ADR
  001.
- Add a generic, configurable dictionary-override mechanism and use
  `en-GB-oxendict` as its example opinionated profile.
- Provide a simple download and installation workflow for Hunspell
  dictionaries, or a supported equivalent, into the location defined by the
  Cross-Desktop Group (XDG) Base Directory Specification.
- Do not distribute dictionary assets with Stilyagi. Download them from their
  upstream source and record provenance and licensing in the user-facing
  documentation.
- Support repository-local personal dictionaries.
- Keep suggestions out of scope until offset fidelity and provider behaviour
  are stable.
- Add acceptance fixtures for Markdown, Python docstrings, and Rust
  documentation comments.
- Include the motivating spellings:
  - accepted: `minimize`, `analyse`, `neighbour`, `compelled`, `enrol`,
    `artefact`;
  - rejected variants only where the selected dictionary and policy make a
    clear choice.

Roadmap impact:

- Extend 4.4 with a locale-profile item after the diagnostic-only spelling
  capability.
- Make `en-GB-oxendict` an explicit example acceptance profile rather than
  relying on a generic `en` or `en-GB` dictionary.
- Document that arbitrary non-doc comments remain outside the current spelling
  surface, but may be added by a post-v1 extraction roadmap item.

#### 6.2.3. Slice C: `write-good` gap probes

This slice uses six `write-good`-style checks to expose missing primitives and
avoid designing only for the punctuation examples.

##### Passive voice

Passive voice needs morphology and dependency structure. A useful rule should
look for auxiliary-passive and nominal-subject-passive constructions, not
merely the sequence `was` plus participle.

Required work:

- `TOKENS`, `POS`, `MORPH`, and `DEPENDENCY` capabilities.
- A stable dependency abstraction for passive subjects and passive auxiliary
  tokens.
- Advisory diagnostics with no automatic active-voice rewrite.
- Duplicate suppression with E-Prime where both rules see the same auxiliary.

##### E-Prime

E-Prime prohibits forms of `to be`. It should be disabled by default because it
is a style constraint rather than a general correctness rule.

Required work:

- Token or lemma matching for `be`, `am`, `is`, `are`, `was`, `were`, `been`,
  and `being`.
- Rule-selection support that keeps the rule disabled unless selected by a
  profile or config.
- Context filters for code spans, API names, examples, and quoted material.
- Diagnostic coalescing with passive-voice checks.

##### Lexical illusion

Lexical illusion flags repeated adjacent words. It is simple, but it is a
source-mapping stress test.

Required work:

- Region flattening that can see across soft breaks while preserving original
  source spans.
- Markdown-aware exclusions for code spans, links, and tables when configured.
- Tests for repeated words split by inline markup or comment prefixes.
- Safe delete fixes only when the redundant token maps cleanly to source.

##### Sentence-initial existential `there is` or `there are`

This rule catches sentence openings such as `There is` or `There are`. A
regex-only rule is cheap, but a robust Stilyagi rule should benefit from
sentence segmentation and, later, dependency analysis.

Required work:

- `SENTENCES` and `TOKENS` for the first version.
- Optional dependency-based detection of existential `there`.
- Configurable severity, because reference prose often uses this construction
  deliberately.
- No automatic rewrite.

##### Weasel words

Weasel-word detection is primarily a lexicon policy rule.

Required work:

- Configurable word and phrase lists.
- Case, plural, and simple inflection handling where configured.
- Allowlists and quoted-material exclusions.
- A clear distinction between builtin defaults and project-provided policy.

##### Too wordy

Wordy-phrase detection exercises multi-token phrase matching and replacement
suggestions.

Required work:

- Phrase-table primitives over flattened region text.
- Source-backed spans for multi-token matches that cross segment boundaries.
- Optional replacement suggestions.
- Manual or unsafe fix applicability by default, with safe fixes reserved for
  mechanically obvious substitutions.

Roadmap impact:

- Add a policy-probe subsection to Phase 4 after the first grammar-provider
  wave.
- Treat the gap probes as preview rules until false-positive behaviour is known
  across real repositories.
- Ensure the rule testing framework has compact fixtures for lexical, phrase,
  sentence, and dependency rules.

#### 6.2.4. Slice D: person and imperative policy

This slice proves Stilyagi can express prose-person and mood constraints
without writing a full grammar checker.

Required work for first-person and second-person prohibition:

- Token and POS wrappers.
- Morphological person features where available.
- Fallback matching for possessive determiners such as `my`, `our`, and `your`.
- Region targeting so the rule can ignore code spans, examples, quoted text, or
  procedural sections.
- Configurable banned persons, such as `[1, 2]`.

Required work for imperative prohibition:

- Sentence, token, POS, fine POS, lemma, and dependency capabilities.
- A helper or recipe for likely imperative roots.
- Context targeting for headings, docstring summaries, ordered procedures, and
  usage examples.
- Manual diagnostics only. Automatic imperative rewrites tend to change tone or
  meaning.

Roadmap impact:

- Amend 4.2.3 so one showcase rule proves policy-oriented mood or person
  analysis, not only general grammar diagnostics.
- Add fixtures for Markdown, Python docstrings, and Rust documentation comments.
- Document that imperative and person policies are style laws, not default
  grammar-correctness checks.

#### 6.2.5. Slice E: clause and coordination punctuation

This slice is the grammar-officiant showcase. It proves that clause and
coordination helpers can support punctuation law while keeping policy decisions
out of the helper nodes.

Required work for necessary serial comma:

- `CoordinationNode` with items, conjunction, punctuation adjacency, item spans,
  and source-backed insertion points.
- Heuristics for when a missing serial comma creates a real comprehension risk.
  Start conservatively:
  - flag item-internal conjunctions;
  - flag item-internal commas or appositive material;
  - flag nested coordination;
  - flag category mixtures that make the final item bind ambiguously.
- A `mode = "necessary"` configuration option, separate from any blanket serial
  comma rule.
- Safe comma insertion only when the insertion point is unambiguous.

Required work for commas before strong subordinate clauses:

- `ClauseNode` with marker, root, subject, span, `preceded_by_comma()`, and
  source-backed insertion point.
- A policy marker list for configured postposed subordinate clauses.
- Separate modes for always-strong markers and semantically slippery markers.
  For example, `although`, `though`, and `whereas` may be suitable for safe
  insertion, while `because`, `since`, and `as` may need manual diagnostics.
- Severity defaults that reflect uncertainty.

Required work for commas after fronted dependent clauses:

- Reliable detection of sentence-initial subordinate clauses introduced by a
  subordinating conjunction.
- Clause-boundary detection that works over flattened Markdown and doc-comment
  text.
- Source-backed comma insertion after the dependent clause, not into synthetic
  analysis text.
- Fixtures for inline markup, soft breaks, doc-comment prefixes, and nested
  clauses.

Roadmap impact:

- Strengthen 4.2.2 so clause and coordination helpers expose enough information
  for policy rules without making policy decisions themselves.
- Add a preview punctuation-policy slice after 4.2.2 and 4.3.2.
- Require `dump-ir --include-grammar`, or an equivalent view, to explain why a
  clause or coordination helper was built.

#### 6.2.6. Slice F: `df12-editorial-style` and rule-author workflow

This slice delivers `df12-editorial-style` as a first-party pack for df12 house
style and as a worked example for code shepherds who want to implement their
own logic-driven grammatical rules without changing Stilyagi core.

Required work:

- Entry-point discovery for third-party policy packs.
- Pack-level metadata for required capabilities, disabled-by-default
  enablement, preview status, supported locales, and configurable variants.
- Rule-test helpers for spelling, phrase, grammar, diagnostic, and fix cases.
- Profile documentation that explains which rules are stable, preview, or
  project-specific.
- SARIF output that carries policy rule codes and messages without losing the
  source-backed spans.

Roadmap impact:

- Amend 5.1 so installed policy packs and every rule within
  `df12-editorial-style` stay inert unless selected.
- Amend 5.2 so rule-author tests cover grammar and spelling providers, not only
  structural rules.
- Amend 5.3 so CI reporting handles policy diagnostics consistently.

### 6.3. Proposed roadmap amendments

The current roadmap order should remain intact. The amendments below make the
policy path explicit.

#### 6.3.1. Amend existing roadmap items

Amend 2.3.1 to say that the first builtin Markdown rules should include
lightweight policy-substrate probes, such as repeated words, banned terms, and
simple wordy phrases, provided they do not require grammar enrichment.

Amend 2.3.2 to require rule metadata for policy configuration, preview status,
capability requirements, fix applicability, examples, limitations, and
configurable inverse or variant behaviour.

Amend 3.2.2 to require policy rules to state which v1 prose surfaces they
cover: Markdown, Python docstrings, Rust documentation comments, or some
subset. It should also state that arbitrary non-doc comments are out of scope
for now and may only enter the supported surface through a post-v1 roadmap item.

Amend 4.2.2 to require `ClauseNode` and `CoordinationNode` helpers to expose
policy-useful facts without carrying policy decisions. Helper nodes should know
spans, markers, heads, punctuation adjacency, and source-backed insertion
points. They should not know whether a project likes Oxford commas.

Amend 4.2.3 to include at least one policy-facing grammar rule in the showcase
set, such as first/second-person prohibition, imperative mood detection,
passive voice, necessary serial comma, or fronted-clause comma insertion.

Amend 4.4 to add generic dictionary-download and override support, followed by
an explicit `en-GB-oxendict` example acceptance profile, after the first
diagnostic-only spelling capability lands.

Amend 5.2 to include provider-backed rule test helpers for spelling and grammar
rules.

#### 6.3.2. Add the showcase-pack roadmap item

The canonical task plan is [roadmap item 4.5](
../roadmap.md#45-add-the-df12-editorial-style-showcase-pack). It adds the
disabled-by-default `df12-editorial-style` pack after the grammar and spelling
provider slices, covering policy configuration, the dictionary example, gap
probes, person and imperative rules, punctuation rules, and adoption guidance.
This RFC records the design intent; the roadmap remains the source of truth for
task breakdown, dependencies, and acceptance criteria.

### 6.4. Rule-code sketch

The exact codes can change, but `df12-editorial-style` could use this shape.
Every rule remains disabled unless a project selects it explicitly:

| Code       | Rule                                                             | Default status | Capabilities                                        |
| ---------- | ---------------------------------------------------------------- | -------------- | --------------------------------------------------- |
| `SPELL101` | opinionated dictionary override, exemplified by `en-GB-oxendict` | disabled       | spelling                                            |
| `PUN201`   | necessary serial comma                                           | disabled       | tokens, POS, dependency, coordination               |
| `PUN231`   | comma before configured strong subordinate clause                | disabled       | tokens, POS, dependency, clauses                    |
| `PUN232`   | comma after fronted dependent clause                             | disabled       | tokens, POS, dependency, clauses                    |
| `STY301`   | first- or second-person policy                                   | disabled       | tokens, POS, morphology                             |
| `STY302`   | imperative-mood policy                                           | disabled       | sentences, tokens, POS, fine POS, lemma, dependency |
| `WG101`    | lexical illusion                                                 | disabled       | structural or tokens                                |
| `WG102`    | weasel words                                                     | disabled       | lexicon                                             |
| `WG103`    | wordy phrases                                                    | disabled       | phrase table                                        |
| `WG104`    | E-Prime                                                          | disabled       | tokens or lemma                                     |
| `WG105`    | existential `there is` or `there are`                            | disabled       | sentences, tokens, dependency optional              |
| `WG106`    | passive voice                                                    | disabled       | tokens, POS, morphology, dependency                 |

_Table 2: Illustrative rule-code shape for the disabled-by-default policy pack._

## 7. Requirements

### 7.1. Diagnostics and fix policy

Policy diagnostics should not be fatal by default. The rule pack should support
`info`, `warning`, and `error`, but most grammar-aware policy rules should
start as `warning` or `info`.

Enablement and severity are separate. Every `df12-editorial-style` rule ships
disabled, even when its configured severity is `warning` or `error`. Where an
inverse or variants are easily identifiable, the rule configuration should
choose the enforced behaviour. Examples include requiring or prohibiting a
serial comma, selecting which grammatical persons are allowed, and choosing
which clause variants require punctuation.

Fixes should follow these rules:

- Spelling diagnostics are diagnostic-only in the first provider wave.
- Lexical illusion may offer a safe deletion only when the duplicate token maps
  cleanly to source bytes.
- Wordy phrase replacements should default to manual or unsafe.
- E-Prime, passive voice, person, and imperative diagnostics should not offer
  automatic rewrites in the first wave.
- Comma insertion may be safe only when the clause or coordination helper
  exposes one unambiguous source-backed insertion point.
- Rules must never insert punctuation into synthetic spaces produced by region
  flattening.

### 7.2. Testing strategy

Each slice should add fixtures that run through the real CLI, not only unit
helpers.

Minimum acceptance coverage:

- The `en-GB-oxendict` example dictionary override in Markdown, Python
  docstrings, and Rust documentation comments.
- Dictionary acquisition tests that prove supported dictionaries install into
  the XDG data-share location and are absent from Stilyagi distribution
  artefacts.
- Markdown inline markup, links, tables, blockquotes, and soft breaks for all
  source-backed diagnostics and fixes.
- Python and Rust doc comments with owner metadata, suppression directives,
  line prefixes, and malformed-source recovery.
- Necessary-serial-comma cases that distinguish simple lists from ambiguous
  lists.
- Fronted and postposed subordinate-clause comma cases.
- First-person, second-person, possessive-determiner, and imperative examples.
- Paired cases for each easily identifiable inverse or variant, proving that
  configuration selects the enforced behaviour.
- The six `write-good` gap probes across at least one Markdown fixture and one
  source-tree fixture.
- Provider-debug snapshots showing which capabilities were selected.
- Performance checks showing structural-only runs do not start grammar or
  spelling providers.

### 7.3. Compatibility and migration

This RFC does not change the v1 extraction contract by itself. It relies on the
accepted v1 surfaces:

- Markdown files;
- Python docstrings; and
- Rust documentation comments.

Arbitrary non-doc comments are out of scope for now. A post-v1 roadmap item may
bring them into scope, but it should define their extraction, ownership,
suppression, and false-positive policy. `df12-editorial-style` should not
quietly treat arbitrary code comments as supported merely because some
doc-comment machinery exists.

Existing structural rules remain unaffected. Grammar and spelling providers are
loaded only when selected rules require them.

## 8. Alternatives Considered

### 8.1. Put editorial policy into extractor nodes

Rejected. Extractor nodes should describe source and prose regions. They should
not know that one policy profile treats `whereas` clauses as strong or that
another profile allows first person in tutorials.

### 8.2. Expose raw spaCy objects to policy rules

Rejected. RFC 0005 already defines the provider-neutral grammar route. Policy
packs should consume Stilyagi-owned nodes so backend changes do not become API
breaks.

### 8.3. Ship a blanket Oxford comma rule as the only serial-comma model

Rejected. A blanket serial-comma rule may be useful as a separate policy, but
the motivating use case is a necessary-comma policy. Stilyagi should support
both by putting item structure in `CoordinationNode` and style decisions in the
rule.

### 8.4. Rewrite prose automatically

Rejected for the first wave. Passive voice, imperative mood, E-Prime, and
wordiness rules often require judgment. Stilyagi should flag them and provide
examples, not silently mutate authorial intent.

## 9. Open questions

- Which download metadata, integrity checks, and provenance requirements must
  ADR 001 define for dictionaries installed into the XDG data-share location?
- Should `df12-editorial-style` ship as a first-party external pack, or as a
  separately selectable builtin pack that exercises the same extension surface?
- What is the default severity for high-opinion punctuation rules?
- Which configuration shape best represents inverse policies and variants
  without multiplying rule codes unnecessarily?
- What evidence should a post-v1 proposal provide before arbitrary non-doc
  comments join the supported syntax surface?

## 10. Recommendation

Adopt the proposed vertical-slice design and add `df12-editorial-style` after
the grammar and spelling provider slices. Keep policy in explicitly selected
packs over source-backed, provider-neutral facts; keep every rule disabled by
default; and use the canonical roadmap item for implementation sequencing and
acceptance criteria.
