"""What NM asks under "What I need from you" is answered in a window, each question in a box of its own, and the answers go
to NM as the advocate's next message, each under the question it answers (plan AN.37, D37 and D43, piece 37a). The shipped
script's own functions are run; the window itself is checked in the browser."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]

_CHECK = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('nm/app/app.js', 'utf8');
const start = source.indexOf('function needQuestions(');
const end = source.indexOf('\nfunction openNeedAnswers(', start);
assert.ok(start >= 0 && end > start, 'the shipped functions must be present');
const sandbox = {};
vm.runInNewContext(source.slice(start, end) + '\nthis.needQuestions = needQuestions; this.needAnswersMessage = needAnswersMessage;',
                   sandbox);

// The items of "What I need from you" as the page groups them: a dispute's name, what it asks; what to get for its case; the
// advocate's call across the disputes.
const items = [
  {kind: 'NEED_GROUP', text: 'Recovery of the loan'},
  {kind: 'ASK', text: 'When did the borrower receive the notice?'},
  {kind: 'NEED_CASE', text: 'The signed agreement', need: {what: 'The signed agreement', from_whom: 'the client',
                                                           why: 'It proves the terms.'}},
  {kind: 'NEED_GROUP', text: 'Possession of the shop'},
  {kind: 'NEED_ITEM', text: 'The lease deed', item: {need: 'The lease deed'}},
  {kind: 'YOUR_CALL', text: 'Your call'},
  {kind: 'ASK', text: 'Do you want to file both suits together?'},
  {kind: 'ASK', text: '   '},
];
const questions = sandbox.needQuestions(items);
assert.deepEqual(JSON.parse(JSON.stringify(questions)), [
  {group: 'Recovery of the loan', text: 'When did the borrower receive the notice?'},
  {group: 'Recovery of the loan', text: 'The signed agreement — from the client'},
  {group: 'Possession of the shop', text: 'The lease deed'},
  {group: null, text: 'Do you want to file both suits together?'},
]);

// Only what was answered is sent, in order, each under its question; a blank answer sends nothing for it.
const message = sandbox.needAnswersMessage(questions, ['On 3 March.', '', '  I will send it tomorrow. ', 'Yes, together.']);
assert.equal(message, 'My answers to your questions:\n\n'
  + 'On Recovery of the loan, you asked: “When did the borrower receive the notice?”\nMy answer: On 3 March.\n\n'
  + 'On Possession of the shop, you asked: “The lease deed”\nMy answer: I will send it tomorrow.\n\n'
  + 'You asked: “Do you want to file both suits together?”\nMy answer: Yes, together.');
// Nothing answered, nothing to send.
assert.equal(sandbox.needAnswersMessage(questions, ['', ' ', '', '']), '');
assert.deepEqual(JSON.parse(JSON.stringify(sandbox.needQuestions([]))), []);
"""


def test_each_question_gets_its_box_and_only_answered_ones_are_sent_under_their_question():
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped script"
    result = subprocess.run([node, "-e", _CHECK], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
                            check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_answers_window_is_offered_beside_what_nm_asks_and_sends_through_the_one_send():
    """The button sits in the "What I need from you" block of a saved answer, and the window sends through send() or, while
    this conversation's message is being answered, adds the answers to what is sent next - never to another conversation."""
    script = (ROOT / "nm/app/app.js").read_text(encoding="utf-8")
    block = script[script.index("if (el.kind === 'NEEDS' && Array.isArray(el.items))"):]
    block = block[:block.index("// A NOTE IN A SECTION'S PLACE")]
    assert "needQuestions(el.items)" in block and "openNeedAnswers(entry, questions)" in block
    window = script[script.index("\nfunction openNeedAnswers("):]
    window = window[:window.index("\n}\n") + 3]
    assert "activeDelivery.entry.context !== entry.context" in window and "send(message)" in window
    assert "usageUsedUp()" in window and "attachmentsBlockSend()" in window
