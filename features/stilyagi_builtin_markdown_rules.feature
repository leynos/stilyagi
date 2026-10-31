# markdownlint-disable MD041

Feature: Builtin Markdown rules

  Scenario: report a heading depth jump with a manual fix
    Given a Markdown file has a level one heading followed by a level three heading
    When I run stilyagi check on the file with JSON output
    Then the second heading has an MD001 source span and a manual fix
    And applying fixes leaves the heading markers unchanged

  Scenario: require explicit opt-in for a repeated-word fix
    Given a Markdown file contains the repeated words "the the"
    When I run stilyagi check with fixes enabled
    Then STY001 is reported and the source file is unchanged
    When I run stilyagi check with unsafe fixes enabled
    Then the repeated suffix is removed and verification re-lint is clean

  Scenario: report configured banned terms only when selected
    Given configuration selects TERM001 with the term "obviously"
    And a Markdown paragraph contains "obviously"
    When I run stilyagi check on the file
    Then TERM001 reports the exact original UTF-8 byte span
    And no automatic fix is offered

  Scenario: anchor a per-file ignore at its own configuration directory
    Given a repository whose extended config ignores STY for "docs/*.md"
    And a Markdown document under "docs" repeats the word "the"
    And a Markdown document under "src" repeats the word "the"
    When I run stilyagi check from outside the repository on every document
    Then only the document outside the ignored tree reports STY001

  Scenario: resolve a stream filename against the working directory
    Given a repository whose extended config ignores STY for "docs/*.md"
    When I pipe the repeated word "the the" to stilyagi check named "docs/notes.md"
    Then no STY001 diagnostic is reported

  Scenario: report a stream file whose name misses the ignored glob
    Given a repository whose extended config ignores STY for "docs/*.md"
    When I pipe the repeated word "the the" to stilyagi check named "notes.md"
    Then STY001 is reported for the piped document

  Scenario: ignore the configuration when isolation is requested
    Given a repository whose extended config ignores STY for "docs/*.md"
    And configuration discovery is isolated
    When I pipe the repeated word "the the" to stilyagi check named "docs/notes.md"
    Then STY001 is reported for the piped document
