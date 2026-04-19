# Architectural decision record (ADR) 001: Select a spell checking provider

## Status

Proposed.

## Date

2026-04-19.

## Context and problem statement

Stilyagi is intended to replace the current Vale-oriented repository with a
Rust extraction layer and a Python rule engine. The current design already
assumes provider-backed enrichment behind stable Stilyagi-owned abstractions
rather than direct dependence on one backend's public types.[^1][^2][^3]

The current design does not yet select a concrete spell checking provider. That
question matters if Stilyagi wants a first-party spelling capability that can
work across Markdown, Python docstrings, and Rust documentation comments
without depending on an external `hunspell` binary, Vale language server
integration, or a C or C++ runtime.

This decision is narrower than "spell checking versus grammar checking". It is
about the backend used for dictionary-based spelling checks. Grammar-aware
analysis remains the separate capability track described in RFC 0005.[^3]

The main question is therefore:

Which spell checking provider should Stilyagi use as its builtin backend for a
future spelling capability, while preserving the current Rust-plus-provider
architecture and avoiding Vale-compatibility baggage?

## Decision Drivers

- Keep the public Stilyagi API provider-neutral.
- Avoid shelling out to an external spell checker process.
- Avoid introducing a platform-specific C or C++ runtime dependency.
- Reuse Hunspell-compatible dictionaries rather than invent a new dictionary
  format.
- Preserve source-faithful spans by running checks over Stilyagi regions and
  mapping offsets back through `segments`.
- Keep initial spelling support diagnostic-first rather than suggestion-first.
- Leave room to replace the backend later if the chosen crate proves too weak.

## Requirements

### Functional requirements

- The provider must load Hunspell-compatible `.aff` and `.dic` dictionary
  files.
- The provider must support whole-word correctness checks for ordinary prose.
- The provider must expose misspelling locations precisely enough for Stilyagi
  to map them back to source-backed spans.
- The provider must support project-local personal dictionaries or equivalent
  runtime word additions.
- The provider must be usable for Markdown, Python docstrings, and Rust
  documentation comments once those regions are extracted.

### Technical requirements

- The provider must embed cleanly inside the Rust side of the current PyO3 and
  `maturin` architecture.[^1]
- The provider must not require network access, auto-downloads, or system
  package managers at runtime.[^1]
- The provider must not force Stilyagi to expose backend-owned public types.
- The provider should allow asynchronous or background dictionary loading,
  because large dictionaries can take measurable time to initialize.[^4]
- The provider should keep suggestions optional and separable from the base
  correctness-checking path.

## Options considered

### Option A: `spellbook`

`spellbook` is a Rust library compatible with Hunspell dictionaries. Its docs
describe it as a lightweight rewrite of Nuspell in Rust. It exposes
`Dictionary`, `Checker`, and `Suggester`, is `no_std` plus `alloc`, and depends
only on `hashbrown`.[^5]

The strongest argument for `spellbook` is architectural fit. It is designed as
a lightweight embedded library rather than as a process wrapper. The Helix
integration discussion also shows the intended operating model is close to what
Stilyagi needs: load dictionaries in the background, check parsed document
regions off the main thread, and layer in personal-dictionary additions.[^4]

The main weakness is maturity visibility. The public docs are relatively thin,
and Helix maintainers still describe suggestions as work in progress and note
that advanced-rule dictionaries in other languages may still expose bugs.[^4]

### Option B: `zspell`

`zspell` is a Rust spell checker compatible with Hunspell dictionaries. Its
docs expose a stabilized checker surface built around `check`, `check_word`,
and `check_indices`, and it explicitly documents dictionary loading via `.aff`
and `.dic` sources.[^6][^7]

The strongest argument for `zspell` is clarity about its stable surface.
Compared with `spellbook`, it documents current limits more explicitly.
`check`, `check_word`, and `check_indices` are described as stable, while
suggestions are explicitly unstable and slow, and compound word handling is not
yet available.[^6][^7]

The main weakness is feature maturity for anything beyond plain correctness
checks. Suggestions are still not finalized, compound handling is absent, and
the crate carries a larger dependency surface than `spellbook`.[^7]

### Option C: External `hunspell` binary or C binding

This option would use the original Hunspell implementation through a system
binary or a direct native binding.[^8]

The strongest argument for this option is maturity and broad dictionary
compatibility. The main weaknesses are operational. It would complicate
cross-platform packaging, introduce external runtime dependencies, and pull
Stilyagi away from its current design goal of being a self-contained Python
distribution with a Rust extension.[^1]

### Option D: No builtin spell checking provider in v1

This option would defer all spelling checks to external tools and keep
Stilyagi's builtin capabilities structural and grammar-oriented only.

The strongest argument for deferral is delivery focus. The main weakness is
product fit. Teams replacing Vale often expect at least basic spelling support,
and forcing them back onto a second tool would dilute the replacement story.

| Topic                         | Option A: `spellbook`  | Option B: `zspell`  | Option C: external Hunspell | Option D: no builtin provider |
| ----------------------------- | ---------------------- | ------------------- | --------------------------- | ----------------------------- |
| Hunspell dictionary support   | Yes                    | Yes                 | Yes                         | No                            |
| Pure Rust embedding           | Yes                    | Yes                 | No                          | Not applicable                |
| Stable documented check API   | Partial                | Stronger            | Depends on binding choice   | No                            |
| Suggestion maturity           | Unclear to early-stage | Explicitly unstable | Mature                      | No builtin suggestions        |
| Dependency footprint          | Smaller                | Larger              | Largest operational burden  | Smallest                      |
| Fit for Stilyagi architecture | Strong                 | Strong              | Weak                        | Medium                        |
| Immediate user value          | High                   | High                | Medium                      | Low                           |

_Table 1: Trade-offs between provider options for Stilyagi's builtin spelling
capability._

## Decision outcome / proposed direction

Adopt `spellbook` as the proposed builtin spell checking provider for
Stilyagi's first-party spelling capability.

This recommendation is not based on Vale parity. It is based on architectural
fit. `spellbook` is a pure Rust, Hunspell-compatible library that can live
inside the Rust side of the current Stilyagi design without introducing
external binaries or native runtime baggage.[^1][^5]

Stilyagi should wrap `spellbook` behind a Stilyagi-owned provider facade. The
public surface should expose Stilyagi capabilities and diagnostics rather than
`spellbook` types. The initial implementation should support correctness checks
and personal-dictionary additions, but it should treat suggestions as
non-blocking follow-up work.

`zspell` remains the strongest fallback candidate if the `spellbook` spike
fails on correctness, offset reporting, or operational behaviour.

## Goals and non-goals

### Goals

- Add a credible path to builtin spelling support using Hunspell-compatible
  dictionaries.
- Keep the provider internal behind a stable Stilyagi capability interface.
- Preserve precise source-span mapping for spelling diagnostics.
- Keep dictionary loading and checking in Rust, close to the existing
  extraction and source-map logic.

### Non-goals

- This ADR does not decide the full rule set for spelling diagnostics.
- This ADR does not commit Stilyagi to spelling suggestions or autofixes in the
  first release of the capability.
- This ADR does not choose the final dictionary-distribution model for every
  supported locale.
- This ADR does not replace the separate grammar-capability track in RFC 0005.

## Migration plan

### Phase 1: provider spike

- Build a Rust-side prototype that loads one English Hunspell-compatible
  dictionary through `spellbook`.
- Run correctness checks over extracted Markdown, Python docstring, and Rust
  documentation-comment regions.
- Prove that misspelling locations can be mapped back to source-backed spans
  through Stilyagi's region and `segments` model.

### Phase 2: provider facade and diagnostics

- Add a Stilyagi spelling capability behind the provider planner.
- Expose diagnostic-only spelling checks first.
- Add personal-dictionary support through repo-local or user-local word lists.

### Phase 3: acceptance or fallback

- Accept this ADR if the spike clears accuracy, performance, and span-mapping
  gates.
- Switch to `zspell` if `spellbook` cannot meet those gates without excessive
  patching or architectural compromise.

## Known risks and limitations

- `spellbook` appears lighter than `zspell`, but its public documentation is
  thinner, so some behaviour may have to be learned by experiment rather than
  by reading stable docs alone.[^5]
- The Helix integration notes explicitly say that `spellbook` suggestions were
  still in progress and that other languages may expose bugs with more advanced
  dictionary rules.[^4]
- Dictionary-based spelling is not grammar checking. It should not be marketed
  as a substitute for the grammar-capability work in RFC 0005.[^3]
- Personal-dictionary, locale, and dictionary-distribution policy still need
  separate project decisions.

## Outstanding decisions

- What capability names should Stilyagi use for spelling, forbidden-word, and
  optional suggestion support?
- Should the first supported locale policy be English-only, or should spelling
  dictionaries follow the broader locale policy once that ADR is settled?
- Should Stilyagi ship any dictionaries, or require explicit user or
  repository configuration for `.aff` and `.dic` paths?
- What acceptance corpus should decide whether `spellbook` is good enough to
  keep over `zspell`?

## Architectural rationale

This decision aligns with the current Stilyagi architecture in four ways.

First, it keeps extraction and source mapping in Rust, where Stilyagi already
places byte-accurate responsibilities.[^1]

Second, it keeps the public API provider-neutral. The design already rejects
leaking backend-owned types into the stable rule surface, and a spell provider
should follow the same rule as the grammar provider.[^1][^2][^3]

Third, it avoids Vale-compatibility baggage. The design explicitly positions
Stilyagi as a replacement rather than a wrapper, so the provider should serve
the Stilyagi architecture directly instead of preserving old tool
boundaries.[^1]

Fourth, it preserves optionality. By selecting `spellbook` behind an internal
provider facade and keeping `zspell` as a documented fallback, the project can
move forward without hard-coding the public product surface to one external
crate.

[^1]: [Stilyagi design](stilyagi-design.md)
[^2]: [RFC 0002: Stilyagi Python rule API](rfcs/0002-stilyagi-python-rule-api.md)
[^3]: [RFC 0005: Grammar capability and syntactic API extensions](rfcs/0005-grammar-capability-and-syntactic-api-extensions.md)
[^4]: [Helix spellchecking integration issue](https://github.com/helix-editor/helix/issues/11660)
[^5]: [spellbook crate documentation](https://docs.rs/spellbook/latest/spellbook/)
[^6]: [zspell crate documentation](https://docs.rs/zspell/latest/zspell/)
[^7]: [zspell crate page](https://docs.rs/crate/zspell/latest)
[^8]: [Hunspell project repository](https://github.com/hunspell/hunspell)
