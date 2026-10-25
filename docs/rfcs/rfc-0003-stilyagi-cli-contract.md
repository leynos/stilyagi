# RFC 0003: Stilyagi CLI contract

## Preamble

- RFC: 0003
- Status: Proposed
- Created: 2026-04-14
- Target: Stilyagi 0.1
- Depends on: RFC 0001, RFC 0002

## 1. Summary

The Stilyagi command-line interface (CLI) SHALL present a compact, predictable
command surface inspired by Ruff:

- `check`
- `rule`
- `rules`
- `config`
- `clean`
- `dump-ir`
- `version`
- `help`

`server` SHALL be reserved for a later RFC.

A global `-V` / `--version` flag SHALL be supported in addition to the explicit
`version` subcommand.

## 2. Goals

The CLI needs to feel crisp in daily use and debuggable when things go sideways.

Ruff is the model here for command layout, config precedence, fix safety,
suppression concepts, and exit-code discipline. Ruff documents top-level
commands such as `check`, `rule`, `config`, `clean`, and `server`; “closest
config wins” behaviour with explicit `extend`; safe versus unsafe fixes;
per-file ignores; suppressions; and exit codes `0/1/2`.[^1]

Stilyagi will intentionally diverge in one place: v1 SHALL NOT autoload
user-level configuration. Prose linting is taste-heavy enough already; hidden
personal defaults would turn continuous integration (CI) parity into soup. Ruff
does support a user-level fallback, but Stilyagi should not copy that part in
v1.[^1]

## 3. Command surface

### 3.1 `stilyagi check`

Primary entry point.

Usage:

```bash
stilyagi check [FILES]...
```

If `FILES` is omitted, the default target SHALL be `.`.

The command SHALL accept `-` for stdin. When reading from stdin, callers SHOULD
pass `--stdin-filename` so that Stilyagi can infer syntax, apply per-file
configuration, and report a plausible path.

Guaranteed options in v1:

- `--select`
- `--ignore`
- `--extend-select`
- `--fix`
- `--unsafe-fixes`
- `--diff`
- `--output-format`
- `--config`
- `--isolated`
- `--no-cache`
- `--stdin-filename`
- `--quiet`
- `--verbose`
- `--silent`

### 3.2 `stilyagi rule CODE`

Print full documentation for one rule.

The output SHALL include at least:

- code
- name
- summary
- long explanation
- default severity
- whether the rule is fixable
- fix safety
- configuration keys
- examples
- references

### 3.3 `stilyagi rules`

List installed rules.

The command SHALL support filtering by prefix, pack, severity, preview status,
and fixability. It SHOULD support both human-readable and JavaScript Object
Notation (JSON) output.

### 3.4 `stilyagi config [KEY]`

Without `KEY`, print the resolved configuration for the current working
directory or target path, including defaults and preserved schema values. The
command SHALL accept `--target PATH` for one existing file or directory,
repeated `--config` values, `--isolated`, and the rule-selection flags also
accepted by `check`. It SHALL NOT lint files, write configuration, or create a
cache.

Keys use the TOML dotted spelling, such as `cache-dir`, `lint.select`, or
`extract.markdown.gfm`. With `KEY`, print its effective value and the origins
of that leaf or table's descendants. Each origin SHALL identify its kind
(`default`, `file`, `inline`, or `flag`), source file when a file supplied the
displaced value, and whether a CLI value overrode it. File origins SHALL name
the file that defined the winning value, including values inherited through
`extend`.

`--output-format text|json` selects deterministic human-readable or JSON
output. JSON without `KEY` has `values` and `origins` objects. JSON with `KEY`
has `key`, `value`, and `origins` fields. An unknown key, missing target,
invalid TOML, or cyclic `extend` SHALL exit with status 2, write a useful error
to standard error, and leave standard output empty. The command SHALL NOT
autoload user-level configuration.

### 3.5 `stilyagi clean`

Delete Stilyagi caches rooted beneath the current working directory.

This deliberately mirrors Ruff’s `clean` idea because cache invalidation
remains a malicious little goblin and deserves its own broom. Ruff already
documents `clean` as a top-level cache-clearing command.[^1]

### 3.6 `stilyagi dump-ir [FILES]...`

Emit RFC 0001 IR as canonical JSON.

The command SHALL default to `.` and recursively inspect Markdown files with
`.md`, `.markdown` or `.mdc` suffixes. Explicit non-Markdown files SHALL exit
`2`. It SHALL accept `-` once when paired with a Markdown `--stdin-filename`,
and SHALL reject stdin mixed with file or directory operands. Configuration
flags, `--no-cache` and `--output-format json` are supported; fix and
rule-selection flags are not.

One successful input SHALL emit its canonical IR object. Zero or multiple
inputs SHALL emit a JSON array, with empty discovery represented as `[]`.
Rust's canonical document JSON SHALL be retained without parsing and
re-serializing it. The command SHALL prepare the complete result in a spooled
temporary stream with a 1 MiB memory threshold before writing standard output.
An input failure SHALL therefore emit no partial JSON. Normal output SHALL end
with one newline, and errors or logs SHALL use standard error only. If the
standard-output stream itself fails after copying begins, the command SHALL
report the write error without promising rollback of bytes already sent.

This is the one major addition beyond the Ruff-like surface. A parser-heavy
prose linter without an IR dump command would be begging for séance-grade
debugging.

The runtime MAY use a more efficient in-process transport internally, but
`dump-ir` is the stable serialized and debug form for fixtures, compatibility
review, and false-positive investigation.

## 4. Configuration files

Stilyagi SHALL recognize exactly these configuration files:

- `pyproject.toml`
- `stilyagi.toml`
- `.stilyagi.toml`

All three SHALL use the same schema. In `pyproject.toml`, settings live under
`[tool.stilyagi]`. In standalone TOML files, the prefix is omitted.

If more than one supported config file exists in the same directory, precedence
SHALL be:

1. `.stilyagi.toml`
2. `stilyagi.toml`
3. `pyproject.toml`

This mirrors Ruff’s same-directory precedence rules.[^1]

## 5. Configuration discovery and precedence

Stilyagi SHALL use nearest-config semantics.

For any given file:

1. discover the nearest supported config in the directory hierarchy,
2. load that config,
3. follow any explicit `extend` chain,
4. apply CLI overrides.

Stilyagi SHALL NOT implicitly merge parent configs. Users who want inheritance
SHALL opt into it with `extend`.

This is a direct adoption of Ruff’s best configuration decision: explicit
inheritance instead of spooky-action-at-a-distance merging. Ruff documents both
the “closest config wins” rule and the explicit `extend` escape hatch.[^1]

CLI precedence SHALL be:

1. dedicated CLI flags
2. `--config "key = value"` overrides
3. explicitly specified config file via `--config path/to/file`
4. discovered nearest config
5. defaults

`--isolated` SHALL disable config discovery entirely.

## 6. Configuration schema

Recommended baseline schema:

```toml
[tool.stilyagi]
cache-dir = ".stilyagi_cache"
respect-gitignore = true
line-length = 88
plugins = ["builtin"]

[tool.stilyagi.lint]
select = ["MD", "DOC", "PUN", "STY", "PYDOC"]
ignore = []
fixable = ["ALL"]
unfixable = []
preview = false

[tool.stilyagi.lint.per-file-ignores]
"CHANGELOG.md" = ["PUN201"]
"tests/**" = ["PYDOC"]

[tool.stilyagi.extract.markdown]
gfm = true
frontmatter = true
mdx = false

[tool.stilyagi.nlp]
model = "en_core_web_sm"
sentence-provider = "sentencizer"

[tool.stilyagi.rule.PUN201]
min_items = 3
```

## 7. File discovery

By default, `check` SHALL recurse through directories.

Stilyagi SHOULD respect `.gitignore` and related Git ignore files by default.
Ruff documents the same behaviour, and it is the least surprising option for
modern repository tooling.[^1]

Files passed explicitly on the command line SHALL still be analysed unless
`force-exclude` is enabled in a later extension of this RFC.

v1 built-in discovery SHOULD include at least:

- `*.md`
- `*.markdown`
- `*.mdc`
- `*.py`
- `*.rs`

The Markdown suffixes SHALL be accepted by both `check` and `dump-ir`. MDX is
not part of the stable default discovery surface in v1. Preview support for
`*.mdx` MAY land later behind explicit preview configuration, but stable
recursive discovery should assume only Markdown, Python, and Rust.

## 8. Rule selection

`--select`, `--ignore`, and `--extend-select` SHALL accept either full rule
codes or stable prefixes.

That follows Ruff’s rule-prefix ergonomics, which make it practical to enable
or suppress families of rules instead of tediously enumerating every single
code.[^2]

Examples:

```bash
stilyagi check docs/ --select PUN --ignore PUN201
stilyagi check src/ --select PYDOC,STY
```

## 9. Suppressions

Stilyagi SHALL support three suppression strata:

- configuration
- file-level directives
- inline or range directives

Because Stilyagi lints prose surfaces across multiple host syntaxes, it SHALL
not copy Ruff’s `# noqa` syntax literally. Ruff’s suppression model is still
the conceptual inspiration: config ignores, line-level suppressions,
block-range suppressions, and file-level exemptions.[^2]

### 9.1 Directive grammar

The logical directive grammar SHALL be:

```text
stilyagi: ignore-next CODE[,CODE...]
stilyagi: disable CODE[,CODE...]
stilyagi: enable CODE[,CODE...]
stilyagi: ignore-file CODE[,CODE...]
```

Range and inline directives MUST name at least one code or prefix. Blanket
inline suppression is forbidden in v1.

### 9.2 Markdown form and MDX preview behaviour

In Markdown documents, directives SHALL use HTML comments:

```md
<!-- stilyagi: ignore-next PUN201 -->
Apples, bananas and pears.

<!-- stilyagi: disable STY -->
A whole questionable section.
<!-- stilyagi: enable STY -->

<!-- stilyagi: ignore-file MD,DOC -->
```

If MDX preview support is enabled in a later slice, it SHOULD reuse the same
logical directive form rather than inventing a second suppression grammar.

### 9.3 Source-code form

In source files, directives SHALL use the host language’s native comment syntax.

Examples:

```python
# stilyagi: ignore-next PYDOC210
def f():
    """Returns the value."""
```

```rust
// stilyagi: disable STY101
/// this summary starts lower-case
// stilyagi: enable STY101
```

Docstring suppressions SHALL live in host-language comments, not in docstring
prose itself.

## 10. Fixes

`stilyagi check --fix` SHALL apply safe fixes only.

`stilyagi check --fix --unsafe-fixes` SHALL additionally apply unsafe fixes.

`--diff` SHALL print a patch instead of mutating files.

`--fix` combined with `--diff` SHALL be a usage error, exiting `2`.

Rejecting the pair is deliberate. Silent precedence between a mutating and a
non-mutating flag is precisely the surprise this contract exists to prevent,
and rejection is the relaxable direction: a rejected combination can be given
meaning by a later amendment, whereas one accepted with an implicit winner
cannot be withdrawn without breaking scripts that depended on that winner. The
untouched source is also the only preview a user can trust, so a run that both
printed a patch and wrote the file would make `--diff` mean "preview, or apply,
depending on a flag you also passed".

`--diff` SHALL reserve standard output for the patch alone, sending the
rendered diagnostics and the summary line to standard error. Without this,
`stilyagi check --diff | git apply` receives a summary line and fails on a
clean repository, which a user resolves with `|| true` and so disarms the check
permanently.

`--fix` SHALL apply safe fixes only when the target came from a file. A target
read from standard input SHALL NOT be written to disk; instead the fixed
document SHALL be written to standard output, and the rendered diagnostics and
summary SHALL go to standard error. `--stdin-filename` names the input for
reporting only and never identifies a file to write.

Planning refusals SHALL NOT be reported as rule codes. They SHALL travel in a
`fix_errors` array alongside `diagnostics` in `json`, and in `text` under a
distinct non-rule prefix. A refusal identifier is namespaced `fix-error/` and
is exempt from `--select`, `--ignore`, and suppression by construction.

A refusal that records a *planning* decision SHALL carry no exit-code weight of
its own, because the unfixed diagnostic that prompted it already forces exit
`1`. A refusal that records an *environmental* failure — a write the filesystem
rejected — SHALL instead force exit `2`, as an unreadable source does. The two
SHALL be distinguishable without parsing the message: the executor SHALL report
an environmental failure as `fix-error/write-failed` and SHALL NOT abandon the
remaining files, so that a partially applied run can still name every file it
wrote and every file it could not.

This contract follows Ruff’s fix model closely, because the safe or unsafe
split is one of Ruff’s more civilized design choices.[^2]

## 11. Output formats

v1 SHALL support:

- `text`
- `json`

`text` SHALL be the default.

`json` SHALL be the stable machine-readable form for local tooling.

`sarif` (the Static Analysis Results Interchange Format) is deferred to a later
slice and is NOT part of the v1 contract. Until it lands,
`--output-format sarif` SHALL be rejected with a usage error stating that
`sarif` is planned but not yet available, matching the behaviour of
`_parse_output_format`.

When it does land, `sarif` will conform to the SARIF 2.1.0 family of
expectations closely enough to interoperate with downstream static-analysis
consumers. SARIF exists specifically to standardize static-analysis output
interchange, which is exactly the job here, so it remains the intended forward
format for that use case.[^3]

## 12. Exit codes

`check` SHALL exit with:

- `0` when no violations remain, or when all found violations were fixed
- `1` when violations remain
- `2` on invalid configuration, invalid CLI usage, plugin load failure, or
  internal error

That mirrors Ruff’s documented exit-code contract and is the right one.[^2]

## 13. Caching

The default cache directory SHALL be `.stilyagi_cache`.

The cache key SHALL include at least:

- file content hash
- effective configuration hash
- extractor or parser versions
- enabled rule-pack versions
- NLP model signature

`clean` SHALL remove these caches.

## 14. Plugin activation

Installed rule packs SHALL not automatically become active merely because they
exist in the environment.

v1 SHALL activate built-ins by default and any third-party packs named in
config or selected explicitly by CLI options. This keeps surprising arbitrary
Python execution to a minimum and makes CI behaviour legible.

## 15. Reserved future surface

The following names are reserved for future RFCs:

- `server`
- `doctor`
- `migrate-config`

## 16. Examples

```bash
stilyagi check .
stilyagi check docs/ src/ --select DOC,PUN --fix
stilyagi check - --stdin-filename README.md --output-format json
stilyagi rule PUN201
stilyagi rules --select PYDOC
stilyagi config
stilyagi dump-ir README.md
stilyagi clean
```

## 17. Rationale

The CLI should feel small enough to memorize and strict enough to trust.

Ruff’s command surface proves that a linter can stay compact without becoming
anaemic, and its config semantics avoid the usual nested-TOML ghost stories.
Stilyagi should imitate that restraint, then add one debug-first command,
`dump-ir`, because prose linting over reconstructed regions and mixed parse
frontends needs visibility into the intermediate state.[^1]

One deliberate deviation bears repeating: no user-level config autoloading in
v1. That is not asceticism. It is damage control.

[^1]: <https://docs.astral.sh/ruff/configuration/>
[^2]: <https://docs.astral.sh/ruff/linter/>
[^3]: <https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html>
