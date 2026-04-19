# RFC 0005: Grammar capability and syntactic API extensions

## Preamble

- RFC number: 0005
- Status: Proposed
- Created: 2026-04-19
- Target: Stilyagi 0.2
- Depends on: [RFC 0001](0001-stilyagi-intermediate-representation.md),
  [RFC 0002](0002-stilyagi-python-rule-api.md)
- Primary backend for v1 implementation: spaCy

## 1. Summary

Stilyagi should extend its rule API with a grammar layer that exposes
backend-neutral sentence, token, phrase, clause, and coordination nodes. The
layer should support part-of-speech (POS)-only rules, morphology-aware rules,
dependency-aware rules, and higher-level syntactic convenience nodes without
making spaCy classes part of the public API.[^1][^2]

The public model should be astroid-like in spirit: navigable nodes, stable
properties, source spans, parent or child relationships, visitor hooks, and
derived helper methods. The goal is not to reproduce spaCy's concrete class
layout. The goal is to give rule authors one stable Stilyagi-owned abstraction
that can survive backend changes and still map every diagnostic or fix back to
real source text.[^3]

spaCy should be the first production backend because it can provide sentence
segmentation, POS tagging, fine-grained tags, morphology, lemmatization,
dependency parsing, and token navigation from one Python-native pipeline.[^1]

## 2. Problem

The initial Stilyagi rule API supports regions and lightweight text analysis.
That is enough for structural rules and simple editorial checks, but it is not
enough for grammar-aware prose linting.

Some useful rules need only tokenization and POS:

```text
Avoid intensifier adverbs before weak adjectives.
Flag repeated adjectives in noun-phrase candidates.
Prefer imperative verbs in docstring summaries.
Detect noun-stack candidates.
```

Other rules need deeper syntactic structure:

```text
Detect passive voice.
Detect possible dangling modifiers.
Check subject-verb agreement.
Require Oxford commas in coordinated noun phrases.
Flag ambiguous pronoun antecedents.
Handle fronted subordinate clause punctuation.
```

Today a rule author would have to choose between two poor options:

- stay inside the current structural API and give up on richer syntax-aware
  checks; or
- reach through Stilyagi and depend directly on spaCy objects and labels.

The first option makes the rule surface too weak. The second freezes the public
API to one backend and leaks provider details into user code.

## 3. Goals

- Expose canonical POS tags through a stable `UPos` enum based on Universal
  Dependencies (UD) UPOS.[^4]
- Expose provider-native fine POS tags without making them the canonical
  cross-provider contract.
- Expose morphological features through a backend-neutral `MorphFeatures`
  object.
- Expose dependency structure through navigable token nodes.
- Expose higher-level convenience abstractions for noun phrases, clauses, and
  coordinations.
- Let each rule declare required grammar capabilities.
- Ensure that diagnostics and fixes always map back to source-backed spans.
- Support a spaCy backend without making spaCy classes part of the public rule
  API.

## 4. Non-goals

- This RFC does not add full semantic interpretation.
- This RFC does not require coreference resolution in v1.
- This RFC does not promise perfect grammar checking.
- This RFC does not add large language model (LLM)-backed grammar decisions to
  the deterministic core.
- This RFC does not require Stilyagi to serialize spaCy `Doc` objects into the
  intermediate representation (IR). spaCy's `Doc` owns token annotations while
  `Token` and `Span` are views over that underlying data, which makes them a
  poor long-lived interchange format for Stilyagi.[^2]

## 5. Proposed design

### 5.1. Capability model

Stilyagi should define the following grammar capabilities:

```python
class Capability(Enum):
    SENTENCES = "sentences"
    TOKENS = "tokens"

    POS = "pos"
    FINE_POS = "fine_pos"
    LEMMA = "lemma"
    MORPH = "morph"

    DEPENDENCY = "dependency"

    NOUN_PHRASES = "noun_phrases"
    CLAUSES = "clauses"
    COORDINATION = "coordination"

    COREFERENCE = "coreference"  # reserved, not v1
    SEMANTIC_LEXICON = "semantic_lexicon"
```

The planner should treat these relationships as normative:

- `POS` implies `TOKENS`.
- `FINE_POS` implies `POS`.
- `DEPENDENCY` implies `TOKENS` and `SENTENCES`.
- `NOUN_PHRASES`, `CLAUSES`, and `COORDINATION` require `DEPENDENCY` or a
  provider-specific equivalent.
- `MORPH` may imply `POS` for some providers, but rules must declare both when
  they need both.

The planner must reject a rule when the configured provider cannot satisfy its
declared capabilities.

Example error:

```text
Rule GRAM301 requires DEPENDENCY and MORPH, but provider "nltk" supplies only
TOKENS, POS, and FINE_POS.
```

#### Mapping to the existing planner vocabulary

RFC 0002 already defines the current capability-planner vocabulary. Until the
planner implementation and RFC 0002 are amended in the same change, that older
surface remains the canonical source of truth for shipped capability
constants.[^1]

This RFC proposes the grammar-facing extension to that vocabulary. The names
map as follows:

| RFC 0005 name      | Current RFC 0002 planner name | Relationship                                            |
| ------------------ | ----------------------------- | ------------------------------------------------------- |
| `SENTENCES`        | `SENTENCES`                   | Same meaning                                            |
| `TOKENS`           | `TOKENS`                      | Same meaning                                            |
| `POS`              | `POS`                         | Same meaning                                            |
| `MORPH`            | `MORPH`                       | Same meaning                                            |
| `LEMMA`            | `LEMMAS`                      | Same capability, singularized for grammar-node examples |
| `DEPENDENCY`       | `DEPENDENCIES`                | Same capability, singularized for grammar-node examples |
| `FINE_POS`         | No current equivalent         | New capability proposed by this RFC                     |
| `NOUN_PHRASES`     | No current equivalent         | New capability proposed by this RFC                     |
| `CLAUSES`          | No current equivalent         | New capability proposed by this RFC                     |
| `COORDINATION`     | No current equivalent         | New capability proposed by this RFC                     |
| `COREFERENCE`      | No current equivalent         | Reserved for later work                                 |
| `SEMANTIC_LEXICON` | No current equivalent         | Optional later capability                               |

_Table 1: Mapping between RFC 0005 capability names and the existing RFC 0002
planner vocabulary._

The implementation should not ship both plural and singular spellings as
independent public constants. When this RFC is implemented, the planner types,
constants, and RFC 0002 should be updated together so one canonical enum or
constant set remains visible to rule authors.

### 5.2. Canonical enums

#### `UPos`

Stilyagi should expose a `UPos` enum based on the UD universal POS inventory:

```python
class UPos(Enum):
    ADJ = "ADJ"
    ADP = "ADP"
    ADV = "ADV"
    AUX = "AUX"
    CCONJ = "CCONJ"
    DET = "DET"
    INTJ = "INTJ"
    NOUN = "NOUN"
    NUM = "NUM"
    PART = "PART"
    PRON = "PRON"
    PROPN = "PROPN"
    PUNCT = "PUNCT"
    SCONJ = "SCONJ"
    SYM = "SYM"
    VERB = "VERB"
    X = "X"
```

UD defines these as cross-linguistic coarse categories and expects morphology
and other grammatical information to carry the extra detail.[^4]

#### `Dep`

Stilyagi should expose a normalized dependency enum for relations that builtin
rules are expected to use frequently.

```python
class Dep(Enum):
    ROOT = "root"
    NSUBJ = "nsubj"
    NSUBJ_PASS = "nsubj:pass"
    OBJ = "obj"
    IOBJ = "iobj"
    OBL = "obl"
    OBL_AGENT = "obl:agent"

    AUX = "aux"
    AUX_PASS = "aux:pass"
    COP = "cop"

    AMOD = "amod"
    ADVMOD = "advmod"
    ACL = "acl"
    ADVCL = "advcl"
    RELCL = "acl:relcl"

    MARK = "mark"
    CC = "cc"
    CONJ = "conj"
    COMPOUND = "compound"
    DET = "det"
    PUNCT = "punct"
```

The spaCy backend should map provider labels onto this enum where possible and
preserve the original backend label as `token.raw_dep` for debugging and
advanced fallback logic.[^5]

### 5.3. Grammar node model

All grammar nodes should inherit a shared source-backed base:

```python
class GrammarNode:
    span: SourceSpan
    text: str
    region: RegionNode
    document: DocumentNode

    def walk(self) -> Iterable["GrammarNode"]: ...
    def nearest(self, kind: type[T]) -> T | None: ...
```

#### `TokenNode`

```python
class TokenNode(GrammarNode):
    index: int

    lemma: str | None
    pos: UPos | None
    fine_pos: str | None
    morph: MorphFeatures

    dep: Dep | None
    raw_dep: str | None

    head: TokenNode | None
    children: tuple[TokenNode, ...]

    prev: TokenNode | None
    next: TokenNode | None

    confidence: float | None
    provider: str

    def ancestors(self) -> tuple[TokenNode, ...]: ...
    def descendants(self) -> tuple[TokenNode, ...]: ...
    def subtree(self) -> SpanNode: ...
    def next_content(self) -> TokenNode | None: ...
    def prev_content(self) -> TokenNode | None: ...

    def children_with_dep(self, *deps: Dep) -> tuple[TokenNode, ...]: ...
    def has_child(
        self,
        *,
        dep: Dep | None = None,
        pos: UPos | None = None,
    ) -> bool: ...

    def subject(self) -> TokenNode | None: ...
    def object(self) -> TokenNode | None: ...
    def governing_verb(self) -> TokenNode | None: ...

    def is_finite_verb(self) -> bool: ...
    def is_content(self) -> bool: ...
```

`next_content()` and `prev_content()` should walk forward or backward from the
current token and return the nearest token that the provider classifies as
content-bearing according to `is_content()`. They should skip punctuation and
other non-content tokens but must not cross sentence boundaries.

#### `SentenceNode`

```python
class SentenceNode(GrammarNode):
    tokens: tuple[TokenNode, ...]

    def content_tokens(self) -> tuple[TokenNode, ...]: ...
    def first_content_token(self) -> TokenNode | None: ...

    def roots(self) -> tuple[TokenNode, ...]: ...
    def verbs(self) -> tuple[TokenNode, ...]: ...
    def finite_verbs(self) -> tuple[TokenNode, ...]: ...

    def noun_phrases(self) -> tuple[NounPhraseNode, ...]: ...
    def clauses(self) -> tuple[ClauseNode, ...]: ...
    def coordinations(self) -> tuple[CoordinationNode, ...]: ...

    def main_clause(self) -> ClauseNode | None: ...
    def leading_modifier_clause(self) -> ClauseNode | None: ...
    def fronted_subordinate_clauses(self) -> tuple[ClauseNode, ...]: ...
```

#### `NounPhraseNode`

```python
class NounPhraseNode(GrammarNode):
    head: TokenNode
    tokens: tuple[TokenNode, ...]

    def number(self) -> str | None: ...
    def person(self) -> str | None: ...
    def agrees_with_pronoun(self, pronoun: TokenNode) -> bool: ...
    def is_likely_animate(self) -> bool: ...
```

#### `ClauseNode`

```python
class ClauseNode(GrammarNode):
    root: TokenNode
    tokens: tuple[TokenNode, ...]

    marker: TokenNode | None
    subject: TokenNode | None

    def subjects(self) -> tuple[TokenNode, ...]: ...
    def objects(self) -> tuple[TokenNode, ...]: ...
    def auxiliaries(self) -> tuple[TokenNode, ...]: ...

    def followed_by_comma(self) -> bool: ...
    def preceded_by_comma(self) -> bool: ...
```

#### `CoordinationNode`

```python
class CoordinationNode(GrammarNode):
    items: tuple[SpanNode, ...]
    conjunction: TokenNode
    head: TokenNode

    def has_serial_comma(self) -> bool: ...
    def all_items_are_nominalish(self) -> bool: ...
```

`CoordinationNode` is intentionally higher-level than raw dependency links.
Oxford comma rules should not have to rediscover every `conj`, `cc`, and
punctuation relationship by hand on every run.

### 5.4. Morphology API

`MorphFeatures` should expose typed accessors for common features while still
retaining raw provider data:

```python
class MorphFeatures:
    raw: Mapping[str, tuple[str, ...]]

    @property
    def number(self) -> str | None: ...

    @property
    def person(self) -> str | None: ...

    @property
    def tense(self) -> str | None: ...

    @property
    def verb_form(self) -> str | None: ...

    @property
    def voice(self) -> str | None: ...

    def has(self, feature: str, value: str) -> bool: ...
    def has_any(self, feature: str, values: set[str]) -> bool: ...
```

spaCy already exposes token morphology and supports checking whether
morphological analysis is present. Stilyagi should normalize that surface
instead of re-exporting spaCy's object directly.[^1]

### 5.5. Pattern APIs

Stilyagi should define two pattern layers.

#### Token patterns

```python
TokenPattern([
    {"POS": UPos.ADV, "LEMMA": {"IN": {"very", "really"}}},
    {"POS": UPos.ADJ},
])
```

These patterns match linear token sequences. The spaCy backend may compile many
of them into spaCy matcher calls, but the rule-facing contract should stay
Stilyagi-owned.[^6]

#### Dependency patterns

```python
DependencyPattern(
    anchor={"POS": UPos.VERB},
    children=[
        {"DEP": Dep.NSUBJ_PASS},
        {"DEP": Dep.AUX_PASS, "OPTIONAL": True},
    ],
)
```

These patterns match syntactic relations. The public API should use Stilyagi
enums. The spaCy provider may compile them into `DependencyMatcher` patterns
internally.[^7]

### 5.6. Visitor hooks

Rules may implement the following hooks:

```python
def visit_token(self, ctx, token: TokenNode): ...
def visit_sentence(self, ctx, sentence: SentenceNode): ...
def visit_noun_phrase(self, ctx, noun_phrase: NounPhraseNode): ...
def visit_clause(self, ctx, clause: ClauseNode): ...
def visit_coordination(self, ctx, coordination: CoordinationNode): ...
```

The engine should call only the hooks whose required capabilities were
materialized for the current run.

```python
class OxfordCommaRule(Rule):
    requires = {Capability.COORDINATION}

    def visit_coordination(self, ctx, coordination):
        ...
```

This is cleaner than making every rule perform a sentence-level manual search
through raw tokens and dependency links.

### 5.7. Backend contract

A grammar backend should implement the following protocol:

```python
class GrammarProvider(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def annotate(
        self,
        regions: Sequence[RegionNode],
        required: set[Capability],
    ) -> GrammarDocument:
        ...
```

The spaCy provider should:

1. build a spaCy `Doc` per region or compatible region batch;
2. map spaCy tokens to `TokenNode` objects;
3. map spaCy sentence spans to `SentenceNode` objects;
4. populate POS, fine POS, morphology, lemma, dependency, head, and child
   data;
5. derive noun-phrase, clause, and coordination nodes; and
6. preserve raw spaCy objects behind an explicit unstable escape hatch.

Example escape hatch:

```python
spacy_token = token.backend("spacy")
```

This API should be marked unstable and excluded from the compatibility promise.

### 5.8. Source mapping requirements

- Every grammar node must have a `SourceSpan`.
- Every span used in a diagnostic must resolve to source-backed bytes.
- A grammar backend must not produce a fix against synthetic text.
- If a token exists only because of region reconstruction, such as an inserted
  space between Markdown inline nodes, it may participate in analysis but must
  not be directly editable.

### 5.9. Safety and diagnostic wording

Rules using only POS should phrase diagnostics as candidates or suggestions
unless the pattern is genuinely deterministic.

Rules involving ambiguous antecedents, dangling modifiers, and other uncertain
grammar should default to `info` or `warning`, not `error`.

Autofix applicability should remain the existing Stilyagi tri-state:

```text
safe
unsafe
manual
```

Grammar fixes should usually be `unsafe` unless they only insert punctuation at
an unambiguous source-backed location.

Safe examples:

```text
Insert a serial comma before "and".
Insert a comma after a clearly identified fronted subordinate clause.
```

Unsafe examples:

```text
Rewrite passive voice as active voice.
Change verb number.
Replace a docstring opening verb with its lemma.
```

### 5.10. Capability mapping examples

Representative rule-to-capability mappings should look like this:

```text
Weak intensifier rule
Requires: TOKENS, POS, LEMMA

Repeated adjective rule
Requires: TOKENS, POS, LEMMA

Imperative docstring summary rule
Requires: TOKENS, POS, FINE_POS, LEMMA

Noun-stack candidate rule
Requires: TOKENS, POS

Passive voice rule
Requires: TOKENS, POS, MORPH, DEPENDENCY

Dangling modifier rule
Requires: TOKENS, POS, MORPH, DEPENDENCY, CLAUSES, SEMANTIC_LEXICON

Subject-verb agreement rule
Requires: TOKENS, POS, MORPH, DEPENDENCY

Oxford comma rule
Requires: TOKENS, POS, DEPENDENCY, COORDINATION

Ambiguous antecedent rule
Requires: TOKENS, POS, MORPH, DEPENDENCY, NOUN_PHRASES

Fronted subordinate clause comma rule
Requires: TOKENS, POS, DEPENDENCY, CLAUSES
```

### 5.11. Configuration

Recommended configuration:

```toml
[tool.stilyagi.grammar]
provider = "spacy"
model = "en_core_web_sm"
components = "auto"
expose-backend-objects = false

[tool.stilyagi.grammar.capabilities]
prefer-lightweight-sentencizer = true
dependency-parser = "on-demand"
noun-phrases = "on-demand"
clauses = "on-demand"
coordinations = "on-demand"
```

The planner should load only the pipeline components required by enabled rules.
spaCy pipelines are explicitly component-based, so the provider can enable or
skip heavier pieces depending on the active capability set.[^8]

## 6. Compatibility and migration

This RFC extends RFC 0002 rather than replacing it. The region-oriented rule
API remains the entry point for most rules. Grammar nodes add a richer layer
that selected rules can opt into.

Implementation should happen in two layers.

### 6.1. Layer one

Ship the smallest grammar layer that can support token and sentence-aware rules:

```text
TokenNode
SentenceNode
UPos
MorphFeatures
POS
FINE_POS
LEMMA
MORPH
basic dependency navigation
```

This layer enables POS-only rules, imperative-docstring checks, passive-voice
candidates, and subject-verb agreement prototypes.

### 6.2. Layer two

Ship the higher-level syntax helpers once the lower-level data model is stable:

```text
NounPhraseNode
ClauseNode
CoordinationNode
TokenPattern
DependencyPattern
```

This layer enables Oxford comma, clause-punctuation, ambiguous-antecedent, and
dangling-modifier heuristics without forcing every rule author to rebuild
syntactic groupings by hand.

### 6.3. IR and debugging impact

`stilyagi dump-ir --include-grammar` should expose grammar annotations for
debugging, but grammar objects should remain a derived analysis view rather
than a mandatory persisted part of the extraction-only IR.

## 7. Alternatives considered

### Raw spaCy public API

Rejected because it would freeze Stilyagi's public surface to one provider's
classes, labels, and lifecycle rules. Stilyagi needs a stable abstraction that
can survive backend changes.[^1][^2]

### POS-only grammar features

Rejected because POS alone cannot support passive voice, subject-verb
agreement, coordination-aware punctuation, or clause-boundary rules with
acceptable accuracy.

### Serializing full spaCy `Doc` objects into the IR

Rejected because those objects are provider-owned runtime views, not a stable
interchange format, and because v1 should keep extraction transport distinct
from analysis views.[^2]

### Coreference in v1

Rejected because even the advisory version of antecedent analysis is already
complex. The v1 capability surface should reserve `COREFERENCE` without
pretending it is ready.

## 8. Open questions

- Stilyagi needs a strict mapping table from spaCy dependency labels to the
  normalized `Dep` enum.
- Clause extraction should start heuristic and conservative. Clause boundaries
  are not free, even with dependency parses.
- `CoordinationNode` needs careful golden tests. Oxford comma rules become
  surprisingly tricky once Markdown links, inline code, and nested noun phrases
  are involved.
- `is_likely_animate()` should live behind an optional semantic-lexicon
  capability rather than inside core morphology.
- Ambiguous antecedent detection should remain advisory until Stilyagi grows an
  explicit coreference capability.

## 9. Acceptance criteria

The extension is acceptable when:

1. a POS-only rule can run without dependency parsing;
2. a dependency-aware rule fails clearly when the selected provider lacks
   dependencies;
3. all grammar nodes have source-backed spans;
4. spaCy objects are not required for normal rule authoring;
5. builtin passive-voice, imperative-docstring, noun-stack, and Oxford comma
   prototype rules can be implemented without direct spaCy imports;
6. diagnostics can include primary and secondary spans;
7. autofixes cannot edit synthetic spans; and
8. `stilyagi dump-ir --include-grammar` can show grammar annotations for
   debugging.

## 10. Recommendation

Accept this RFC and implement the grammar API as an extension to the existing
region-oriented rule model, not as a replacement for it.

The most important design line is simple: rules should talk to Stilyagi grammar
nodes, not spaCy classes. spaCy is the backend engine. The public API should be
the stable wrapper around it.

## Appendix A. Worked examples

The examples below use a deliberately hypothetical Stilyagi API. They assume a
spaCy-backed provider under the hood, but rules interact with Stilyagi grammar
nodes rather than raw `spacy.Token` objects. The astroid comparison is about
ergonomics and traversal style, not about semantic inference or exposing raw
provider classes.[^3]

### A.1. Avoid intensifier adverbs before weak adjectives

Example text:

```text
The interface is very nice.
```

Desired diagnostic:

```text
STY104: "very nice" is weak praise. Prefer a more precise adjective.
```

This rule needs tokenization, POS, and optionally lemmas. It does not need
dependency structure.

```python
class WeakIntensifierRule(Rule):
    code = "STY104"
    name = "weak-intensifier"
    requires = {Capability.TOKENS, Capability.POS, Capability.LEMMA}

    intensifiers = {"very", "really", "quite", "rather", "pretty", "fairly"}
    weak_adjectives = {"nice", "good", "bad", "great", "fine", "interesting"}

    def visit_token(self, ctx, token):
        if token.pos is not UPos.ADV:
            return

        if token.lemma not in self.intensifiers:
            return

        adjective = token.next_content()
        if not adjective or adjective.pos is not UPos.ADJ:
            return

        if adjective.lemma not in self.weak_adjectives:
            return

        yield Diagnostic(
            code=self.code,
            severity=Severity.INFO,
            message=(
                f"Consider replacing '{token.text} {adjective.text}' with a "
                "more precise adjective."
            ),
            span=token.span.join(adjective.span),
        )
```

### A.2. Prefer imperative verbs in docstring summaries

Example Python:

```python
def normalize_path(path: str) -> str:
    """Normalizes the input path."""
```

Desired diagnostic:

```text
PYDOC210: Docstring summary should use the imperative mood: "Normalize the
input path."
```

This rule needs region metadata, POS, fine POS, and lemmas. It does not need a
dependency parse.

```python
class ImperativeDocstringSummaryRule(Rule):
    code = "PYDOC210"
    name = "imperative-docstring-summary"
    requires = {
        Capability.TOKENS,
        Capability.POS,
        Capability.FINE_POS,
        Capability.LEMMA,
    }

    non_imperative_fine_tags = {"VBZ", "VBD", "VBG"}

    def visit_region(self, ctx, region):
        if region.kind != "python_docstring_summary":
            return

        sentence = region.sentences[0] if region.sentences else None
        if not sentence:
            return

        first = sentence.first_content_token()
        if not first:
            return

        if first.pos is UPos.VERB and first.fine_pos in self.non_imperative_fine_tags:
            yield Diagnostic(
                code=self.code,
                severity=Severity.WARNING,
                message="Use the imperative mood in docstring summaries.",
                span=first.span,
            )
```

### A.3. Detect passive voice

Example text:

```text
The request was validated by the service.
```

Desired diagnostic:

```text
STY201: Passive voice: "was validated".
```

This rule needs morphology and dependency information. POS alone is not
reliable enough, because `AUX VERB` can also describe active progressive
constructions.[^5]

```python
class PassiveVoiceRule(Rule):
    code = "STY201"
    name = "passive-voice"
    requires = {
        Capability.TOKENS,
        Capability.POS,
        Capability.MORPH,
        Capability.DEPENDENCY,
    }

    def visit_sentence(self, ctx, sentence):
        for verb in sentence.verbs():
            passive_subjects = verb.children_with_dep(Dep.NSUBJ_PASS)
            passive_auxiliaries = verb.children_with_dep(Dep.AUX_PASS)

            if not passive_subjects and not passive_auxiliaries:
                if not verb.morph.has("Voice", "Pass"):
                    continue

            span = verb.span
            if passive_auxiliaries:
                span = passive_auxiliaries[0].span.join(verb.span)

            yield Diagnostic(
                code=self.code,
                severity=Severity.INFO,
                message=(
                    f"Passive voice: '{span.text}'. Consider naming the actor "
                    "if it matters."
                ),
                span=span,
            )
```

### A.4. Check subject-verb agreement

Example text:

```text
The list of options are long.
```

Desired diagnostic:

```text
GRAM301: Subject-verb agreement mismatch: "list" is singular but "are" is
plural.
```

This rule needs dependency structure to identify the true subject and
morphology to compare number values. The nearest preceding noun is not always
the grammatical subject.[^9]

```python
class SubjectVerbAgreementRule(Rule):
    code = "GRAM301"
    name = "subject-verb-agreement"
    requires = {
        Capability.TOKENS,
        Capability.POS,
        Capability.MORPH,
        Capability.DEPENDENCY,
    }

    def visit_sentence(self, ctx, sentence):
        for verb in sentence.finite_verbs():
            subject = verb.subject()
            if not subject:
                continue

            subject_number = subject.morph.number
            verb_number = verb.morph.number

            if not subject_number or not verb_number:
                continue

            if subject.is_coordinated():
                continue

            if subject_number == "Sing" and verb_number == "Plur":
                yield Diagnostic(
                    code=self.code,
                    severity=Severity.WARNING,
                    message=(
                        f"Subject-verb agreement mismatch: subject "
                        f"'{subject.text}' is singular, but verb "
                        f"'{verb.text}' is plural."
                    ),
                    span=verb.span,
                    secondary_spans=[subject.span],
                )
```

### A.5. Require the Oxford comma in coordinated noun phrases

Example text:

```text
The parser supports Markdown, docstrings and comments.
```

Desired diagnostic:

```text
PUN201: Use a serial comma before "and".
```

This rule is best expressed over a coordination structure rather than over a
linear POS sequence. Coordination-aware helpers are the difference between a
usable punctuation API and a pile of repeated dependency-tree plumbing.

```python
class OxfordCommaRule(Rule):
    code = "PUN201"
    name = "oxford-comma"
    requires = {
        Capability.TOKENS,
        Capability.POS,
        Capability.DEPENDENCY,
        Capability.COORDINATION,
    }

    def visit_sentence(self, ctx, sentence):
        for coordination in sentence.coordinations():
            if coordination.conjunction.text.lower() not in {"and", "or"}:
                continue

            if len(coordination.items) < 3:
                continue

            if not coordination.all_items_are_nominalish():
                continue

            if coordination.has_serial_comma():
                continue

            yield Diagnostic(
                code=self.code,
                severity=Severity.WARNING,
                message=(
                    f"Use a serial comma before "
                    f"'{coordination.conjunction.text}'."
                ),
                span=coordination.conjunction.span,
                fix=Fix(
                    title="Insert serial comma",
                    applicability="safe",
                    edits=[
                        TextEdit.insert_before(
                            coordination.conjunction.span,
                            ",",
                        )
                    ],
                ),
            )
```

## References

[^1]:
    <https://spacy.io/usage/linguistic-features> "spaCy usage documentation:
    linguistic features"

[^2]:
    <https://spacy.io/api/doc> "spaCy API documentation: Doc"

[^3]:
    <https://pylint.pycqa.org/projects/astroid/en/latest/api/base_nodes/astroid.nodes.NodeNG.html>
    "Astroid API documentation: NodeNG"

[^4]:
    <https://universaldependencies.org/u/pos/> "Universal Dependencies:
    universal POS tags"

[^5]:
    <https://universaldependencies.org/u/dep/> "Universal Dependencies:
    universal dependency relations"

[^6]:
    <https://spacy.io/usage/rule-based-matching> "spaCy usage documentation:
    rule-based matching"

[^7]:
    <https://spacy.io/api/dependencymatcher> "spaCy API documentation:
    DependencyMatcher"

[^8]:
    <https://spacy.io/usage/processing-pipelines> "spaCy usage documentation:
    processing pipelines"

[^9]:
    <https://universaldependencies.org/u/dep/nsubj.html> "Universal
    Dependencies: nominal subject"
