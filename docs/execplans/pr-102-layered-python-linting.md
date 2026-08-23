# PR #102: Configure layered Python linting

This ExecPlan is a completed record of the layered Python linting work in PR
#102. It is retained as a concise implementation history and retrospective.

Status: COMPLETE

## Constraints

- Keep Ruff as the first Python lint tier and retain the focused PyPy Pylint
  pass.
- Resolve `df12-python-lints` through the locked development environment under
  CPython 3.14, using immutable commit
  `9c835f35b0f1690597ade799c9c6a30bc5922959`.
- Run `ambrleaks` from the same locked environment and preserve the existing
  Rust lint stages and command order.
- Keep configuration validation and extraction contracts explicit in tests and
  maintainer documentation.

## Tolerances

- Documentation must describe the committed Makefile and `uv.lock` contracts;
  it must not infer a release version from package metadata that disagrees
  with the lockfile.
- The plan records implemented outcomes only where they are visible in the
  current source tree. Validation commands are listed separately until their
  output is available after these documentation changes.

## Risks

- A mutable tool reference or a documentation-only version correction could
  make local and CI lint environments appear different. The immutable commit
  and lockfile are the source of truth.
- Nested configuration mappings can accept invalid key types unless they pass
  through the shared mapping validator. Direct parser tests and a property
  test protect that boundary.
- Extraction vocabulary caches can retain patched bridge state across tests.
  The dedicated reset helper keeps test-only invalidation separate from the
  production extraction path.

## Progress

- [x] Configure the layered Ruff, Interrogate, focused PyPy Pylint, df12
  Pylint, `ambrleaks`, Rustdoc, Clippy, and Whitaker stages.
- [x] Pin the df12 source by immutable commit and run its Pylint stage under
  CPython 3.14.
- [x] Add the nested `ensure_mapping` regression coverage and the Hypothesis
  property for string-key acceptance and non-string-key rejection.
- [x] Document the extraction vocabulary helpers and their cache-reset
  boundary.
- [x] Align this record, ADR 004, and the developer's guide with `uv.lock`.

## Surprises & Discoveries

- `uv.lock` records the immutable source commit with package version 0.1.0;
  the lockfile is therefore more reliable for repository documentation than
  stale package metadata or a mutable release label.
- `ambrleaks` is available from the project-backed development environment, so
  it can share the same resolved df12 source as the CPython Pylint plugin.

## Decision Log

- Use `uv run --group dev --python 3.14` for both df12 commands so the project
  lockfile controls their source and dependencies.
- Keep the focused Pylint pass on `uv tool run --python pypy` with the pinned
  `pylint-pypy-shim`; it serves a different compatibility purpose.
- Treat extraction vocabulary caches as process-wide implementation state and
  expose reset semantics only through the test-only helper.

## Outcomes & Retrospective

The implementation delivered Ruff preview rules, `ASYNC`, `DOC`, and
NumPy-style documentation rules; Interrogate and focused PyPy Pylint;
`df12-python-lints` v0.1.0 under CPython 3.14; and `ambrleaks`. It also added
the focused `ensure_mapping` regression test, the Hypothesis property proving
string-key acceptance and non-string-key rejection, and documentation for the
extraction helper contracts.

The documentation changes in this follow-up add the ADR 004 addendum, align
the release wording with `uv.lock`, and make this plan discoverable from the
documentation index. The repository-configured validation commands that must
be run after these changes are:

```text
make markdownlint
make nixie
uv run --group dev pytest tests/test_config_schema.py
uv run --group dev pytest tests/test_config_schema_properties.py
```
