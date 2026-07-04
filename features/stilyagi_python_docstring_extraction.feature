Feature: Python docstring extraction

  Scenario: Extract Python docstrings with owner metadata
    Given the shared Python docstring fixture is available
    When I extract Python docstrings through the Python engine
    Then the Python document contains docstring regions
    And the Python IR records owner metadata

  Scenario: Recover from malformed Python through the Python engine
    Given the malformed Python docstring fixture is available
    When I extract Python docstrings through the Python engine
    Then the Python document contains the module docstring
    And the Python IR records a recoverable parse error
