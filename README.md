# Stilyagi

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](
https://deepwiki.com/leynos/stilyagi)

Stilyagi is a prose linter for Markdown files and doc comments.

It reads the human-facing text embedded in a source repository — Markdown
pages, Python docstrings, Rust documentation comments — and analyses it as
structured regions rather than as undifferentiated lines. A Rust layer owns
parsing, extraction, and byte-exact source maps; a Python layer owns the rules.
Diagnostics point back at the bytes they came from, so a fix can never land on
text the extractor invented.

Website: <https://df12.studio/stilyagi>

## Status

Version 0.1.0. **Early.** The extraction half of the design works; the rule
half has no rules in it yet.

`stilyagi check` runs today and reports `0 diagnostics found`, because no
built-in rules ship — `stilyagi.rules.builtin` is a reserved namespace, not a
rule pack. The tool is not yet useful for linting your prose. It is useful if
you want to read the extraction layer, write a rule pack against the Python
API, or follow the design.

### Working

- Markdown parsed into a versioned intermediate representation carrying
  `line_index`, region `segments`, content hashes, and explicit markers for
  synthetic insertions such as soft-break spaces.
- Python docstring extraction with owner metadata — module, class, and
  function owners with `__qualname__`-style names, including `<locals>` for
  definitions nested in function bodies.
- Rust documentation-comment extraction with equivalent owner semantics.
- Suppression directives parsed in all three syntaxes, with range polarity
  preserved in the IR.
- `stilyagi check` over Markdown, with nearest-config discovery.
- Wheels build and smoke-test on Linux, macOS, and Windows through PyO3 and
  `maturin`.

### Not built yet

- **Built-in rules.** None ship. The rules catalogue on the website describes
  the intended v1 surface, not shipped behaviour.
- Safe-fix planning, conflict resolution, `--fix`, and `--diff`.
- The `dump-ir`, `config`, `clean`, `rules`, and `rule` commands.
- Grammar and spelling providers, and the capability planner that would load
  them on demand.
- Discovery defaults covering `*.py` and `*.rs` alongside `*.md`.

Treat the website and the design documents as a statement of intent. The
roadmap in [docs/roadmap.md](docs/roadmap.md) is the honest record of what has
landed: each item is checked off only when it is done.

## Requirements

Python 3.14 or newer. A Rust toolchain is needed to build from source; release
wheels bundle the compiled extension.

## Documentation

- [Design](docs/stilyagi-design.md) — the normative v1 architecture.
- [Roadmap](docs/roadmap.md) — delivery plan and current progress.
- [User's guide](docs/users-guide.md) and
  [developer's guide](docs/developers-guide.md).
- [Contents](docs/contents.md) — index of every document, including the RFCs
  and architecture decision records.

## Licence

ISC.
