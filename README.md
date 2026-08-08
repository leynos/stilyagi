# Stilyagi

*A compiler for prose — structural linting for the documentation that lives in
your source tree.*

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](
https://deepwiki.com/leynos/stilyagi)

Stilyagi reads Markdown pages, Python docstrings, and Rust documentation
comments as structured regions rather than as undifferentiated lines. Rust does
the parsing and keeps byte-exact source maps; Python runs the rules.

> **Status: pre-0.1.0.** The extraction engine works. No rules ship yet, so
> `stilyagi check` runs and finds nothing. Come for the architecture, not
> for the linting — see the [roadmap](docs/roadmap.md) for what has landed.

Website: <https://df12.studio/stilyagi>

______________________________________________________________________

## Why Stilyagi?

Prose linters tend to sit at one of two extremes, and neither is much fun to
live with:

- **Declarative tools** understand document structure but cap what a rule can
  say. Once your policy outgrows YAML and a regular expression, you are stuck.
- **Ad hoc scripts** can express anything, but they lose the plot the moment
  prose lands inside a heading, a table, a docstring, or mixed markup.

Stilyagi takes the middle road. Rules are ordinary Python against a typed
model, and the text they see has already been parsed properly:

- **Source-faithful.** Every region carries the exact byte range it occupies.
  A fix can only ever touch text that was really there — never a space the
  flattener invented.
- **Structural.** A heading is a heading, a docstring knows which function
  owns it, and a link's title is not confused with its target.
- **Deterministic.** Same input, same output, same order. No network, no
  model downloads, no surprises in continuous integration.
- **Programmable.** Declare the capabilities a rule needs and the engine
  loads only those. A structural run never pays for a parser it did not ask for.

______________________________________________________________________

## Quick start

Stilyagi is not published yet — the `stilyagi` package currently on the Python
Package Index is an unrelated older tool. Build from source:

```shell
git clone https://github.com/leynos/stilyagi.git
cd stilyagi
make build
```

That creates the virtual environment, compiles the Rust extension through
`maturin`, and installs the package in editable mode. Python 3.14 or newer and
a Rust toolchain are required.

Then point it at some Markdown:

```shell
$ uv run stilyagi check docs/
0 diagnostics found
```

Zero is the honest answer today: extraction runs over every file, and there are
no rules yet to have an opinion about what it found. Ask for machine output, or
pipe prose in on standard input:

```shell
uv run stilyagi check docs/ --output-format json
echo '# A heading' | uv run stilyagi check - --stdin-filename docs/guide.md
```

______________________________________________________________________

## Features

Working today:

- Markdown parsed into a versioned intermediate representation carrying a line
  index, region segments, content hashes, and explicit markers for synthetic
  insertions such as soft-break spaces.
- Python docstring extraction with owner metadata — module, class, and
  function owners with `__qualname__`-style names, including `<locals>` for
  definitions nested inside function bodies.
- Rust documentation-comment extraction with equivalent owner semantics.
- Suppression comments in all three syntaxes, with range polarity preserved.
- `stilyagi check` over Markdown, with configuration discovery, text and JSON
  output, and standard input.
- Wheels that build and smoke-test on Linux, macOS, and Windows.

Designed, not yet built:

- Built-in rules. The catalogue described on the website is the v1 target.
- Safe-fix planning, `--fix`, and `--diff`.
- The `dump-ir`, `config`, `clean`, `rules`, and `rule` commands.
- Grammar and spelling providers behind the capability planner.
- Discovery covering `*.py` and `*.rs` alongside `*.md`.

The [roadmap](docs/roadmap.md) is the reliable record: an item is ticked only
once it is done.

______________________________________________________________________

## Learn more

- [Users' guide](docs/users-guide.md) — what the tool promises, and what it
  does not.
- [Developers' guide](docs/developers-guide.md) — building, testing, and the
  Rust to Python boundary.
- [Design](docs/stilyagi-design.md) — the normative v1 architecture.
- [Roadmap](docs/roadmap.md) — delivery plan and current progress.
- [Contents](docs/contents.md) — index of every document, including the RFCs
  and architecture decision records.

______________________________________________________________________

## Licence

ISC — see [LICENSE](LICENSE) for details.

______________________________________________________________________

## Contributing

Contributions are welcome, and early is a good time to arrive — the rule API is
still soft enough to shape. See [AGENTS.md](AGENTS.md) for the conventions this
repository follows.
