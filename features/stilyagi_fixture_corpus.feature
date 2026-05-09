Feature: Shared validation corpus

  Scenario: Shared validation corpus covers every v1 syntax
    Given the shared validation corpus is available
    When I inspect the fixture corpus
    Then every v1 syntax has valid and malformed fixtures
    And malformed fixtures can be read without executing them
