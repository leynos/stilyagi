Feature: Owner-aware Rust documentation-comment extraction

  Scenario: Extract documentation comments with their owning items
    Given a Rust source file with crate, type, and function doc comments
    When the extractor runs for the rust_doc_comment syntax
    Then each doc-comment region records its prose text
    And each doc-comment region records its owning item kind and qualified name

  Scenario: Recover from a malformed Rust file
    Given a Rust source file whose function body never closes
    When the extractor runs for the rust_doc_comment syntax
    Then the crate documentation comment is still extracted
    And a recoverable Rust parse error is recorded
