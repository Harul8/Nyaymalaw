# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-08, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-08 Sign in with an email address or an existing advocate ID; register with email only

  Scenario: The sign-in field takes an email address or an advocate ID
    Given the sign-in page
    Then the sign-in field is labelled "Email or advocate ID" and does not insist on an email address

  Scenario: An account that has an advocate ID signs in with it
    Given an existing account with the advocate ID "adv_legacy"
    When they sign in with that advocate ID and the right password
    Then sign-in succeeds

  Scenario: Registration takes only an email address
    When a visitor tries to register with "adv_newcomer" instead of an email address
    Then registration is refused asking for an email address
    And no account exists for "adv_newcomer"
