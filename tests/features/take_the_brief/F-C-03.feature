# GENERATED from docs/Nyaymalaw_Implementation_Plan.xlsx, row F-C-03, column "Executable scenarios (Gherkin)".
# Edit the sheet, then run `python assurance/control_plane/plan_scenarios.py --write`.
Feature: F-C-03 Live words while the advocate speaks

  Scenario: The words appear in the brief box as they are spoken
    Given the page
    And the page script
    Then the live words come from a socket and are written into the brief box as they arrive
    And the live words stop being written the moment the advocate edits them
    And the final transcription replaces the live words it stood in for

  Scenario: The microphone reaches the live model as it wants it, and not the speakers
    Given the page script
    Then the audio is sent as 16 kHz mono frames of about a tenth of a second
    And the page does not play the advocate's own voice back

  Scenario: The live socket authenticates itself
    When a stranger opens the live dictation socket
    Then the socket is refused before any audio is read
    And a socket opened from another page is refused the same way

  Scenario: The live words arrive while the advocate is still speaking
    Given the live dictation service
    When the page sends two frames of speech and then stops
    Then the words heard so far come back after each frame
    And the final words come back when it stops
    And no audio is stored anywhere

  Scenario: Live words that are not set up do not stop the dictation
    Given the page script
    When the live speech model is not downloaded and an advocate dictates
    Then the socket says the live words are off and the recording goes on
