# markdownlint-disable MD041

Feature: stilyagi check applies conservative safe fixes

  Scenario: diff prints a patch and leaves the file untouched
    Given a Markdown file and a rule offering one safe source-backed fix
    When the fix command "stilyagi check . --diff" runs in that tree
    Then the fix command exits with code 1
    And standard output holds a unified diff that git apply accepts
    And standard error holds the diagnostic summary
    And the Markdown file on disk is unchanged

  Scenario: fix rewrites the file and exits zero
    Given a Markdown file and a rule offering one safe source-backed fix
    When the fix command "stilyagi check . --fix" runs in that tree
    Then the fix command exits with code 0
    And the Markdown file on disk contains the repaired text

  Scenario: unsafe fixes are withheld without the opt-in
    Given a Markdown file and a rule offering one unsafe source-backed fix
    When the fix command "stilyagi check . --fix" runs in that tree
    Then the Markdown file on disk is unchanged
    And the fix command exits with code 1
    And the text output offers the --unsafe-fixes option

  Scenario: unsafe fixes apply with the explicit opt-in
    Given a Markdown file and a rule offering one unsafe source-backed fix
    When the fix command "stilyagi check . --fix --unsafe-fixes" runs in that tree
    Then the fix command exits with code 0
    And the Markdown file on disk contains the repaired text

  Scenario: an edit against a synthetic span is refused
    Given a Markdown file and a rule offering a fix over a soft line break
    When the fix command "stilyagi check . --fix" runs in that tree
    Then the text output reports a synthetic-span fix error
    And the Markdown file on disk is unchanged

  Scenario: conflicting edits leave the whole file untouched
    Given a Markdown file and two rules offering different edits to one span
    When the fix command "stilyagi check . --fix" runs in that tree
    Then the text output reports an overlapping-edits fix error naming both rules
    And the text output states that the file was not modified
    And the Markdown file on disk is unchanged

  Scenario: identical edits from two rules coalesce
    Given a Markdown file and two rules offering the identical edit
    When the fix command "stilyagi check . --fix" runs in that tree
    Then the fix command exits with code 0
    And the Markdown file on disk contains the repaired text

  Scenario: a CRLF file keeps its line endings
    Given a CRLF Markdown file and a rule offering one safe source-backed fix
    When the fix command "stilyagi check . --fix" runs in that tree
    Then the Markdown file on disk still uses CRLF line endings
    And only the repaired bytes differ

  Scenario: standard input is never written to disk
    Given a Markdown file named notes.md on disk
    When the fix command "stilyagi check - --stdin-filename notes.md --fix" runs in that tree
    Then the fixed document is written to standard output
    And the Markdown file on disk is unchanged

  Scenario: combining fix and diff is a usage error
    Given a tree holding two Markdown files and an injected rule
    When the fix command "stilyagi check . --fix --diff" runs in that tree
    Then the fix command exits with code 2
    And the standard error reports that --fix and --diff conflict
