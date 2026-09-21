# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-02, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-02 Register a private account with email and password

  Scenario: The register card shows the registration details and the privacy notice
    Given the sign-in page
    Then the register card has exactly an email field, a password field, a retype-password field and two privacy boxes
    And the register card has a Register button and a Back to sign in link
    And the register card states the password rules
    And the register card carries only account details, delivery status and confirmation navigation

  Scenario: Email and password create an account without an invitation
    When a visitor registers "new@example.com" with a valid password typed twice
    Then the account is created
    And the response carries no recovery code or any other secret
    And they can sign in with that email and password

  Scenario: Mismatched passwords create nothing
    When a visitor registers "typo@example.com" with two different passwords
    Then registration is refused with "do not match"
    And no account exists for "typo@example.com"

  Scenario: A password that breaks the rules creates nothing
    When a visitor registers "weak@example.com" with the password "weak"
    Then registration is refused naming the password rule
    And no account exists for "weak@example.com"

  Scenario: Registering an email twice never replaces the first password
    Given a registered advocate "reader@example.com"
    When a visitor registers "READER@example.com" again with a different password
    Then the response does not say whether the account exists
    And the original password still signs in
