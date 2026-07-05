# Markdown suppression directives surface in the IR

Feature: Markdown suppression directives surface in the IR

  Scenario: A canonical ignore-next directive becomes a suppression
    Given a Markdown document with a "stilyagi: ignore-next PUN201" comment
    When the document is extracted
    Then the IR suppressions contain one inline entry naming PUN201
    And the suppression span re-slices to the directive comment

  Scenario: A blanket directive is refused
    Given a Markdown document with a "stilyagi: disable" comment naming no code
    When the document is extracted
    Then the IR suppressions are empty
    And the IR errors contain a blanket-forbidden entry
