# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-04, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-04 No recovery codes anywhere in the product

  Scenario: Nothing in the product offers, issues or accepts a recovery code
    When the served routes, the backend code, the page and the script are searched
    Then no recovery code is found anywhere

  Scenario: The sign-in page has no recovery-code option
    Given the sign-in page
    Then there is no "Use a recovery code" link and no recovery-code form

  Scenario: An older account's recovery-code data is removed at its next sign-in
    Given an older account that still holds recovery-code data
    When it signs in with its password
    Then the recovery-code data is gone from its record
    And its password is unchanged
