# Migration guide: v0.1.0 to v0.2.0

## Who should read this

Read this if you run `stilyagi check`, keep a `stilyagi.toml`, or have a
Markdown-heavy repository. v0.2.0 adds three commands, turns Markdown
extraction caching on by default, claims `.mdc` files during discovery, refuses
a planned fix that would disturb YAML frontmatter, and ships three opt-in
builtin documentation rules for Python docstrings and Rust documentation
comments.

Nothing here removes an existing command or option. Every change is either an
addition you can ignore or a new default you can turn off. The one behaviour a
reader must decide about is the cache directory, which appears in the working
tree without being asked for.

## Impact at a glance

| Priority           | Area            | What to do                                                                                                      |
| ------------------ | --------------- | --------------------------------------------------------------------------------------------------------------- |
| Required           | Cache directory | Add `.stilyagi_cache` to your version-control ignore file, or set `cache-dir` to a path you already ignore.     |
| Required if called | Discovery       | Confirm that claiming `.mdc` files in `check` and `dump-ir` does not lint files you meant to exclude.           |
| Review if enabled  | Fix planning    | Re-read your frontmatter expectations: a fix that cannot be shown to preserve those bytes is now refused whole. |
| Recommended        | Command surface | Use `stilyagi config` and `stilyagi dump-ir` when you need to inspect effective configuration or canonical IR.  |
| Optional           | Cache           | Pass `--no-cache` if you want fresh extraction for a run, or run `stilyagi clean` to remove cache data.         |
| Review if enabled  | Documentation   | Opt in to `DOC001`-`DOC003` per rule; a malformed `enabled` value now exits 2 even when the rule is ignored.    |

_Table 1: Obligations when moving from v0.1.0 to v0.2.0._

## 1. Leave the cache directory out of version control

Markdown extraction is cached by default under
`<working directory>/.stilyagi_cache`. A cache hit reuses only the canonical
extracted IR; current rules, diagnostics, and fix planning still run against
the source, so a stale entry cannot mask a new diagnostic. The cache is
disposable and its entries never expire on their own.

### Before: an untracked cache directory

```text
$ stilyagi check
checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings
$ git status --short
?? .stilyagi_cache/
```

### After: an ignored cache directory

```text
$ stilyagi check
checked 1 files (0 skipped, 0 unreadable); 0 errors, 0 warnings
$ git status --short
```

Add one line to the ignore file your version control reads:

```gitignore
.stilyagi_cache/
```

If you would rather keep cache data outside the working tree, set a `cache-dir`
in `stilyagi.toml` and point it at a path you already ignore. A relative value
is resolved against the invocation directory.

## 2. Review the `.mdc` files discovery now claims

`check` and `dump-ir` discover `.md`, `.markdown`, `.mdc`, `.py`, and `.rs`
files. `.mdc` is new in this release. If your tree contains `.mdc` files that
are generated, vendored, or otherwise not meant to be linted, exclude them as
you already exclude any other generated source.

### Before: twelve discovered files

```text
$ stilyagi check
checked 12 files (0 skipped, 0 unreadable); 0 errors, 2 warnings
```

### After: fourteen discovered files

```text
$ stilyagi check
checked 14 files (0 skipped, 0 unreadable); 0 errors, 5 warnings
```

The new warnings are in the two `.mdc` files the run now reads. There is no
`include` or `exclude` configuration for changing the discovered set, so the
choice is between fixing those files and not passing them as operands.

## 3. Expect frontmatter-protected refusals from `--fix`

A planned fix that would change, or that cannot be shown to preserve, the
recognized YAML frontmatter bytes is now refused whole rather than applied
partially. The refusal is reported on the fix-error channel, so it appears in
`--diff` and `--fix` output instead of silently dropping edits. The diagnostic
text is `fix-error/frontmatter-protected`; see
[Common errors and fixes](#common-errors-and-fixes).

A refusal is per file and all-or-nothing. If any planned fix in a file cannot
be shown to preserve the frontmatter, that file is refused whole: no edits and
no replacement bytes are produced, so an otherwise valid body fix in the same
file does not apply either. Fix the frontmatter conflict, then re-run.

## 4. Opt in to the builtin documentation rules

v0.2.0 adds `DOC001` (summary separation), `DOC002` (summary punctuation), and
`DOC003` (owner-only summary) for Python docstrings and Rust documentation
comments. The `DOC` prefix was already part of the default `lint.select`, so
the rules are selected by default but stay inert until each rule's own table
sets `enabled = true`:

```toml
[rule.DOC001]
enabled = true
```

No existing output changes if you leave them unconfigured. Two details are
worth checking in an existing configuration: a `[rule.DOCnnn]` table that sets
`enabled` to a non-boolean now fails with exit code `2` even when the rule is
ignored or unselected, and the `enabled` key is the only option these rules
accept. See the [users' guide](users-guide.md#builtin-documentation-rules) for
the supported surfaces and the conservative exclusions.

## What does not need to change

- Existing `stilyagi check` invocations, their arguments, and their exit codes.
  The exit-code contract is unchanged: `0` for a clean run, `1` when
  diagnostics exist, `2` for an operational error.
- Existing `stilyagi.toml` files. This release adds no required key and
  renames none.
- Rules, rule selection, and suppression directives. A cache hit reuses only
  canonical IR, so rules always evaluate the current source.
- Standard input and the verification pass after `--fix`. Both already
  extracted the current source and continue to do so.
- Existing behaviour of `stilyagi --version` and `-V`.

## Migration checklist

- [ ] Add `.stilyagi_cache/` to the version-control ignore file, or set
      `cache-dir` to an ignored path.
- [ ] Run `stilyagi check` and confirm the file count is what you expect now
      that `.mdc` files are discovered.
- [ ] Deal with any new `.mdc` diagnostics, by fixing the files or by not
      passing them as operands.
- [ ] Run any `--fix` workflow you rely on and read every
      `frontmatter-protected` refusal rather than assuming the fix applied.
- [ ] Optionally run `stilyagi clean` to remove cache data you no longer want.
- [ ] Decide whether to opt in to `DOC001`-`DOC003`, and fix any malformed
      `enabled` value in an existing `[rule.DOCnnn]` table.

## Common errors and fixes

- **Error:** `fix-error/frontmatter-protected`
  - **Fix:** apply the change by hand, or reword the planned fix so it does not
    touch the recognized YAML frontmatter. Use `--diff` to see the planned
    change without applying it.
- **Error:** `stilyagi check: cannot read <path>: ...`
  - **Fix:** the source bytes could not be decoded. This is an operational
    error and exits `2`; it is unrelated to the cache, which stores only
    successfully extracted documents.
- **Error:** `stilyagi dump-ir: cannot extract <path>: ...`
  - **Fix:** the extractor rejected a document whose bytes were readable. The
    command emits no partial JSON, so a pipeline receives nothing rather than a
    truncated array.
- **Error:** a run leaves an untracked `.stilyagi_cache/` directory.
  - **Fix:** this is the default cache, not an error. Ignore it, set
    `cache-dir` elsewhere, or pass `--no-cache` for a run that must not create
    it.

## See also

- [User's guide](users-guide.md) is the command reference and exit-code
  contract.
- [Markdown inspection and cache change notes](markdown-inspection-and-cache-notes.md)
  summarize the same behaviour without the release boundary this guide draws.
- [Mixed-source discovery change notes](mixed-source-discovery-notes.md) cover
  the discovery behaviour `check` and `dump-ir` share.
- [Roadmap](roadmap.md) tracks the delivery these commands belong to.
