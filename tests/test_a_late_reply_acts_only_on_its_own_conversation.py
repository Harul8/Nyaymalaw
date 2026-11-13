"""A late reply acts only on its own conversation (plan AN.53, piece 53i; D224; the review's F-37).

The page waits in several places before it acts on what the server said: it saves the draft first, or it asks again every few
seconds. An advocate who opened another conversation during that wait was taken back to the first one, and the next message
went to it - or the open conversation was given the other's version, and its next message was refused as out of date. Whatever
the page does to the open conversation because a reply arrived, it now does only while the advocate is still in the
conversation the reply belongs to, asked again after every wait.

The shipped script's own functions run in Node, with the server and the screen stood in for. Each case is run twice: the
advocate stays (the reply acts, as before) and the advocate leaves during the wait (nothing of the open conversation changes).
Not a browser check.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]

_HARNESS = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('nm/app/app.js', 'utf8');
function slice(from, to) {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert.ok(start >= 0 && end > start, `the shipped script must hold: ${from}`);
  return source.slice(start, end);
}
const shipped = [
  slice('function ownsIntent(intent) {', 'function matchesIntake('),
  slice('function followPending(intent, pending, chatId) {', '// CONVERSATION HISTORY (owner, 16 Oct 2026)'),
  slice('async function deliver(entry) {', '// PLAN AN.48 (48f1, D167): A STEP THAT WENT ON BY ITSELF'),
  slice('const RECONNECT_EVERY_MS = ', '// CONTINUE (D70; D73 by itself after a restart)'),
  slice('async function discardTurn(entry) {', '// ADD TO A QUESTION WHILE IT IS WORKED ON'),
  slice('async function showSoFar(entry, chatId) {', '/* ------------------------------------------------------------------ wire'),
].join('\n');

// One page: two conversations, the server and the screen stood in for, every wait held until the case lets it go.
function page() {
  const did = [];
  const waits = { draft: [], api: [] };
  const held = (list, label) => new Promise((resolve, reject) => list.push({ label, resolve, reject }));
  const element = () => ({ value: '', placeholder: '', hidden: false, scrollTop: 0, scrollHeight: 0 });
  const elements = {};
  const sandbox = {
    did, waits, JSON, Number, Array, Boolean, Promise, Error, Object, AbortController,
    setTimeout: (run) => { Promise.resolve().then(run); return 0; },
    $: (id) => (elements[id] = elements[id] || element()),
    api: (address) => held(waits.api, address),
    saveProtectedDraft: (how) => (how && how.previousKey !== undefined ? held(waits.draft, 'draft') : Promise.resolve(true)),
    showThreadBoard: (matterId) => { did.push(`opened matter ${matterId}`); return Promise.resolve(); },
    restorePendingChat: (chatId) => { did.push(`opened conversation ${chatId}`); return Promise.resolve(); },
    takeTitle: (chatId) => { did.push(`took the title of ${chatId}`); },
    watchProgress: (entry, finished, stopped) => { sandbox.watch = { entry, finished, stopped }; return { stop() {} }; },
    intentKey: (matterId, chatId) => `key:${matterId || chatId || 'new'}`,
    intentContexts: new Map(),
    matchesIntake: () => false,
    COMPOSER_WAITING: 'waiting', COMPOSER_PROMPT: 'prompt',
  };
  for (const name of ['checkIdle', 'paintSend', 'repaint', 'snapshotIntent', 'restoreIntent', 'loadChatBoard', 'refreshTitle',
    'refreshStopped', 'renderQueued', 'updateWorkspace', 'loadUsage', 'nmFinished', 'releaseQueued', 'followAs', 'unfollow',
    'takePending', 'continueTurn', 'stepOutcome']) sandbox[name] = () => undefined;
  vm.runInNewContext(`
    let activeDelivery = null;
    let activeIntent = null;
    const state = { advocate: 'a@example.test', workspace: 'w', sessionGeneration: 1, ended: false, turns: [],
      matterId: null, matterVersion: null };
    ${shipped}
    this.page = { deliver, reconnect, followPending, discardTurn, showSoFar, state,
      open(intent) { activeIntent = intent; state.matterId = intent.matterId; state.matterVersion = intent.version; },
      delivering() { return activeDelivery; } };
  `, sandbox);
  const intent = (chatId, matterId, version) => ({ advocate: 'a@example.test', workspace: 'w', chatId, matterId, version,
    key: `key:${matterId || chatId || 'new'}`, pending: [], queued: [], intake: null });
  return { ...sandbox.page, did, waits, sandbox, intent };
}
const turns = async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); };
const entryOf = (context, more = {}) => ({ context, turnId: 't-1', request: { matter_id: context.matterId, chat_id: context.chatId },
  envelope: '{}', ...more });
const refused = (detail) => Object.assign(new Error('refused'), { status: 409, detail });

// Each case: the advocate is in the first conversation; `leaves` says whether another is opened during the wait.
async function answered(leaves) {
  const p = page();
  const first = p.intent(null, null, null);   // an opening not yet saved: the answer names its conversation and its matter
  const other = p.intent('c-other', 'm-other', 3);
  p.open(first);
  const done = p.deliver(entryOf(first));
  await turns();
  p.waits.api.shift().resolve({ chat_id: 'c-first', matter_id: 'm-first', matter_version: 7 });
  await turns();
  assert.equal(p.waits.draft.length, 1, 'the page saves the draft under its new name before it acts on the answer');
  if (leaves) p.open(other);
  p.waits.draft.shift().resolve(true);
  await done;
  return p;
}

async function inputOnly(leaves) {
  const p = page();
  const first = p.intent(null, null, null);
  const other = p.intent('c-other', 'm-other', 3);
  p.open(first);
  const done = p.deliver(entryOf(first));
  await turns();
  p.waits.api.shift().reject(refused({ committed: 'input_only', matter_id: 'm-first', matter_version: 7 }));
  await turns();
  assert.equal(p.waits.draft.length, 1);
  if (leaves) p.open(other);
  p.waits.draft.shift().resolve(true);
  await done;
  return p;
}

async function afterARestart(leaves) {
  const p = page();
  const first = p.intent('c-first', null, 5);
  const other = p.intent('c-other', 'm-other', 3);
  p.open(first);
  const done = p.reconnect(entryOf(first, { chatId: 'c-first' }));
  await turns();
  assert.equal(p.waits.api.length, 1, 'the page asks how the turn stands');
  if (leaves) p.open(other);
  p.waits.api.shift().resolve({ state: 'finished', chat_id: 'c-first' });
  await done;
  return p;
}

async function followed(leaves) {
  const p = page();
  const first = p.intent('c-first', null, 5);
  const other = p.intent('c-other', 'm-other', 3);
  p.open(first);
  p.followPending(first, { turn_id: 't-1', state: 'working', message: 'm' }, 'c-first');
  assert.ok(p.sandbox.watch, 'a turn worked on elsewhere is watched');
  if (leaves) p.open(other);
  p.sandbox.watch.finished();
  await turns();
  return p;
}

async function discarded(leaves) {
  const p = page();
  const first = p.intent('c-first', null, 5);
  const other = p.intent('c-other', 'm-other', 3);
  p.open(first);
  const done = p.discardTurn(entryOf(first, { chatId: 'c-first' }));
  await turns();
  if (leaves) p.open(other);
  p.waits.api.shift().resolve({ matter_version: 9 });
  await done;
  return p;
}

async function workSoFar(leaves) {
  const p = page();
  const first = p.intent('c-first', null, 5);
  const other = p.intent('c-other', 'm-other', 3);
  p.open(first);
  const done = p.showSoFar(entryOf(first, { chatId: 'c-first' }), 'c-first');
  await turns();
  if (leaves) p.open(other);
  p.waits.api.shift().resolve({ title: 'The first conversation', pending: null });
  await done;
  return p;
}

const untouched = (p, what) => {
  assert.deepEqual(p.did, [], `${what}: nothing is opened over the conversation the advocate is now in`);
  assert.equal(p.state.matterId, 'm-other', `${what}: the next message still goes to the open conversation`);
  assert.equal(p.state.matterVersion, 3, `${what}: the open conversation keeps its own version`);
};
"""

_CASES = {
    "an_answer": r"""
(async () => {
  const stayed = await answered(false);
  assert.deepEqual(stayed.did, ['opened matter m-first']);
  assert.equal(stayed.state.matterId, 'm-first');
  assert.equal(stayed.state.matterVersion, 7);
  untouched(await answered(true), 'an answer that came after the advocate left');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "a_refusal_that_kept_the_message": r"""
(async () => {
  const stayed = await inputOnly(false);
  assert.deepEqual(stayed.did, ['opened matter m-first']);
  assert.equal(stayed.state.matterVersion, 7);
  const left = await inputOnly(true);
  assert.deepEqual(left.did, [], 'nothing is opened over the conversation the advocate is now in');
  assert.equal(left.state.matterVersion, 3, 'the open conversation keeps its own version');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "a_turn_followed_after_a_restart": r"""
(async () => {
  const stayed = await afterARestart(false);
  assert.deepEqual(stayed.did, ['opened conversation c-first']);
  untouched(await afterARestart(true), 'a turn that finished after a restart');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "a_turn_worked_on_elsewhere": r"""
(async () => {
  const stayed = await followed(false);
  assert.deepEqual(stayed.did, ['opened conversation c-first']);
  untouched(await followed(true), 'a followed turn that finished');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "the_work_so_far_of_a_turn": r"""
(async () => {
  const stayed = await workSoFar(false);
  assert.deepEqual(stayed.did, ['took the title of c-first']);
  untouched(await workSoFar(true), 'the work so far of a turn in a conversation the advocate left');
})().catch((error) => { console.error(error); process.exit(1); });
""",
    "a_discard": r"""
(async () => {
  const stayed = await discarded(false);
  assert.equal(stayed.state.matterVersion, 9);
  untouched(await discarded(true), 'a discard answered late');
})().catch((error) => { console.error(error); process.exit(1); });
""",
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_a_reply_that_comes_after_the_advocate_opened_another_conversation_changes_nothing_of_it(case):
    node = shutil.which("node")
    assert node, "NOT ASSESSED: Node is required to run the shipped script"
    result = subprocess.run([node, "-e", _HARNESS + _CASES[case]], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
