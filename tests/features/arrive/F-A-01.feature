# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-01, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-01 Sign in with email and password on a clean card

  Scenario: The sign-in card shows only its own content
    Given the sign-in page
    Then the sign-in card shows "Welcome back." and "Sign in to your practice workspace."
    And the sign-in card has an email field, a password field and a Sign in button
    And the sign-in card carries no logo and no text below its links

  Scenario: Forgot password and Register sit in one row under Sign in
    Given the sign-in page
    Then directly under the Sign in button there is one row as wide as the button
    And the row shows Forgot password on the left and Register on the right

  Scenario: A correct email and password opens the advocate's own workspace
    Given a registered advocate "reader@example.com"
    When they sign in with the right password
    Then sign-in succeeds
    And their own private workspace is named

  Scenario: A failed sign-in does not reveal whether the account exists
    Given a registered advocate "reader@example.com"
    When someone signs in as "reader@example.com" with a wrong password
    And someone signs in as "nobody@example.com" with any password
    Then both are refused with exactly the same message
