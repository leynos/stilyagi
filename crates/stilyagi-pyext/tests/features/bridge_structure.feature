Feature: PyO3 bridge structure

  Scenario: Bridge delegates the smoke greeting to the core crate
    Given the bridge can call the shared smoke greeting
    When the bridge produces a hello greeting
    Then the greeting matches the core crate greeting

  Scenario: Bridge greeting is not the legacy Python fallback
    Given the bridge can call the shared smoke greeting
    When the bridge produces a hello greeting
    Then the greeting is not the legacy Python fallback

  Scenario: Bridge extracts a Markdown document through the Rust boundary
    Given the bridge can call the Rust extraction entrypoint
    When the bridge extracts a Markdown document
    Then the extracted document reports Markdown syntax
    And the extracted document preserves one source-backed region

  Scenario: Bridge extracts the shared Markdown fixture through the Rust boundary
    Given the bridge can call the Rust extraction entrypoint
    When the bridge extracts the shared Markdown fixture
    Then the extracted document reports Markdown syntax
    And the extracted document preserves the shared Markdown fixture

  Scenario: Bridge keeps blank Markdown compatibility region
    Given the bridge can call the Rust extraction entrypoint
    When the bridge extracts a blank Markdown document
    Then the extracted document reports Markdown syntax
    And the extracted document preserves no source-backed regions
