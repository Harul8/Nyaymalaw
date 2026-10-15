# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-18, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-18 A sign-in opens a new matter beside the list of matters

  Scenario: A sign-in opens a new matter beside the list of matters
    Given the page script
    Then a sign-in opens a new matter beside the list of matters
    And a sign-in after a session ended part-way through a brief goes back to that brief
