# markdownlint-disable MD041

Feature: Inspect and maintain Markdown CLI state

  Scenario: Inspect effective selection and its origin
    Given a project with one Markdown file and inherited lint selection
    When I inspect the selection with an extra rule
    Then JSON reports the combined value and config origin

  Scenario: Dump multiple Markdown documents as canonical JSON
    Given a project with two Markdown files containing Unicode and CRLF
    When I dump both files as IR
    Then the output is one array of canonical documents
    And the source bytes are unchanged

  Scenario: A later input failure emits no partial JSON
    Given a project with a readable and an invalid UTF-8 Markdown file
    When I dump both files as IR
    Then dump-ir exits two without writing stdout

  Scenario: Bypass a populated extraction cache
    Given a project with one clean Markdown file
    When I check it cold, warm, and with cache bypassed
    Then the checks have equal output and report miss, hit, and bypass

  Scenario: Frontmatter-only edits refresh cached source coordinates
    Given a project with cached YAML-frontmatter Markdown
    When I extend its frontmatter without changing the body
    Then the changed check misses and dump spans match current bytes

  Scenario: Clean owned cache state twice
    Given a project with a populated cache and an outside symlink
    When I clean the project twice
    Then cleanup removes only cache state and preserves both targets
