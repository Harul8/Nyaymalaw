# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-B-04, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-B-04 The matter's own tools sit in its header

  Scenario: The matter's own tools sit in its header
    Given the page script
    Then Matter cover & instructions, Attributed file and Protective handoff sit in the matter's header beside Case file and History
