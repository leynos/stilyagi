# Stilyagi

Stilyagi is a Cyclopts-based command line tool for packaging Vale styles and
dropping them into writing projects. It no longer ships the Concordat style
ruleset itself; that style now lives in a dedicated repository.

## What it does

- Build reproducible ZIP archives from a Vale style checkout, ready to attach
  to a release.
- Update a consumer repository so Vale downloads and applies a packaged style,
  including optional post-sync steps defined in a manifest.
- Merge curated word lists into Tengo maps that Vale can read.

The end-to-end workflows, command options, and troubleshooting notes live in
`docs/users-guide.md`.

## Quick start

```bash
uv sync --group dev
```

- Package a style from its checkout:

  ```bash
  uv run stilyagi zip --project-root /path/to/style --archive-version 1.2.3
  ```

- Point a consumer repository at a released archive:

  ```bash
  uv run stilyagi install owner/repo \
    --project-root /path/to/consumer \
    --release-version 1.2.3
  ```

- Merge entries into a Tengo map that Vale uses:

  ```bash
  uv run stilyagi update-tengo-map \
    --source .config/common-acronyms \
    --dest .vale/styles/config/scripts/AcronymsFirstUse.tengo
  ```

See `docs/users-guide.md` for fuller examples, defaults, and caveats.

## Repository layout

- `stilyagi/` – CLI entry points and helpers for packaging, installation, and
  Tengo map updates.
- `docs/` – User and design documentation. Start with `docs/users-guide.md`
  for everyday usage.
- `features/` – Behaviour-driven feature files that exercise the CLI end to
  end.
- `tests/` and `test_helpers/` – Unit and integration coverage.
- `scripts/` – Support utilities, such as acronym allowlist maintenance.
- `Makefile` – Common tasks for formatting, linting, typechecking, testing, and
  validating Markdown and diagrams.
