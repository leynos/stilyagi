# Architectural decision record (ADR) 0014: Publish the sdist and make releases idempotent

## Status

Accepted. A tag publishes native wheels and exactly one source distribution to
PyPI, attests every artefact, mirrors the same bytes to the tag's GitHub
Release, and completes a re-run of the same tag without uploading anything new.

## Date

2026-11-04.

## Context and problem statement

Stilyagi had no release pipeline. `smoke.yml` built wheels on three platforms
and installed them, but it published nothing: it proved the PyO3 boundary
rather than shipping it. The repository is now at its first release, so the
question is no longer whether to publish but what a published tag must mean.

Four constraints shaped the answer, and each rules out the obvious shortcut:

- **A source distribution must be publishable.** PyPI accepts a project page
  that carries an sdist and wheels, and downstream packagers — Linux
  distributions in particular — build from the sdist rather than the wheel
  built for a different platform. A release that is wheels only silently
  excludes them.
- **A tag can be pushed twice.** Fixing a broken workflow and re-running, or
  re-pushing a corrected tag, must converge on the published release rather
  than fail on "file already exists". PyPI rejects a second upload of an
  existing filename outright, so a naive re-run does not merely waste work; it
  fails.
- **Rebuilt artefacts are rarely byte-identical.** Re-running `maturin build`
  produces different bytes: build metadata, timestamps and ordering all move. A
  re-run that uploads a rebuilt wheel under an existing name is rejected by
  PyPI, and one that re-attaches a rebuilt wheel to the release leaves the two
  destinations holding different bytes under the same name.
- **The bytes must be attributable.** A published artefact should carry proof
  of which commit and which run produced it, and that proof should not be
  overwritten by the next run.

The reference implementation is
[`leynos/cuprum#488`](https://github.com/leynos/cuprum/pull/488), adopted here
with the names and destinations changed to Stilyagi's. Cuprum's repository
carries composite actions under `.github/actions/`; this repository has none,
so the steps those actions performed are inlined into the jobs.

## Decision drivers

- One tag, one outcome: every artefact the release promises reaches both
  destinations, or the GitHub Release stays a draft.
- Re-running the tag is safe, and is the normal repair for a failed release.
- No artefact is ever overwritten, in either destination.
- Nothing reaches PyPI or GitHub that was not built and attested by a workflow
  run, so no developer machine can publish.
- The release jobs hold a token only for the destination they write to.

## Decision

### The reusable build workflow

`.github/workflows/build-wheels.yml` is a `workflow_call` workflow with
`permissions: {}` at the top level and per-job scopes beneath. It has three
jobs:

- `build-linux` builds `x86_64` and `aarch64` wheels in a matrix. Only the
  `aarch64` leg installs QEMU, and only the `x86_64` leg also builds the one
  sdist, with `uv build --sdist`, so exactly one source distribution exists per
  run. Both legs build through maturin 1.14.1 against `manylinux_2_28`.
- `build-hosted` builds the macOS `arm64` and `x86_64` wheels and the Windows
  wheel, since each of those targets needs its own runner.
- `verify-wheel-install` proves the wheel installs and that the sdist
  rebuilds. It is the step that makes "the sdist is publishable" a tested claim
  rather than an assumption.

`smoke.yml` keeps a job named `release-smoke`, which now delegates to this
workflow instead of repeating a matrix of its own. The smoke workflow therefore
exercises the same build the release uses, and a change to the build cannot
pass smoke while failing the release.

The sdist cardinality is asserted in three places: the build job counts the
sdists it produced, `verify-wheel-install` counts the sdists it received, and
`release.yml`'s `attest` job refuses to continue unless exactly one is present.
The redundancy is deliberate — the three checks guard different boundaries, and
the failure they prevent (two sdists, or none) is silent otherwise.

### The release workflow

`.github/workflows/release.yml` runs on `v*.*.*` tags, with
`cancel-in-progress: false` so a re-pushed tag queues behind the run it
replaces instead of interrupting an upload part-way through.

It has six jobs:

- `check-version` compares the tag with `crates/stilyagi-pyext/Cargo.toml` and
  with `pyproject.toml`, and derives the pre-release flag from the PEP 440
  label. It runs beside the build rather than before it, so a hosted check does
  not delay the paid build lane.
- `build-wheels` delegates to the reusable workflow.
- `attest` collects the built files, attests exactly those with
  `actions/attest-build-provenance`, and stages the Sigstore bundle under a
  run-unique name,
  `stilyagi-${GITHUB_REF_NAME}-run${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`, so a
  second run adds a record rather than colliding with the first.
- `draft-release` creates the tag's release as a draft, or reuses one that
  already exists, and downloads the assets it already holds.
- `publish-pypi` uploads through `pypa/gh-action-pypi-publish` under Trusted
  Publishing, with `skip-existing: true`.
- `publish-release` fills the release's gaps, verifies both destinations, and
  only then edits the release from draft to published.

Every network call stays in the workflow's own `curl` and `gh` invocations. The
decisions live in `scripts/release_assets.py`, which
`scripts/release_assets_cli.py` wraps in the command line the steps call. That
module resolves no third-party code, because it executes inside the job holding
the PyPI token.

Cuprum's `release-telemetry` composite action is not adopted. It writes to a
sink cuprum owns and Stilyagi has none; the run's logs and its attached
provenance bundle are the release record this repository keeps.

### The PyPI name

The `stilyagi` project on PyPI already exists: version 0.1.0 of a Vale-style
packaging tool, uploaded by this repository's maintainer, with its Repository
URL pointing at `leynos/stilyagi`. It is the predecessor of this compiler, not
an unrelated squatter, so the name is reused rather than replaced.

Two consequences follow. The first release must be a version higher than 0.1.0,
because PyPI rejects a second upload of an existing filename and a 0.1.0
release would be skipped entirely by the idempotency check; `0.2.0` is that
release. And the old files stay on the project page forever — PyPI does not
allow deletion of a release's files — so the README names the earlier tool and
this compiler as its successor rather than pretending the page was always this
project.

### Canonical bytes

Each filename's canonical bytes are, in order of precedence:

1. the bytes PyPI already holds under that name;
2. the bytes an existing asset on the tag's GitHub Release holds; and
3. this run's freshly built and attested file, only when neither destination
   has the name.

Each destination receives only the names it lacks. Nothing is overwritten:
PyPI's upload step never sees a name PyPI holds, and `gh release upload` is
invoked without `--clobber`. When the release's asset is the canonical source
for a name PyPI lacks, the release's bytes are copied over this run's rebuild
and sent to PyPI, so the two destinations converge on one byte string.

The release stays a draft until `verify` finds that PyPI and the GitHub Release
hold identical digests for every name and that this run's bundle is attached. A
disagreement leaves it a draft, which is visible only to a token that can write
contents — a failed release is not a public one.

### Network isolation

Each release job holds a token only for the destination it writes to:
`publish-pypi` holds `id-token: write` for Trusted Publishing and
`contents: read`; `draft-release` and `publish-release` hold `contents: write`
and no `id-token`. Every job checks out with `persist-credentials: false` and a
sparse checkout of `scripts/`, so no job carries a credential it does not need.

## Options considered

### Option A: Publish with `maturin publish` and `uv publish`

`maturin publish` builds and uploads in one step, and `uv publish` uploads an
existing directory. Both are simpler than what was adopted, and both are
rejected for the same two reasons: neither signs a PEP 740 attestation under
Trusted Publishing, and neither reconciles an existing release. A re-run would
fail on the first already-published filename, and the GitHub Release would not
be mirrored at all.

### Option B: Publish only wheels

This was the shape `smoke.yml` implied. It is rejected because it denies
source-based packagers a supported path, and because the sdist is the artefact
that proves the Rust build is reproducible from source rather than only
shippable from a prebuilt wheel.

### Option C: Delete and recreate the release on every run

Recreating the release would make a re-run converge trivially. It is rejected
because it discards the previous run's attestation bundle and makes the
release's notes and asset history churn on every attempt. Reuse-with-gap-fill
keeps the first published bytes canonical and leaves earlier bundles attached.

## Consequences

- A failed release is repaired by re-running the same tag, not by inventing a
  new version. The queued run reconciles against whatever the failed run
  published.
- The canonical byte for a name is decided by the destinations, not by the
  build, so the pipeline must be able to read PyPI's index and the release's
  assets before it can decide anything. Both are read in the same step that
  stages.
- `publish-release` needs `publish-pypi` to have completed, so PyPI is always
  the source of a release gap's bytes. That ordering is the mechanism, not an
  incidental detail: reversing it would let the release carry bytes PyPI never
  saw.
- The release jobs carry a copy of the PyPI index fetch as a YAML anchor
  (`*fetch-index`), so the retry policy is written once and used twice. The
  runner's `curl` cannot report `%{num_retries}`, so the loop retries network
  errors, 429 and 5xx itself; a 404 is an empty index, because a first release
  has no project page yet.
- A tag whose `pyproject.toml` version disagrees with the tag fails at
  `check-version` and never reaches an upload.
- The sdist is built only on `x86_64`. It is platform-independent, so building
  it once is correct, and building it per-leg would produce two sdists with
  different bytes under the same name.

## References

- [Issue #229](https://github.com/leynos/stilyagi/issues/229) requested the
  release process.
- [`leynos/cuprum#488`](https://github.com/leynos/cuprum/pull/488) is the
  reference implementation.
- [ADR 0002](adr-0002-ratify-the-packaging-boundary.md) records the packaging
  boundary the release publishes.
- [ADR 0011](adr-0011-pinned-nightly-and-build-standard.md) records the build
  standard the release builds under.
