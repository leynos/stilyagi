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