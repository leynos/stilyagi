# Usage guide

## Packaging a Vale style with `stilyagi`

`stilyagi` now lives in its own repository. Point `--project-root` at a Vale
style checkout (for example, the Concordat style repository) that exposes a
`styles/` directory and, optionally, a `stilyagi.toml` manifest.

Default workflow:

1. Install dependencies once: `uv sync --group dev`.
2. Package from the style repo:

   ```bash
   uv run stilyagi zip --project-root ../concordat-style \
     --archive-version 1.2.3
   ```
3. Retrieve the ZIP from the printed path (defaults to
   `dist/<style>-<version>.zip`) and attach it to the style repository's
   release.

Notes:

- The CLI auto-discovers style directories under `styles/` unless `--style` is
  supplied.
- When a single vocabulary exists under `styles/config/vocabularies`, it is
  recorded as `Vocab = <name>` in the generated `.vale.ini`.
- A root `stilyagi.toml` (if present in the style checkout) is copied into the
  archive so installers can apply the packaged defaults.
- `--ini-styles-path` controls both the `StylesPath` written into `.vale.ini`
  and the directory used inside the ZIP.

## Installing a packaged style with `stilyagi install`

The install sub-command updates another repository so Vale downloads a packaged
style from GitHub releases. It rewrites `.vale.ini` and adds a `vale` Makefile
target that syncs, runs any manifest-defined post-sync steps, and then lints.

Key options:

- `stilyagi install <owner>/<repo>` points at the style repository that hosts
  release assets (for Concordat this is `leynos/concordat-vale`).
- `--project-root` sets the consumer repository root (defaults to `.`).
- `--vale-ini` and `--makefile` override the files to edit.
- `--release-version` and `--tag` bypass GitHub lookups when the desired
  release is already known.

Manifest handling:

- If the packaged ZIP contains `stilyagi.toml`, its `[install]` table supplies
  defaults such as `style_name`, `vocab`, `min_alert_level`, and
  `post_sync_steps`.
- When the manifest is missing or download is skipped, the installer falls back
  to `style_name = concordat`, `vocab = concordat`, `min_alert_level =
  warning`, and no post-sync steps.

Example:

```bash
uv run stilyagi install leynos/concordat-vale \
  --project-root /path/to/consumer \
  --release-version 9.9.9 \
  --tag v9.9.9
```

## Updating Tengo maps with `stilyagi`

- `stilyagi update-tengo-map` merges entries from a source file into a Tengo
  map. `--dest` accepts a Tengo script path plus an optional map suffix (for
  example `scripts/AcronymsFirstUse.tengo::allow`); the suffix defaults to
  `allow`.
- `--source` points at the list of entries. Blank lines and lines that start
  with `#` are ignored, and any text after whitespace and an optional `#` is
  stripped.
- `--type` defaults to `true`, which writes every entry as `"key": true`. Use
  `=` to write string values (splitting on the first `=` per line), `=b` to
  coerce booleans, and `=n` for numeric values.
- The command exits after printing a concise summary such as
  `2 entries provided, 1 updated`.

Example:

```bash
uv run stilyagi update-tengo-map \
  --source .config/common-acronyms \
  --dest .vale/styles/config/scripts/AcronymsFirstUse.tengo
```
