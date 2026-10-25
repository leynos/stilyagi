# Mixed-source discovery change notes

These notes summarize the mixed-source discovery behaviour. Stilyagi has not
published a release; the current `0.1.0` package metadata does not establish a
published version or a future release target. The
[user's guide](users-guide.md) remains the detailed command reference.

## Mixed-source discovery

Default discovery now includes `.md`, `.markdown`, `.mdc`, `.py`, and `.rs`
files. `stilyagi check` can check Markdown, Python docstrings, and Rust
documentation comments together in one repository pass, selecting an extractor
for each file by its final suffix.

## Run summary and diagnostics

Text output ends with a run summary such as:

```text
checked N files (M skipped, K unreadable); E errors, W warnings
```

JSON output reports the same counts in its `summary` object. The summary makes
the amount of work and its diagnostic outcome visible, including runs with no
discovered files.

Parse-recovery notices from extraction are warnings; warning-only runs exit
with status `0`. Authored suppression-directive mistakes are errors and make
the command exit `1`. Operational failures, including read, configuration,
extraction, traversal, and usage failures, use exit status `2`. See the
[user's guide](users-guide.md) for the complete output and exit-code contract.

## Standard input

When checking standard input with `stilyagi check -`, `--stdin-filename PATH`
sets the diagnostic filename and selects the extractor using `PATH`'s final
suffix. Without `--stdin-filename`, Stilyagi uses Markdown. For example,
`stilyagi check - --stdin-filename src/lib.rs` selects Rust extraction.

See the [standard-input reference](users-guide.md#standard-input) for the full
syntax and usage constraints.
