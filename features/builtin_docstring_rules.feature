# markdownlint-disable MD041

Feature: Builtin documentation rules share the mixed-source rule loop

  Scenario: Python summary requires a separator
    Given DOC001 is enabled for Python docstrings
    And a function docstring contains "Read records." followed by "More detail."
    When the mixed-source tree is checked
    Then DOC001 points to the start of "More detail."

  Scenario: Rust summary punctuation is source located
    Given DOC002 is enabled for Rust documentation comments
    And an item has the documentation comment "/// Read records"
    When the mixed-source tree is checked
    Then DOC002 points to the final "s" in "records"
    And no automatic fix is offered for DOC002

  Scenario: Owner metadata distinguishes a redundant summary
    Given DOC003 is enabled
    And class Widget has the docstring "Widget."
    And class Other has the docstring "Widget."
    When the mixed-source tree is checked
    Then only the Widget docstring receives DOC003

  Scenario: Policy excludes ordinary comments and Markdown
    Given all three documentation rules are enabled
    And matching text occurs in Markdown and ordinary Python and Rust comments
    When the mixed-source tree is checked
    Then none of those surfaces receives a documentation rule diagnostic

  Scenario: Disabling a rule removes only its diagnostics
    Given all three documentation rules are enabled
    And DOC002 is disabled
    And the mixed-source tree has one offending summary for each rule
    When the mixed-source tree is checked
    Then DOC001 and DOC003 are reported but DOC002 is not

  Scenario: A Rust anonymous owner is skipped by the owner rule
    Given DOC003 is enabled
    And a Rust module documentation comment reads "Module."
    When the mixed-source tree is checked
    Then the module comment receives no DOC003

  Scenario: A blank separator passes the separation rule
    Given DOC001 is enabled for Python docstrings
    And a function docstring separates its summary with a blank line
    When the mixed-source tree is checked
    Then no DOC001 diagnostic is reported

  Scenario: Mixed-tree findings are ordered deterministically
    Given all three documentation rules are enabled
    And the mixed-source tree has one offending summary for each rule
    When the mixed-source tree is checked twice
    Then both runs report the same codes in the same order
