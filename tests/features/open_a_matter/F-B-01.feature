# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-01, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-01 Start a new matter in the conversation

  Scenario: A new matter opens straight into the conversation
    Given the page script
    Then New matter opens a new conversation with the message box ready and no form
    And the board says it fills in as NM understands the matter
    And the conversation history is read afresh each time it is opened
