Feature: Structural performance probe

  Scenario: Maintainers can record cold and warm structural timings
    Given the shared Markdown structural fixture is available
    When I run the structural performance probe for cold and warm modes
    Then the probe writes a JSON report with cold and warm runs
