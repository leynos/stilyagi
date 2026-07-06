# markdownlint-disable MD041

Feature: stilyagi check for Markdown files with nearest-config

  Scenario: check reports clean Markdown with exit code zero
    Given a temporary tree with two well-formed Markdown files
    When I run "stilyagi check ." in that tree
    Then the exit code is 0
    And the text output lists no diagnostics

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
