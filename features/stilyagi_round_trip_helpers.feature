Feature: Internal round-trip test helpers
  Scenario: Source-backed edits preserve untouched text
    Given a source document for round-trip testing
    When I replace the editable middle span
    Then the round-trip helper preserves the surrounding text
