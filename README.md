# 🎷 Stilyagi

*A compiler for prose — structural linting for the documentation that lives in
your source tree.*

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](
https://deepwiki.com/leynos/stilyagi)

Stilyagi reads Markdown pages, Python docstrings, and Rust documentation
comments as structured regions rather than as undifferentiated lines. Rust does
the parsing and keeps byte-exact source maps; Python runs the rules.

> **Status: preview.** 0.2.0 is the first release of this compiler. The
> extraction engine works, and three builtin rules ship: `MD001` (heading
> depth), `STY001` (adjacent repeated words), and the opt-in `TERM001`
> (configured banned terms). See the [users' guide](docs/users-guide.md) for
> their options and the [roadmap](docs/roadmap.md) for what has landed.

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
- **Programmable.** Declare the capabilities a rule needs, and the engine
  loads only those. A structural run never pays for a parser it did not ask for.

______________________________________________________________________

## Installation

Stilyagi releases are published to the Python Package Index as `stilyagi`, with
wheels for Linux (`x86_64` and `aarch64`), macOS (`arm64` and `x86_64`), and
Windows, plus a source distribution for everything else. Python 3.14 or newer
is required; there is no Rust toolchain to install and no helper binary to
manage, because the extraction engine ships inside the wheel.

```shell
uv pip install "stilyagi>=0.2.0"
```

or, with `pip`:

```shell
pip install "stilyagi>=0.2.0"
```

The `stilyagi` name on the Python Package Index belongs to this project. Its
only upload so far, 0.1.0, was an earlier Vale-style tool that this compiler
replaces. That older release declares `>=3.13`, so it installs on a Python 3.14
interpreter, and an unversioned `pip install stilyagi` would select it. The
floor above is what keeps the predecessor out; lower it only if you mean to
install the Vale-style tool.

To run the compiler from a checkout, build it there:

```shell
git clone https://github.com/leynos/stilyagi.git
cd stilyagi
make build
```

A release is published only from a `v*.*.*` tag, and every artefact is attested
by the workflow run that built it. Source-based installs build from the sdist,
which needs a Rust toolchain — see
[Building from source](#building-from-source).

## Building from source

Build a checkout with `make build`:

```shell
git clone https://github.com/leynos/stilyagi.git
cd stilyagi
make build
```

That creates the virtual environment, compiles the Rust extension through
`maturin`, and installs the package in editable mode. Python 3.14 or newer,
`uv`, and [`rustup`](https://rustup.rs) are required for a source build. The
repository pins a dated Rust nightly in `rust-toolchain.toml`, which `rustup`
selects automatically. On Linux the development build also links with the
[`mold`](https://github.com/rui314/mold) linker, so run
`make install-build-tools` once to install the pinned `mold` and the pinned
toolchain before `make build`. See the
[developer's guide](docs/developers-guide.md) for what each tool does and for
building without `make`.

Then point it at some Markdown, or pipe prose in on standard input:

```shell
$ printf '# Release notes\n\nThis is is a repeated word.\n' \
    | uv run stilyagi check - --stdin-filename docs/release-notes.md
docs/release-notes.md:3:9: warning STY001 Repeated word 'is'
checked 1 files (0 skipped, 0 unreadable); 0 errors, 1 warnings; 0 safe fixes, 1 unsafe fix
```

`MD001` reports a heading whose level jumps by more than one, `STY001` reports
an adjacent repeated word, and `TERM001` reports a configured banned term when
the configuration opts in. The [users' guide](docs/users-guide.md) documents
their options, suppression, and fixability. Ask for machine output, or check a
directory:

```shell
uv run stilyagi check docs/ --output-format json
uv run stilyagi check docs/
```

______________________________________________________________________

## Features

Working today:

- Markdown parsed into a structured model where every region remembers the
  bytes it came from.
- Docstrings lifted out of Python, and documentation comments out of Rust,
  each tied to the definition that owns it.
- Suppression comments honoured in all three syntaxes, for a line, the next
  line, or a range.
- Safe-fix planning with `--fix` and `--diff`, plus opt-in unsafe fixes through
  `--unsafe-fixes`.
- `stilyagi check` over Markdown, Python, and Rust sources, with configuration
  discovery, text and JSON output, run summaries, and standard input.
- Three builtin Markdown rules — `MD001` heading depth, `STY001` adjacent
  repeated words, and opt-in `TERM001` banned terms — with selection, ignore,
  per-file ignores, and suppression.
- Wheels and a source distribution that build, smoke-test, and publish on
  Linux, macOS, and Windows.

The [developers' guide](docs/developers-guide.md) covers the intermediate
representation these rest on.

Designed, not yet built:

- The rest of the v1 rule catalogue described on the website.
- The `dump-ir`, `config`, `clean`, `rules`, and `rule` commands.
- Grammar and spelling providers behind the capability planner.
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
