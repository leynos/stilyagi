# Architectural decision record (ADR) 008: Adopt v1 discovery defaults

## Status

Accepted.

## Date

2026-08-24.

## Context and problem statement

Stilyagi v1 supports Markdown documents, Python docstrings, and Rust
documentation comments, but `stilyagi check` previously discovered only
Markdown files. That meant a mixed repository could expose extractor support
through the Python API while the command intended to check a tree silently
missed most of its source prose.

The command also needed an honest response to recoverable extraction anomalies.
A parse-recovery event is not an authored rule violation, but treating all IR
errors alike made an ordinary mixed-tree run fail. Conversely, demoting every
IR error would conceal incorrect suppression directives. More inputs also make
an empty result ambiguous unless the command reports what it checked and
skipped.

What default discovery, diagnostic classification, and operational boundaries
let this CLI slice support the three v1 prose surfaces without claiming a
configurable or fully scalable source walker prematurely?

## Decision drivers

- Match the accepted v1 syntax scope in [ADR 003](adr-003-v1-contract-scope.md).
- Preserve deterministic output, ordering, and a narrow command-line contract.
- Avoid treating recoverable extraction anomalies as user-authored violations.
- Make mixed-tree coverage observable rather than inferring it from silence.
- Keep the Python orchestration and Rust extraction ownership boundary intact.

## Requirements

### Functional requirements

- Discover Markdown, Python, and Rust source files recursively from file and
  directory targets.
- Select the extractor syntax for each discovered file and retain its
  user-facing path.
- Report authored suppression-directive mistakes as errors and extraction
  anomalies as warnings.
- Explain checked, skipped, unreadable, error, and warning counts in text and
  JSON output.

### Technical requirements

- Preserve `.markdown` discovery while excluding MDX and Python stubs.
- Keep the v1 extension set fixed: no `include` or `exclude` configuration and
  no new CLI flags.
- Keep bridge payload vocabularies Rust-owned, but keep file-extension mapping
  with the current Python discovery walker.
- Cover order and classification invariants with repository-supported tests,
  rather than introducing a new formal-verification toolchain.

## Options considered

### Option A: fixed Python-owned mixed-source defaults

Keep the extension-to-syntax mapping with Python discovery, add the four
registered suffixes, and carry the selected syntax to the existing Rust
extraction boundary. Publish authored-directive codes from Rust because those
codes appear in bridge payloads. Add summaries and warning classification in
the Python orchestration layer.

This reuses the existing boundary and gives users a working mixed-tree command
now. Its deliberate limitation is a fixed directory-pruning list without
gitignore semantics.

### Option B: configurable discovery and a broader extension set

Add discovery configuration or flags for inclusion, exclusion, MDX, Python
stubs, or other suffixes in this slice.

This would appear flexible, but it would create unapproved public contract
surface and over-claim support before the relevant extractors and user policy
exist.

### Option C: move discovery to Rust immediately

Move the walker and extension mapping into Rust now, ideally using the `ignore`
crate for gitignore-aware traversal.

This is the architectural destination, but it is a larger cross-boundary
migration than this CLI expansion. It should be one coherent move rather than a
temporary bridge seam around a Python walker.

| Topic                            | Option A | Option B | Option C |
| -------------------------------- | -------- | -------- | -------- |
| Delivers mixed-tree checking now | Yes      | Yes      | Yes      |
| Adds unratified user contract    | No       | Yes      | No       |
| Preserves the current boundary   | Yes      | Mostly   | No       |
| Provides gitignore semantics     | No       | No       | Yes      |

_Table 1: Discovery options for the v1 CLI expansion._

## Decision outcome

Adopt Option A.

- Discovery recognizes `.md`, `.markdown`, `.py`, and `.rs`. The mapping is in
  `python/stilyagi/discovery.py`, because file extensions are not
  bridge-payload vocabulary. The selected `model.Syntax` travels with each
  discovered file.
- Discovery remains a fixed built-in default. There are no `include` or
  `exclude` keys and no additional CLI flags. MDX and `.pyi` remain excluded;
  retaining `.markdown` avoids a compatibility regression.
- `discover_markdown_files` becomes `discover_files`. This internal module does
  not need a compatibility shim for a name that would now be false.
- Rust declares the two authored-directive error codes beside their mint sites
  and exports them through the existing bridge. Only those codes are errors;
  other current and future IR error codes default to warnings.
- Exit status is temporarily severity-based: error diagnostics produce exit
  `1`, warning-only diagnostics produce exit `0`, and operational failures
  produce exit `2`. The behaviour is deliberately explicit but not the final
  violation model.
- The command reads source with `utf-8-sig`, reports `OSError`, `MemoryError`,
  and decoding failures against the reported path, and still treats them as an
  operational failure for the run.
- Text and JSON output include a run summary. Discovery order and diagnostic
  classification are protected by the existing unit, behavioural, property,
  snapshot, and integration test tooling.

The destination is a Rust-owned, gitignore-aware walker. That move should use
the `ignore` crate and relocate the walker and extension table together rather
than creating an interim Python-to-Rust lookup bridge.

## Goals and non-goals

- Goals:
  - Make `stilyagi check .` useful for mixed Markdown, Python, and Rust trees.
  - Preserve deterministic, explainable results while broadening discovery.
  - Give users a visible coverage signal when inputs are skipped or unreadable.
- Non-goals:
  - Add a configurable discovery policy, MDX, Python stubs, or other suffixes.
  - Change per-file read failures into normal diagnostics or alter the meaning
    of operational exit status.
  - Move discovery into Rust, add gitignore support, parallelize checking, or
  stream results.

## Migration plan

1. Deliver fixed mixed-source discovery, syntax dispatch, error classification,
   summaries, and regression coverage in roadmap item 3.2.1.
2. Before shipping warning-severity rules in roadmap item 3.2.2, replace the
   temporary severity-based exit decision with a violation discriminator.
3. In a dedicated future migration, move discovery into Rust with gitignore
   support and reassess the fixed pruning list.

## Known risks and limitations

- A fixed directory list can miss repository-specific generated trees, and it
  does not respect `.gitignore`.
- Warning-only extraction anomalies do not gate a build by default. The summary
  exposes their count, but teams cannot yet select a stricter policy.
- A non-UTF-8 source or read failure still makes the overall invocation exit
  `2`, even though other files may have been checked.
- Single-threaded discovery and end-of-run rendering will become more visible
  as repository size grows.

## Outstanding decisions and follow-up register

| Candidate                                     | Why it is deferred                                               | Intended follow-up                                                           |
| --------------------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `--fail-on` / `--max-warnings`                | Needs an RFC 0003 §2 command-contract amendment.                 | Let teams gate on extraction degradation.                                    |
| Per-file read diagnostics                     | Changes the meaning of exit `2`.                                 | Retain successful-file results after an unreadable file.                     |
| Violation discriminator                       | Severity is only a temporary exit-code proxy.                    | Resolve before 3.2.2 adds warning-severity rules.                            |
| Typed `IrError` code enum                     | Needs the 3.2.3 IR-envelope reshape.                             | Make code classification exhaustive while preserving kebab-case wire values. |
| Rust discovery with `ignore`                  | Requires a coherent walker migration.                            | Respect gitignore and retire the growing prune list.                         |
| Metrics recorder                              | Existing extractor counters are write-only; Markdown has none.   | Make per-language operational counters observable.                           |
| `--doctest-modules`                           | Current Python doctests do not run.                              | Enforce the documented Python examples.                                      |
| Corpus-fixture relocation                     | Adversarial Python and Rust fixtures are currently discoverable. | Let CI dogfood `stilyagi check .`.                                           |
| File-size, parallel, and incremental controls | Require a scalable execution and rendering design.               | Support monorepo-scale checking.                                             |
| `.mdx` and `.pyi`                             | Neither belongs to the current supported set.                    | Revisit each as a separate product decision.                                 |

_Table 2: Deferred discovery and operational-policy candidates._

## References

- [ADR 003: Ratify the v1 contract scope](adr-003-v1-contract-scope.md)
- [RFC 0003: CLI contract](rfcs/0003-stilyagi-cli-contract.md)
- [Roadmap](roadmap.md)
- [ExecPlan 3.2.1](execplans/3-2-1-expand-discovery-defaults-to-md-py-and-rs.md)
