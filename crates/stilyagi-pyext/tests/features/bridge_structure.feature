Feature: PyO3 bridge structure

  Scenario: Bridge delegates the smoke greeting to the core crate
    Given the bridge can call the shared smoke greeting
    When the bridge produces a hello greeting
    Then the greeting matches the core crate greeting

  Scenario: Bridge greeting is not the legacy Python fallback
    Given the bridge can call the shared smoke greeting
    When the bridge produces a hello greeting
    Then the greeting is not the legacy Python fallback
