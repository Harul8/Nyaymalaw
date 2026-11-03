"""The page's side of what NM asks while it works (plan AN.37, D37-D40, D44): how an answer stands is said in words, a window
whose message is already answered sends its answers as the next message, and a saved answer shows what was asked. The shipped
script's own functions run in Node; the window itself is checked in the browser."""
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
const end = source.indexOf('function showConversationFromStart()', start);
assert.ok(start >= 0 && end > start, 'the shipped functions must be present');
function el(tag) {
  return { tagName: tag, className: '', children: [], text: '', attributes: {},
    set textContent(v) { this.text = String(v); this.children = []; },
    get textContent() { return this.text + this.children.map((c) => c.textContent).join(''); },
    appendChild(c) { this.children.push(c); return c; }, append(...c) { this.children.push(...c); },
    setAttribute(n, v) { this.attributes[n] = v; } };
}
const sandbox = { document: { createElement: el, createTextNode: (t) => Object.assign(el('#text'), { text: String(t) }) } };
vm.runInNewContext(source.slice(start, end) + '\nthis.turnQuestionAnswers = turnQuestionAnswers; this.askedLine = askedLine;'
                   + ' this.renderQuestionsAsked = renderQuestionsAsked;', sandbox);

const question = { id: 'q1', header: 'Your client', question: 'Whom do you act for?', default: ['The buyer'] };
assert.equal(sandbox.askedLine(question, { chosen: ['The seller'], other: '', how: 'answered' }), 'You answered: The seller');
assert.equal(sandbox.askedLine(question, { chosen: ['The buyer'], other: '', how: 'assumed' }),
             'No answer came in time, so NM went on assuming: The buyer');
assert.equal(sandbox.askedLine(question, { chosen: [], other: 'The bank', how: 'late' }),
             'You answered after NM had gone on: The bank');

// Once the message is answered, the answers go as the next message, each under its question.
assert.equal(sandbox.turnQuestionAnswers([question, { id: 'q2', question: 'Which court?' }],
                                         { q1: { chosen: ['The seller'], other: 'with a co-owner' } }),
             'My answers to your questions:\n\nYou asked: “Whom do you act for?”\nMy answer: The seller; with a co-owner');

// A saved answer shows what was asked above it, with how each answer came to stand.
const box = sandbox.renderQuestionsAsked({ questions: [question, { id: 'q2', question: 'Which court?' }],
  answers: [{ id: 'q1', chosen: ['The buyer'], other: '', how: 'assumed' }] });
assert.equal(box.attributes['aria-label'], 'What NM asked while working');
assert.match(box.textContent, /Whom do you act for\? No answer came in time, so NM went on assuming: The buyer/);
assert.match(box.textContent, /Which court\? Not answered\./);
"""


def test_how_each_answer_stands_is_said_and_a_closed_window_sends_the_answers_as_the_next_message():
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped script"
    result = subprocess.run([node, "-e", _CHECK], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
                            check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_progress_opens_the_window_once_and_offers_it_while_it_is_open():
    script = (ROOT / "nm/app/app.js").read_text(encoding="utf-8")
    poll = script[script.index("async function poll() {"):script.index("function watchProgress(") + 4000]
    assert "seen.asking === true && !entry.questionsSeen && !entry.questionsOpen" in poll
    working = script[script.index("function renderTurn(entry) {"):script.index("function showConversationFromStart()")]
    assert "if (progress.asking)" in working and "openTurnQuestions(entry)" in working
    window = script[script.index("async function openTurnQuestions("):script.index("function renderQuestionsAsked(")]
    # The answers go to the turn; once it has finished, as the next message - never to another conversation's message.
    assert "'/api/turn-question'" in window and "window_closed" in window
    assert "activeDelivery.entry.context === entry.context" in window
    assert "input.type = question.multiple ? 'checkbox' : 'radio'" in window
