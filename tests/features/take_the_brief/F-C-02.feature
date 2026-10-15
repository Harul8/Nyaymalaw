# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-C-02, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-C-02 Dictate the brief with the mic, transcribed on this installation

  Scenario: The mic sits beside the plus and puts what was said into the brief for checking
    Given the page
    And the page script
    Then beside the plus button there is a mic button that starts recording and stops on a second press
    And the words come back into the brief box to be checked, and nothing is sent by itself

  Scenario: Dictation goes to GPT Transcribe and the recording is not kept
    Given the dictation model
    When an advocate sends a short recording to be transcribed
    Then the words come back and the recording is not stored anywhere
    And the recording went to GPT Transcribe with the dictation prompt

  Scenario: Dictation without the AI agreement says so
    When an advocate who has not accepted AI processing dictates
    Then dictation is refused, saying AI processing needs their permission
