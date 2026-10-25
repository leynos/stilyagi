# Architectural decision record (ADR) 011: Markdown CLI inspection and cache

## Status

Accepted on 2026-10-25. The approved implementation and its acceptance evidence
are recorded in the associated ExecPlan.

## Date

2026-10-24.

## Context and problem statement

Roadmap 2.2.3 requires effective configuration inspection, canonical
intermediate representation (IR) output, cache cleanup and a working
`--no-cache` flag. Configuration resolution and canonical Rust extraction
already exist, but the CLI exposes only `check`. Persistent extraction caching
does not yet exist. RFC 0003 leaves multi-file output framing and cache
ownership unspecified.

## Decision drivers

- Preserve source-faithful Rust IR and existing check/fix behaviour.
- Make configuration provenance explain the same values that check uses.
- Provide meaningful cache controls without implementing analysis caching.
- Keep cleanup safe even when `cache-dir` names a source directory.

## Options considered

A no-op bypass and cleanup of a hypothetical cache would minimize
implementation but fail the practical maintenance goal. Full extraction and
analysis caching would pull roadmap 3.3.1 into this slice. A Markdown
extraction cache provides a bounded intermediate result while analysis and fix
planning remain fresh.

Concatenated pretty JSON documents are not one valid JSON value. A new stream
protocol or mandatory wrapper would introduce another format. A single
canonical object for one input and an array for multiple inputs retains each IR
envelope and supports the RFC's plural file operands.

Deleting a configured cache root by name risks removing source data when its
value is `.` or `docs`. A dedicated owned namespace permits custom cache
parents without granting cleanup authority over those parents.

## Decision outcome

Adopt the detailed command contracts in the
[2.2.3 ExecPlan](execplans/2-2-3-cli-sub-commands-for-markdown.md):

- Treat `.md`, `.markdown` and `.mdc` as Markdown throughout discovery, stdin,
  inspection and repair. Preserve YAML frontmatter bytes, including fences and
  their closing line ending, during body fixes. Frontmatter edits remain out of
  scope even when unsafe fixes are requested.
- Reuse ADR 005's existing whole-block frontmatter nodes and regions;
  field-level YAML parsing and parser robustness are deferred. Include that
  representation in the stored canonical IR checksum and retain full-source
  lookup hashing. Frontmatter-only edits invalidate extraction so body offsets
  remain current. Future configurable exclusion needs a versioned policy and
  reconstruction of current source coordinates; no exclusion switch is
  introduced here.
- Resolve effective configuration and per-leaf origins through one precedence
  path. `config` exposes text and JSON, plus `--target PATH`.
- Retain Rust's canonical JSON and carry source identity through the existing
  Rust identity entrypoint. Emit one object for one input, an array for
  multiple inputs, and `[]` for empty discovery. Prepare complete output before
  writing stdout so input failures cannot leave partial JSON.
- Persist only Markdown extraction results in a marked `stilyagi-v1` namespace
  inside the configured cache directory. Keep all RFC cache-key dimensions,
  including explicit inactive signatures. Validate cached IR with existing Rust
  serde types and reuse the bridge conversion, without recording an extraction
  attempt for hydration.
- Treat `--no-cache` as zero persistent-cache I/O, including directory creation
  and fingerprint reads. Retain per-run config and bridge-vocabulary
  memoization. Stdin and post-fix verification use fresh extraction.
- Anchor descriptor-relative cache operations at the caller-selected invocation
  cwd: open it once per chain walk, then refuse symlinks in cache-root
  descendants. Walk absolute roots outside cwd strictly from the filesystem
  root without following links. Cleanup likewise opens its selected cwd once
  and safely traverses below it.
- Memoize cache-store construction failures for the invocation. Warn once per
  normalized cache root and count later requests as uncached bypasses. Discard
  stores after read or write failures so later requests may retry.
- Discover owned namespaces beneath cwd without following symlinks or loading
  configuration. Remove only recognized disposable contents; preserve unknown
  files, arbitrary parent directories and outside targets. Concurrent writers
  may repopulate the cache after cleanup.

Python owns command coordination, configuration and cache adapters. Rust
retains source identity, extraction and canonical serialization. Cache
coordination is injected at the application boundary; the pure extractor
remains directly usable.

## Known risks and limitations

Safe deletion and publication depend on descriptor-relative platform
primitives; unsupported safety facilities require refusal or uncached fallback,
not a weaker path check. Cache integrity checks and atomic publication protect
against stale or interrupted ordinary cache operations; the cache is not an
authenticated boundary against an attacker who can rewrite the user's files.

Cache entries have no automatic eviction in this slice; `clean` reclaims them.
Disk-full writes fall back to uncached operation. Output spooling uses a 1 MiB
memory threshold. A symlink used to select the invocation cwd is resolved once
per directory-chain walk when opening the trusted base descriptor. Symlinks
below that base are refused. An absolute cache root outside cwd must have a
symlink-free component chain. Cleanup never follows symlinks beneath its
selected cwd.

The binary digest used in cache identity adds one native-extension read per
cached invocation. Measure this overhead; do not claim a speedup from timing
alone. Independent analysis-cache invalidation remains roadmap 3.3.1 work.

## Outstanding decisions

None. Independent analysis caching remains intentionally deferred to roadmap
3.3.1.

## Architectural rationale

Reuse the existing resolver, byte-preserving input readers, Rust source
identity and canonical serializer. Add only the application boundary and
filesystem adapter needed to reuse extraction. Keep output inspection
independent of rule activation, and keep cache cleanup independent of valid
project configuration.
