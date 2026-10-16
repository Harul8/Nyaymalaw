# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-18, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-18 A sign-in opens a new matter with its board

  Scenario: A sign-in opens a new matter with its board
    Given the page script
    Then a sign-in opens a new matter with its board beside the conversation
    And a sign-in after a session ended part-way through a brief goes back to that brief
