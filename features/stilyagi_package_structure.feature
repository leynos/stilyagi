Feature: Stilyagi package structure

  Scenario: Importing the supported package boundaries
    Given the built Stilyagi package is available
    When I inspect the supported package boundaries
    Then the engine and model packages import successfully
    And the package reports a Markdown document extracted by Rust

  Scenario: Rejecting the legacy pure-Python fallback
    Given the built Stilyagi package is available
    When I import the legacy pure-Python fallback module
    Then the import fails with ModuleNotFoundError

  Scenario: Canonical workflows exercise the package smoke path
    Given the repository build spine is available
    When I inspect the canonical build workflows
    Then make build runs the development smoke check
    And make release runs the release artefact smoke check
    And CI uses the canonical Makefile smoke path
