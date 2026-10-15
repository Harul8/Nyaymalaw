# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-03, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-03 The list of matters, and opening one resumes it

  Scenario: The list of matters lists every saved conversation and says when it cannot be read
    Given the page script
    Then the list of matters is read from the server and lists every saved conversation
    And the open conversation is highlighted in the list
    And a list that cannot be read says so rather than looking empty

  Scenario: Choosing a conversation in the list resumes it
    Given the page script
    Then choosing a conversation in the list restores it
