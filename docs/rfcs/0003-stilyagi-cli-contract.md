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
directory or target path.

With `KEY`, print:

- effective value
- source file that provided it
- whether a CLI flag overrode it

### 3.5 `stilyagi clean`

Delete Stilyagi caches rooted beneath the current working directory.

This deliberately mirrors Ruff’s `clean` idea because cache invalidation
remains a malicious little goblin and deserves its own broom. Ruff already
documents `clean` as a top-level cache-clearing command.[^1]

### 3.6 `stilyagi dump-ir [FILES]...`

Emit RFC 0001 IR as canonical JSON.

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
- `*.py`
- `*.rs`

MDX is not part of the stable default discovery surface in v1. Preview support
for `*.mdx` MAY land later behind explicit preview configuration, but stable
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

This contract follows Ruff’s fix model closely, because the safe or unsafe
split is one of Ruff’s more civilized design choices.[^2]

## 11. Output formats

v1 SHALL support:

- `text`
- `json`

`text` SHALL be the default.

`json` SHALL be the stable machine-readable form for local tooling.

`sarif` (the Static Analysis Results Interchange Format) is deferred to a later
slice and is NOT part of the v1 contract. Until it lands, `--output-format
sarif` SHALL be rejected with a usage error stating that `sarif` is planned but
not yet available, matching the behaviour of `_parse_output_format`.

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
