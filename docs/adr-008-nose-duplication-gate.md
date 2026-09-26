# Architectural decision record (ADR) 008: Adopt the `nose` code-duplication gate

## Status

Accepted.

## Date

2026-09-26.

## Context and problem statement

Stilyagi has a blocking tool gate for one class of latent defect — dead code,
checked by Skylos — but nothing that detects copy-paste duplication. The
repository is mixed Rust and Python: Rust owns source-fidelity extraction under
`crates/`, Python owns package integration and the rule-engine runtime under
`python/stilyagi/`. The Rust half is covered by Clippy and Whitaker; the Python
half has Ruff, Interrogate, two Pylint tiers, `ambrleaks`, and Skylos, none of
which observe duplication.

Duplication matters more than usual here because the Python half is a rule
runtime: two rules that share a near-identical helper, or two config validators
that diverge only in their diagnostic, tend to drift apart silently. Review
catches some of it; review is not deterministic and does not run on every
commit.

`leynos/episodic` solved the same problem and recorded the outcome in
[ADR-021](https://github.com/leynos/episodic/blob/d9e5ac0d254f375e2986f52d91a3b88c117c833b/docs/adr/adr-021-adopt-nose-duplication-gate.md)
at revision `d9e5ac0d254f375e2986f52d91a3b88c117c833b`, adopted through
[PR #276](https://github.com/leynos/episodic/pull/276). Its final approach uses
`nose` (`corca-ai/nose`), a Rust-built CLI that lowers many languages into one
intermediate representation and reports ranked clone families. This ADR adopts
that approach, scoped to Stilyagi's Python surface and adjudicated against
Stilyagi's own scan.

The earlier PyChase design described in the reference pull request's opening
description is **not** adopted: ADR-021 and the merged nose code supersede it.
Nor is its later replacement proposal, `pyscn`. Neither is adopted here, and
this ADR does not re-run the detector comparison — the choice is reused by
reference.

## Decision drivers

- Duplication must be blocked deterministically on every commit, not caught
  opportunistically in review.
- The gate must cost milliseconds, not seconds, so it can sit inside
  `make lint` without changing how often maintainers run the gate.
- Every exception must be reviewable in version control and attached to a
  written justification.
- No new heavyweight CI job, source build, or duplicate test suite.
- No change to the application's Python floor, dependency set, or runtime
  behaviour; the gate is tooling only.

## Options considered

### Option A: Adopt `nose` 0.20.0 behind a thin adjudication wrapper

Port episodic's five gate modules to `scripts/`, pin the detector in the
Makefile, CI, and `pyproject.toml`, and let `make lint` run the blocking gate
over `python/stilyagi`.

### Option B: Re-run the detector comparison for Stilyagi

Benchmark `nose` against PyChase and pyscn on Stilyagi's own corpus, then
choose.

### Option C: No automated duplication gate

Rely on review and the existing lint tiers.

| Topic                     | Option A                            | Option B                                        | Option C            |
| ------------------------- | ----------------------------------- | ----------------------------------------------- | ------------------- |
| Cost to adopt             | Port five modules and their tests   | Build a benchmark corpus and tune three tools   | Nothing             |
| Deterministic on commit   | Yes                                 | Yes, eventually                                 | No                  |
| Evidence base             | Episodic's benchmark, reused        | Stilyagi's own, but on a much smaller corpus    | None                |
| Risk of wrong tool choice | Low; the choice is already recorded | Low, but the corpus is too small to be decisive | Not applicable      |
| Review burden carried     | Four reasoned entries               | Four, adjudicated identically                   | Growing duplication |

_Table 1: Comparison of the three options._

Option B was rejected because Stilyagi's Python surface is small: a saturation
scan reports four families. A benchmark run over four families cannot
distinguish three detectors any better than episodic's larger corpus already
did, so re-running it would spend effort to reproduce a decision already
recorded at an immutable revision. Option C was rejected because the existing
tiers genuinely do not observe duplication, and "the maintainer will notice" is
the assumption that duplication accumulates fastest against.

## Decision outcome

In the context of keeping copy-paste duplication out of Stilyagi's Python
surface, facing a repository where no existing lint tier observes duplication
and where a detector choice has already been benchmarked and recorded upstream,
we decided **for** running `nose` 0.20.0 behind `scripts/duplication_gate.py`
inside `make lint`, installed by `make install-nose` through `cargo-binstall`
at a version pinned identically in the Makefile, the CI workflow, and
`[tool.nose]` and asserted by `tests/test_toolchain_contract.py`, with reasoned
location-keyed exceptions in `[tool.duplication_gate]`, and **against**
re-running the detector comparison for Stilyagi, adopting PyChase or pyscn, and
retaining no automated gate at all, to achieve deterministic duplication
enforcement whose exceptions stay reviewable in version control, accepting that
the gate depends on a pre-1.0, platform-specific binary published through
GitHub releases, that the detector reports spans without qualified unit names
so the narrowest available allow key is a path glob, and that the ranked
surface bounds what the gate adjudicates.

## Consequences

### Positive consequences

- `make lint` now fails on an unsuppressed duplication family, so duplication
  is blocked on every commit rather than caught in review.
- The scan is deterministic: repeated runs over an unchanged tree produce
  byte-identical output, so a failure is always a real change.
- Exceptions are ordinary TOML entries carrying a written reason, visible in a
  diff, and reported as stale once they silence nothing.
- The pin lives in one place per consumer and three contract tests keep the
  declarations in agreement, so a routine bump cannot leave local and CI runs
  disagreeing about which detector blocks the build.

### Negative consequences

- The gate depends on a pre-1.0 binary distributed as a platform-specific
  artefact from GitHub releases rather than as a Python package, so
  provisioning needs `cargo-binstall` and a cached `.tools/nose` in CI.
- `nose` reports spans without qualified unit names. Allow keys are therefore
  path globs with an optional `::name` suffix, and the narrowest key available
  for a fragment-level family is the whole file.
- Gating on a ranked surface bounds what the gate adjudicates. Stilyagi's
  ranking saturates below `top`, so the bound currently hides nothing, but that
  is a property of the present tree rather than a guarantee.

### Neutral or clarifying consequences

- The gate is tooling. The application's Python floor (`>=3.14`), dependency
  set, interpreter matrix, and runtime behaviour are unchanged.
- Skylos remains the first blocking tool gate; this is the second, from a
  different vendor, so it is a separate tool rather than an extension of Skylos.
- `scripts/` is reintroduced. It was a documented convention that had been
  emptied, and `docs/scripting-standards.md` already specifies `scripts/tests/`
  for script tests.

## Operational notes

- `make duplication` runs the gate alone and `make duplication-test` runs the
  helper tests. Record one exception with:

  ```shell
  make duplication-allow FIRST=<path[::name]> [SECOND=<path[::name]>] REASON='<why this stays>'
  ```

  `FIRST` and `REASON` are required and rejected when blank, so a mistyped
  invocation cannot record an empty or unexplained entry.
- The gate exits 0 for a clean or fully allowed scan, 1 for unsuppressed
  families, and 2 for configuration or tool-execution errors, including a
  missing binary, a version mismatch, a timeout, and a malformed report. A
  mistyped root surfaces as exit 2 rather than a vacuous pass, so an empty or
  misspelled scope cannot masquerade as a clean result.
- The allowlist writer is atomic and protected by a sidecar advisory lock
  (`.*.duplication-gate.lock`), so concurrent `make duplication-allow` runs do
  not lose updates. The lock coordinates processes that participate in the
  protocol; it does not constrain an editor writing `pyproject.toml` directly.
- `make install-nose` is a no-op when the installed binary already reports the
  pinned version. It passes `--disable-strategies compile,quick-install`, so a
  missing prebuilt artefact fails provisioning rather than starting a Rust
  build or falling back to an unapproved third-party build service. This is a
  deliberate deviation from the reference, which omits the flag.
- The scan covers `python/stilyagi` only. `tests/` is excluded because it
  reports 83 families, overwhelmingly assertion-shape and fixture-setup
  repetition; `scripts/` is excluded so the gate's own modules are not
  self-referential; and `crates/` is covered by Clippy and Whitaker rather than
  by a Python clone detector.
- `[tool.pytest.ini_options] testpaths = ["tests"]` keeps the gate's helper
  tests, which import the gate's own PEP 723 dependencies, out of a bare
  `pytest` run. `make duplication-test` names its files explicitly, and a path
  argument overrides `testpaths`, so that lane still collects them.

## Follow-on work

- Revisit the `top` bound if the ranked surface stays saturated as the package
  grows; the current "nothing is hidden" claim is measured, not guaranteed.
- Re-key exception entries on `path::name` wherever a future detector version
  starts supplying unit names, since that is strictly narrower than the whole
  file.
- Extending the scan to `tests/` would require adjudicating 83 families and is
  deliberately out of scope for this adoption.

## References

- [`leynos/episodic` PR #276](https://github.com/leynos/episodic/pull/276) and
  its
  [ADR-021](https://github.com/leynos/episodic/blob/d9e5ac0d254f375e2986f52d91a3b88c117c833b/docs/adr/adr-021-adopt-nose-duplication-gate.md)
  at revision `d9e5ac0d254f375e2986f52d91a3b88c117c833b`, the reference
  adoption this one follows.
- `corca-ai/nose` `v0.20.0`, the Rust-built `nose-cli` detector. Not the PyPI
  `nose` test framework of the same name.
- [ADR 004](adr-004-python-linting-architecture.md), the Python linting
  architecture this gate extends.
