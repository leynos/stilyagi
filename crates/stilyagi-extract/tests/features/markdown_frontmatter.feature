Feature: Markdown frontmatter remains source-backed

  Scenario: YAML frontmatter is represented by its complete fenced block
    Given the YAML frontmatter Markdown fixture
    When the Markdown fixture is extracted
    Then the frontmatter IR region is source-backed as YAML
