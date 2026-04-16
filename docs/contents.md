# Documentation contents

- [Documentation contents](contents.md) lists the current documentation set and
  where each document fits.
- [Stilyagi design](stilyagi-design.md) is the primary technical design for the
  wholesale replacement of the current Vale-oriented repository with the new
  prose, documentation, comment, and docstring linter.
- [Roadmap](roadmap.md) sequences the implementation work into foundations and
  vertical slices, so the project can deliver useful functionality before the
  full architecture is complete.
- [Developer's guide](developers-guide.md) describes the maintainer-facing
  environment setup, Rust and Python boundaries, build workflow, and
  verification flow for the mixed PyO3 package.
- [Repository layout](repository-layout.md) maps the major repository paths,
  their responsibilities, and the generated or constrained directories that
  contributors should treat carefully.
- [Documentation style guide](documentation-style-guide.md) defines the
  repository-wide writing and Markdown conventions.
- [Scripting standards](scripting-standards.md) describes the expectations for
  shell and automation scripts in this repository.
- [Local validation with act and pytest](
  local-validation-of-github-actions-with-act-and-pytest.md) explains the
  current local workflow for validating GitHub Actions behaviour.
- [RFCs](rfcs/) capture narrower draft contracts and design inputs that feed the
  main design:
  - [RFC 0001: Stilyagi IR](rfcs/0001-stilyagi-intermediate-representation.md)
    proposes the initial IR contract between the Rust extractor and Python
    analysis engine.
  - [RFC 0002: Stilyagi Python rule API](rfcs/0002-stilyagi-python-rule-api.md)
    proposes the Python-facing rule model and plugin surface.
  - [RFC 0003: Stilyagi CLI contract](rfcs/0003-stilyagi-cli-contract.md)
    proposes the command surface, config discovery rules, and suppression
    semantics.
  - [RFC 0004: Stilyagi rule tests](rfcs/0004-stilyagi-rule-testing-framework.md)
    proposes a first-party pytest plugin for exercising rules, temporary
    packs, diagnostics, fixes, and IR output against the real Stilyagi engine.
