# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-05, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-05 Only one logo on the screen at a time

  Scenario: The sign-in page shows the wordmark once, on the left
    Given the sign-in page
    Then the logo appears exactly once
    And it is on the left panel

  Scenario Outline: No card on the right repeats the logo
    Given the sign-in page
    Then the <card> card carries no logo

    Examples:
      | card             |
      | sign-in          |
      | register         |
      | forgot-password  |
      | set-new-password |
      | result           |
