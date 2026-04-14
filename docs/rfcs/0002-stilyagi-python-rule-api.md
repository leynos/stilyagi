# RFC 0002: Stilyagi Python rule API

**Status:** Draft **Target:** Stilyagi 0.1 **Depends on:** RFC 0001

## 1. Summary

Stilyagi SHALL expose a Python-first rule application programming interface
(API) built around rich document, region, sentence, token, and node objects.
Rules SHALL declare the capabilities they require, the targets they want to
visit, and the diagnostics and fixes they may emit.

The API SHALL favour explicitness over magic.

The API SHALL not sandbox third-party Python code.

## 2. Design principles

The rule API takes inspiration from two places.

From spaCy, it takes the idea that annotation is componentised,
order-sensitive, selectively enabled, and attached to `Doc`, `Span`, and
`Token`-like objects rather than passed around as disconnected side tables.
From astroid, it takes the idea that nodes should be traversable,
position-aware, and extensible via transforms or enrichers rather than exposed
as raw dictionaries.[^1][^2]

The API therefore makes three deliberate choices:

- Rules operate on typed wrappers, not raw IR dictionaries.
- Rules declare `requires` up front, so the engine can build the cheapest
  viable annotation plan.
- The stable public API does not expose raw spaCy internals as the main
  abstraction, though advanced rules MAY request backend handles.

## 3. Core abstractions

The public API SHALL define these primary runtime types:

- `Document`
- `Region`
- `NodeRef`
- `Sentence`
- `Token`
- `Rule`
- `RuleContext`
- `Diagnostic`
- `Fix`
- `TextEdit`

`Document`, `Region`, and `NodeRef` SHALL wrap RFC 0001 IR objects.

`Sentence` and `Token` SHALL exist only when sentence and token capabilities
have been materialised.

`NodeRef` SHALL expose, at minimum:

- `id`
- `kind`
- `span`
- `parent`
- `children`
- `props`
- `fields`
- `walk()`
- `find_all(...)`

That shape deliberately resembles astroid’s `NodeNG` family: navigable,
position-aware, and suitable for transforms and visitors. Astroid’s own node
API exposes parent or child traversal, positional data, sibling navigation, and
helper methods such as `nodes_of_class()` and `infer()`. Stilyagi should copy
the ergonomic lesson, not the entire semantic machinery.[^2]

## 4. Rule declaration

A rule SHALL be a Python class that subclasses `Rule`.

Each rule SHALL define:

- `code`
- `name`
- `summary`
- `default_severity`
- `targets`
- `requires`

A rule MAY additionally define:

- `explanation`
- `languages`
- `tags`
- `config_model`
- `preview`
- `fix_mode`

Example:

```python
from dataclasses import dataclass
from stilyagi.api import (
    Capability,
    Diagnostic,
    Fix,
    Rule,
    SentenceTarget,
    Severity,
    TextEdit,
)


@dataclass(frozen=True)
class OxfordCommaConfig:
    min_items: int = 3


class OxfordCommaRule(Rule[OxfordCommaConfig]):
    code = "PUN201"
    name = "oxford-comma"
    summary = "Require a serial comma in simple coordinated lists."
    default_severity = Severity.WARNING
    targets = [SentenceTarget(within={"paragraph", "list_item"})]
    requires = {
        Capability.SENTENCES,
        Capability.TOKENS,
        Capability.POS,
    }
    config_model = OxfordCommaConfig

    def visit_sentence(self, ctx, sentence):
        for lst in sentence.coordination_lists():
            if (
                lst.is_simple_noun_list(min_items=ctx.config.min_items)
                and not lst.has_serial_comma()
            ):
                yield Diagnostic(
                    code=self.code,
                    message="Use a serial comma before the final conjunction.",
                    span=lst.final_conjunction_span(),
                    fix=Fix(
                        title="Insert serial comma",
                        applicability="safe",
                        edits=[
                            TextEdit.insert_before(
                                span=lst.final_conjunction_span(),
                                text=",",
                            )
                        ],
                    ),
                )
```

## 5. Targets

`targets` SHALL be explicit target descriptors, not ad hoc strings.

v1 SHALL define at least:

- `DocumentTarget()`
- `RegionTarget(kind=..., scope_has=..., language=...)`
- `NodeTarget(family=..., kind=..., predicate=...)`
- `SentenceTarget(within=...)`
- `TokenTarget(within=...)`

The engine SHALL only call hooks that correspond to declared targets.

Supported hooks SHALL include:

- `prepare(ctx, document)`
- `visit_document(ctx, document)`
- `visit_region(ctx, region)`
- `visit_node(ctx, node)`
- `visit_sentence(ctx, sentence)`
- `visit_token(ctx, token)`
- `finalize(ctx, document)`

Hooks SHALL yield diagnostics. The engine SHALL collect them.

## 6. Capabilities

Rules SHALL declare capabilities as a set.

v1 SHALL define at least:

- `STRUCTURE`
- `SENTENCES`
- `TOKENS`
- `POS`
- `MORPH`
- `LEMMAS`
- `DEPENDENCIES`
- `VECTORS` as preview-only
- `CUSTOM(name)` for plugin-provided annotations

The engine SHALL plan annotation work from the union of requested capabilities.

This is where spaCy matters. spaCy documents that components are optional, can
be enabled or disabled, and can be swapped or removed. It also documents that
sentence segmentation can come from the dependency parser, a dedicated sentence
recogniser, or the rule-based `Sentencizer`; and it documents that lemmas are
not present by default in v3, requiring an explicit lemmatiser component, with
rule-based lemmatisation depending on POS tags. That makes capability planning
a first-class design requirement rather than a decorative flourish.[^1]

The engine SHOULD satisfy `SENTENCES` with the lightest provider that meets all
active rules. A sentence-only run SHOULD prefer a sentencizer or sentence
recogniser over a full dependency parse. A dependency-aware run MAY use the
parser and let sentence boundaries fall out of it.

## 7. Runtime objects and backend escape hatches

`Sentence` and `Token` SHALL expose a stable Stilyagi API first, not raw spaCy
objects first.

For example, `Token` SHALL expose:

- `text`
- `whitespace`
- `lemma`
- `pos`
- `tag`
- `dep`
- `morph`
- `span`

`Sentence` SHALL expose:

- `text`
- `span`
- `tokens`
- `region`
- `doc`

A backend escape hatch MAY exist as `sentence.backend`, `region.backend_doc`,
or equivalent, but rules SHOULD not depend on backend-specific internals unless
they explicitly opt into unstable APIs.

This design keeps the public contract stable even if Stilyagi later swaps
providers or composes non-spaCy enrichment.

## 8. Context and annotations

`RuleContext` SHALL provide:

- `document`
- `config`
- `settings`
- `memo`
- query helpers such as `regions(...)` and `nodes(...)`
- access to capability-provided annotations

Stilyagi SHOULD support annotation namespaces in the style of spaCy’s extension
attributes. spaCy already treats `Doc._`, `Span._`, and `Token._` as the place
for application-specific metadata and hooks, and that model fits Stilyagi
nicely.[^1]

Example:

```python
ctx.annotations["acme.terminology"]["preferred_terms"]
region.annotations["builtin.syntax"]["coordination_lists"]
```

## 9. Diagnostics

A diagnostic SHALL contain:

- `code`
- `message`
- `severity`
- `span`
- optional `secondary_spans`
- optional `notes`
- optional `tags`
- optional `fix`

`span` SHALL always use source coordinates, never only region-relative offsets.

`severity` SHALL support at least:

- `error`
- `warning`
- `info`
- `hint`

## 10. Fixes

A fix SHALL contain:

- `title`
- `applicability`
- `edits`

A text edit SHALL contain:

- `byte_start`
- `byte_end`
- `replacement`

`applicability` SHALL support:

- `safe`
- `unsafe`
- `manual`

The meanings SHOULD mirror Ruff’s broad distinction: safe fixes preserve intent
to the best of the tool’s deterministic knowledge, while unsafe fixes may alter
semantics, behaviour, or nuance. Ruff documents this distinction explicitly and
treats unsafe fixes as opt-in; Stilyagi should do the same, because prose
rewrites are even more semantically slippery than source rewrites.[^3]

The engine MUST reject overlapping applied edits from distinct diagnostics
unless it can prove they are identical or mergeable.

## 11. Configuration model

Each rule MAY declare a `config_model`.

For v1, `config_model` SHALL be a frozen dataclass or a compatible typed object
constructible from TOML-derived data.

Rule configuration SHALL resolve from two scopes:

- pack-level configuration
- rule-level overrides

Recommended TOML layout:

```toml
[tool.stilyagi.rules.builtin]
dialect = "en-GB"

[tool.stilyagi.rule.PUN201]
min_items = 3
```

## 12. Rule codes and namespaces

Rule codes SHALL follow a stable prefix-plus-digits pattern.

Built-in prefixes SHOULD include:

- `MD`
- `DOC`
- `PUN`
- `STY`
- `TERM`
- `PYDOC`
- `RSDOC`
- `IMG`

Third-party rule packs SHOULD own a stable prefix or prefix family.

This intentionally echoes Ruff’s prefix model, where rule selection works at
either full-code or prefix granularity. Ruff’s documentation makes that
rule-prefix ergonomics explicit, and it is worth stealing.[^3]

## 13. Plugin discovery

Stilyagi SHALL use Python entry points for plugin discovery.

The engine SHALL recognise at least these groups:

- `stilyagi.rules`
- `stilyagi.capabilities`

A rule pack MAY expose either:

- a `RulePack` instance,
- a zero-argument factory returning a `RulePack`, or
- a sequence of `Rule` subclasses.

A capability plugin MAY expose a provider factory.

This follows existing Python packaging standards. PyPA defines entry points as
the mechanism by which installed distributions advertise components for
discovery by other code, and `importlib.metadata` exposes `entry_points()` with
group-based selection and `EntryPoint.load()` for runtime loading.[^4]

Minimal pack example:

```toml
[project.entry-points."stilyagi.rules"]
builtin = "stilyagi_builtin.rules:get_pack"
```

```python
def get_pack():
    return RulePack(
        name="builtin",
        version="0.1.0",
        rules=[OxfordCommaRule, HeadingDepthJumpRule],
    )
```

## 14. Trust model

Third-party rule packs run arbitrary Python code.

Stilyagi SHALL treat installed rule packs as trusted code. It SHALL not pretend
to sandbox them when it does not.

Built-in rules SHALL be deterministic and SHALL not require network access.
Third-party rules SHOULD follow the same discipline, but the core engine cannot
guarantee it.

## 15. Non-goals

v1 rules are document-scoped. Repository-wide whole-corpus inference, vector
search, and large language model (LLM)-backed rewriting are out of scope.

Stilyagi is not trying to become an all-purpose generative editor wearing a
fake moustache.

## 16. Rationale

A string-only callback API would make simple rules trivial and sophisticated
rules grotesque.

A raw-spaCy API would overfit the public contract to one backend. spaCy is
excellent, but Stilyagi should use it as a powerful engine component, not as
the sole shape of the public world. The documentation itself emphasises
pipeline composition, extension attributes, hooks, and component
variability.[^1]

A visitor model without explicit capabilities would waste time and memory.
spaCy’s documentation shows that sentence boundaries, POS tags, lemmas, and
dependencies arrive through different components with different costs and
prerequisites. Capability declarations let the engine pay only for what active
rules actually need.[^1]

[^1]: <https://spacy.io/usage/processing-pipelines>
[^2]: <https://pylint.pycqa.org/projects/astroid/en/latest/api/base_nodes/astroid.nodes.NodeNG.html>
[^3]: <https://docs.astral.sh/ruff/linter/>
[^4]: <https://packaging.python.org/specifications/entry-points/>
