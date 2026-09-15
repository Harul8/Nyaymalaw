# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-A-09, column "Scenarios (Given / When / Then)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-A-09 Privacy notice and consent at registration

  Scenario: The register card shows the privacy notice itself, not a link to it
    Given the sign-in page
    Then the register card's notice names each detail kept and what it is for
    And the notice says how to withdraw consent, how to see, correct or erase the details, and how to complain to the Data Protection Board of India
    And the notice names Nyaymalaw, through Rahul Lambade, Founder & CEO, and the contact haaruln@gmail.com
    And the consent box and the 18-or-older box start unticked

  Scenario: Register waits for both boxes and sends them with the notice version
    Given the sign-in page
    Then the Register button stays unavailable until both boxes are ticked
    And the registration sends both boxes and the notice version the page shows
    And the notice version on the page is the one the server records

  Scenario Outline: A registration without full consent creates nothing
    When a visitor registers "<email>" <gap>
    Then registration is refused and nothing was saved
    And no account exists for "<email>"

    Examples:
      | email                 | gap                                        |
      | noconsent@example.com | without agreeing to the privacy notice     |
      | minor@example.com     | without confirming they are 18 or older    |
      | stale@example.com     | agreeing to an older version of the notice |
      | absent@example.com    | sending no consent at all                  |

  Scenario: The consent is recorded with the account
    When a visitor registers "consent@example.com" with a valid password typed twice
    Then the account record holds the notice version, the time of consent and the 18-or-older confirmation
