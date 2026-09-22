# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-03, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-03 Reset a forgotten password through a link sent to the account email

  Scenario: The same answer whether or not the account exists
    Given a registered advocate "reader@example.com"
    When someone asks for a reset link for "reader@example.com"
    And someone asks for a reset link for "nobody@example.com"
    Then both get exactly the same answer
    And a reset email is queued only for the registered account

  Scenario: The link sets a new password once and signs out every device
    Given a registered advocate "reader@example.com" signed in on two devices
    And a reset link was sent to "reader@example.com"
    When the link is used to set a new valid password
    Then the password is changed and both earlier sessions are signed out
    And the old password no longer signs in
    And the new password signs in
    And using the same link again changes nothing

  Scenario: An expired link changes nothing
    Given a registered advocate "reader@example.com"
    And a reset link was sent to "reader@example.com"
    When the link is used 31 minutes later
    Then it is refused as not valid or expired
    And the original password still signs in

  Scenario: Mismatched new passwords do not use up the link
    Given a registered advocate "reader@example.com"
    And a reset link was sent to "reader@example.com"
    When the link is used with two different new passwords
    Then it is refused with "do not match"
    And the link still works afterwards

  Scenario: The link and the new password are never stored readable
    Given a registered advocate "reader@example.com"
    And a reset link was sent to "reader@example.com"
    When the link is used to set a new valid password
    Then neither the link nor the new password appears readable in any stored file
