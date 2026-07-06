# Adversarial design review — ExecPlan roadmap 2.2.1 (Round 1)

Reviewer: Logisphere design-review crew (Pandalump, Wafflecat, Buzzy Bee,
Telefono, Doggylump, Dinolump) plus pre-mortem and alternatives checkpoint.

Verdict: **REVISE** — not implementable/design-conformant as written.
`satisfied = false`.

## Blocking defects

1. **`make all` does not run the gates.** On current `origin/main`,
   `make all` → `release` → `release-artifact` + `smoke-release`
   (`Makefile:38,48,50,60`). That only builds the release wheel and runs
   `python -m stilyagi.smoke`; it does **not** run `lint`, `typecheck`
   (`ty check`), or `test` (pytest/BDD/e2e), which are separate, unchained
   targets (`Makefile:112,120,131`). The plan's W5 acceptance (line 532) and
   whole-change Validation (lines 629-641) assert `make all` runs "formatting,
   lint, the typecheck target, and the unit/behavioural suites" — false. Fix:
   validation must explicitly invoke `make lint`, `make typecheck`, `make test`
   (plus `make markdownlint`/`make nixie` for docs) in addition to `make all`,
   and every sentence conflating `make all` with the gate suite must be
   corrected.

2. **Incomplete enumeration of tests broken by the W4/W5 rewrites →
   RED gate at the W4 commit.** The plan lists only
   `test_cli_main_reports_placeholder_exit_code` and
   `test_round_trip_helpers.py:93`. But:
   - `tests/test_package_skeleton_units.py::test_diagnostic_preserves_code_and_message`
     (line 92) constructs `diagnostics.Diagnostic(code=, message=, span=NodeRef(...))`;
     W4 reshapes `Diagnostic` (adds required `path`, replaces `span` with
     `line`/`column`), breaking it.
   - `tests/test_package_skeleton_units.py::test_engine_skeleton_dataclasses_preserve_their_fields`
     (line 115) asserts `engine.RendererRegistry().default_format == "text"`;
     W4 rewrites `RendererRegistry`.
   Each must be enumerated as an in-lockstep update (and `default_format`/no-arg
   construction preserved or explicitly retired), or the W4 commit leaves the
   gate red — violating the plan's own commit-green rule.

3. **`test_cli_placeholder_output_matches_snapshot` mischaracterised; the
   remediation is non-hermetic.** `test_round_trip_helpers.py:93` is a `syrupy`
   snapshot capturing `{exit_code, stdout, stderr}` against
   `tests/__snapshots__/test_round_trip_helpers/test_cli_placeholder_output_matches_snapshot.json`,
   not a `== 2` assertion. (a) The plan omits regenerating/removing that stored
   snapshot. (b) Both this test and `test_cli_main_reports_placeholder_exit_code`
   call `cli.main()` with no argv; under default target `.`, `main()` would
   recurse and extract every Markdown file in the repo working directory the
   tests run in — slow, CWD-coupled, non-deterministic. Redefine both to pass
   explicit argv against a `tmp_path` tree (or make no-arg invocation hermetic),
   and account for the snapshot artefact.

4. **Config schema contradicts RFC 0003 §6/§7.** W1 models only a Markdown
   subset and "rejects unknown keys" (exit 2), but RFC §6's v1 baseline
   documents `line-length`, `[lint] fixable`/`unfixable`/`[lint.per-file-ignores]`,
   `[nlp]`, `[rule.<CODE>]` — a config with any (including the RFC's own baseline)
   would be rejected. Conversely the plan invents `[lint] extend_select`
   (`--extend-select` is a CLI flag in §§3.1/8, not a config key) and a
   `[discovery] include` table absent from §6/§7. RFC keys are kebab-case
   (`cache-dir`, `respect-gitignore`, `line-length`); snake-case fields plus
   "reject unknown keys" with no kebab→snake mapping would reject the RFC's own
   keys. Resolve: distinguish "unknown to v1 schema" from "known v1 key not
   consumed by this slice" (accept/ignore the latter), model-or-reserve the full
   §6 key set, specify kebab handling, and land invented keys via RFC/ADR rather
   than unilaterally.

## Advisory

- File failure modes unspecified (non-UTF-8, permission denied, symlink cycles);
  decide exit code / diagnostic behaviour (Doggylump).
- `Document.ir` is `Mapping | None`; offset→location and the extraction-error
  adapter must handle `ir is None`.
- Pin the user-facing JSON `path` form (absolute vs CWD-relative), not only the
  snapshot redaction.
- `--output-format sarif` is rejected by argparse `choices` though RFC §11 lists
  it as v1; deferral is roadmap-consistent — make it explicit in W7 docs and the
  error message.
- Decide the fate of `diagnostics.NodeRef`/`Fix` when reshaping `Diagnostic`.
- Clarify how a single `--config` disambiguates inline `"key = value"` from a
  file path (RFC §5 distinct precedence tiers).

## Signposting

Skills: `logisphere-design-review`. Sources: `docs/roadmap.md` §2.2;
`docs/rfcs/0003-stilyagi-cli-contract.md` §§3-12; `docs/stilyagi-design.md`
lines 302/405/495 and §7.3; `Makefile`; `pyproject.toml`; direct inspection of
`python/stilyagi/{cli,config,diagnostics,model/document,engine/api}.py` and the
affected tests/snapshots. Branch-local facts verified by file inspection.

---


## Re-review (fresh adversarial pass over the round-5 plan, 2026-07-06)

The four original blocking defects above are all resolved in the current draft
(gate story corrected to the four distinct targets; W4 in-lockstep test edits
enumerated; the snapshot artifact accounted for; the schema now accepts and
preserves the whole RFC 0003 §6 baseline). All six advisories are landed.

Re-verified against real source this pass: `Makefile:38-54,114-146`;
`AGENTS.md` §§Quality-gates/Rust-guidance; the placeholder `cli.py` and
single-module `config.py`; the skeleton anchors at
`test_package_skeleton_units.py:92/109/115` and `test_round_trip_helpers.py:93`;
`diagnostics.py` (`NodeRef` only consumed by the one test, no `Fix` importer);
`crates/stilyagi-markdown/src/tests/malformed.rs` (`errors.is_empty()`); the
mixed-extension malformed fixtures; the RFC 0003 §6 baseline key set; roadmap
2.2.1 scope ("JSON or text diagnostics", "Requires 2.1.1 and 1.2.3" — so the
sarif deferral and the refusal of a 2.1.3 dependency are both conformant).

Resolved since round 5 (verified against current source):

1. `discover_markdown_files` — the "Interfaces and dependencies" section had
   declared a return type of `list[pathlib.Path]`, which would have discarded
   the command-line-relative POSIX reported path required by W3/W5 for
   attribution and the pinned renderer `path` form. Verified in current
   `python/stilyagi/discovery.py`: `discover_markdown_files` now returns
   `list[DiscoveredFile]`, where `DiscoveredFile` is a frozen dataclass with
   fields `reported_path: str` (command-line-relative POSIX) and
   `resolved_path: pathlib.Path`. The interface contradiction is resolved.
2. `map_ir_errors` — the "Interfaces" entry had declared a single-argument
   form `map_ir_errors(document) -> list[Diagnostic]`, mismatching the
   two-argument form required by W4 and `tests/test_ir_error_adapter.py`.
   Verified in current `python/stilyagi/engine/checker.py`:
   `map_ir_errors(document, reported_path) -> list[diagnostics.Diagnostic]`.
   The interface contradiction is resolved.

Advisory (fresh):

- Stale citation corrected: bridge facts were cited as
  `crates/stilyagi-pyext/src/tests.rs:14` and `:140`; that file does not
  exist. Citations have been corrected to
  `crates/stilyagi-pyext/src/tests/mod.rs:18` (signature region,
  `bridge_extract_document`) and `:144`
  (`extract_document_function_rejects_unexpected_kwargs`). The main plan
  (`roadmap-2-2-1.md`) already uses the corrected paths. The underlying
  claim is non-load-bearing (Rust is untouched this slice).
