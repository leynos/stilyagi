Feature: Owner-aware Python docstring extraction

  Scenario: Extract docstrings with their owning symbols
    Given a Python source file with module, class, and function docstrings
    When the extractor runs for the python_docstring syntax
    Then each docstring region records its prose text
    And each docstring region records its owning symbol kind and qualified name

  Scenario: Recover from a malformed Python file
    Given a Python source file whose function signature never closes
    When the extractor runs for the python_docstring syntax
    Then the module docstring is still extracted
    And a recoverable parse error is recorded
