# markdownlint-disable MD041

Feature: stilyagi check for Markdown files with nearest-config

  Scenario: check reports clean Markdown with exit code zero
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the text output lists no diagnostics

  Scenario: check discovers Markdown, Python, and Rust in one pass
    Given a temporary tree with Markdown, Python, and Rust source files
    And the extractor records selected syntaxes
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the selected syntaxes are Markdown, Python docstrings, and Rust doc comments

  Scenario: check attributes stdin to the supplied Rust filename
    Given a temporary tree with two well-formed Markdown files
    And the extractor records selected syntaxes
    When I run "stilyagi check - --stdin-filename src/lib.rs" in that tree
    Then the exit code is 0
    And the selected syntax is Rust documentation comments

  Scenario: check skips stdin with an unregistered filename
    Given a temporary tree with two well-formed Markdown files
    And the extractor records selected syntaxes
    When I run "stilyagi check - --stdin-filename main.go" in that tree
    Then the exit code is 0
    And no input was extracted

  Scenario: check emits JSON diagnostics in sorted path order
    Given a temporary tree with Markdown files "b.md", "a.md", and "sub/c.md"
    And the extractor emits one synthetic IR error per file
    When I run "stilyagi check . --output-format json" in that tree
    Then the exit code is 1
    And the diagnostics and processed paths follow sorted normalized order

  Scenario: check attributes stdin diagnostics to the supplied filename
    Given a temporary tree with two well-formed Markdown files
    And the extractor emits one synthetic IR error per file
    When I run "stilyagi check - --stdin-filename README.md" in that tree
    Then the exit code is 1
    And the text output attributes the synthetic diagnostic to "README.md"

  Scenario: check recovers malformed Markdown cleanly
    Given a temporary tree containing malformed Markdown
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the text output lists no diagnostics

  Scenario: check fails with exit code 2 on invalid configuration
    Given a temporary tree with an invalid stilyagi.toml
    When I run "stilyagi check ." in that tree
    Then the exit code is 2
    And the standard error reports an actionable configuration error

  Scenario: isolated mode ignores discovered configuration
    Given a temporary tree with a stilyagi.toml and a Markdown file
    When I run "stilyagi check . --isolated" in that tree
    Then the exit code is 0
    And the text output lists no diagnostics
