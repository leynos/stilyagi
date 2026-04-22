Feature: Stilyagi package structure

  Scenario: Importing the supported package boundaries
    Given the built Stilyagi package is available
    When I inspect the supported package boundaries
    Then the engine and model packages import successfully
    And the package reports the Rust smoke greeting

  Scenario: Rejecting the legacy pure-Python fallback
    Given the built Stilyagi package is available
    When I import the legacy pure-Python fallback module
    Then the import fails with ModuleNotFoundError
