Feature: Markdown region coverage

  Scenario: Valid Markdown corpus covers promised v1 region kinds
    Given the promised v1 Markdown region kind vocabulary
    When the valid Markdown fixture corpus is extracted
    Then each promised v1 Markdown region kind is emitted at least once
