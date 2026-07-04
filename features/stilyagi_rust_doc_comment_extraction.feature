Feature: Owner-aware Rust documentation-comment extraction

  Scenario: Extract documentation comments with their owning items
    Given the shared Rust doc-comment fixture is available
    When I extract Rust doc comments through the Python engine
    Then the Rust document contains doc-comment regions
    And the Rust IR records owner metadata

  Scenario: Recover from a malformed Rust file
    Given the malformed Rust doc-comment fixture is available
    When I extract Rust doc comments through the Python engine
    Then the Rust document contains the crate doc-comment
    And the Rust IR records a recoverable parse error
