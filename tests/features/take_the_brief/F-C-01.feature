# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-C-01, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-C-01 Add documents, media or a voice note from the plus button

  Scenario: A plus button under the brief attaches documents, photos or recordings and records a voice note
    Given the page
    And the page script
    Then under the brief a plus button offers Attach documents, photos or recordings, and Record a voice note
    And there is no files bar above the chat

  Scenario: An attached file is read only after the malware check clears it
    When a clean file and a flagged file are attached
    Then the clean file is read and the flagged file is held unread with ClamAV's reason
