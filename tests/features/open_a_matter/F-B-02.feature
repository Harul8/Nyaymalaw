# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-02, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-02 The Board, one of each matter's own views

  Scenario: Each saved conversation has its own Conversation, Board, Documents and Research notes
    Given the page
    And the page script
    Then a saved conversation offers Conversation, Board, Documents and Research notes, and each shows only its own view

  Scenario: The Board is read from the conversation's saved understanding
    Given the page script
    Then the Board is read from the server for this conversation when it is chosen
    And a Board that cannot be read says so rather than showing an empty one
