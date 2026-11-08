# Markdown inspection and cache change notes

These notes summarize the user-facing behaviour added by the Markdown
inspection and cache work: effective configuration inspection, canonical IR
dumps, the extraction cache, and safe cache cleanup. Stilyagi has not published
a release; the current `0.1.0` package metadata does not establish a published
version or a future release target. The [user's guide](users-guide.md) remains
the detailed command reference.

## New commands

Three commands join `stilyagi check`:

- `stilyagi config` reports the effective configuration for the current
  directory and the file each leaf value came from. Origins are always
  reported; a dotted key only narrows the output to one leaf or table.
- `stilyagi dump-ir` emits the canonical JSON the Rust extractor produces, so
  byte spans, the line index, the content hash, and the frontmatter region can
  be inspected directly.
- `stilyagi clean` removes the extraction cache entries this tool owns.

None of the three changes the behaviour of an existing `stilyagi check`
invocation.

## Markdown extraction cache

Markdown extraction is now cached beneath the configured cache directory. A
cache hit reuses only the canonical extracted IR; rules, diagnostics, and fix
planning still run against the current source, so a stale entry cannot mask a
new diagnostic.

`dump-ir --verbose` reports the cache counters on standard error, keeping the
JSON document on standard output parseable.

The cache is opt-out rather than opt-in:

- `--no-cache` forces fresh extraction without reading, creating, or writing
  persistent cache state. It is accepted by `check` and `dump-ir`.
- Standard input and the verification pass after `--fix` always extract the
  current source again, so neither can consume a cached result.
- A cache write failure warns and falls back to fresh extraction; it does not
  fail the run. A cache read failure is treated the same way.

Cache entries do not expire automatically.

## Cache cleanup

`stilyagi clean` removes recognized cache namespaces beneath the current
working directory. Only namespaces carrying this tool's ownership marker are
removed: unknown files survive, keeping their namespace in place. Directory
symlinks are pruned rather than followed, and `.git` is skipped. Cleanup needs
no project configuration, so it still works in a tree whose `stilyagi.toml` is
broken. It returns status `2` if a safe cleanup operation fails, and it reports
what it removed:

```text
cleaned 1 cache files in 0 namespaces; preserved 1 unknown entries
```

A namespace whose only remaining content is a preserved unrecognized entry is
counted in the preserved tally rather than in the removed namespace count.

## Markdown frontmatter protection

A planned fix that would change, or that cannot be shown to preserve, the
recognized YAML frontmatter bytes is refused whole rather than applied
partially. The refusal is reported as `fix-error/frontmatter-protected` on the
fix-error channel, so it is visible in `--diff` and `--fix` output instead of
silently dropping edits.

## See also

- [User's guide](users-guide.md) records the command reference and exit-code
  contract.
- [Mixed-source discovery change notes](mixed-source-discovery-notes.md) cover
  the discovery behaviour these commands share.
- [Roadmap](roadmap.md) tracks delivery.
