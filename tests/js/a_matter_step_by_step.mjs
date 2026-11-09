// A matter worked step by step (plan AN.48, piece 48a; owner decisions D134-D135, D147, D164), on the page: every message is sent
// step by step; a matter waiting for the advocate says what NM did and what comes next - not in red - with the go-aheads its stop
// offers and what NM noticed, offered and never done; each go-ahead goes by its own route; the history says where a conversation
// waits. Runs the actual functions of nm/app/app.js against offline substitutes for the DOM and the server; the words are invented.
// Not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
function fn(name) {
  const starts = [`\nfunction ${name}(`, `\nasync function ${name}(`];
  const at = Math.min(...starts.map((start) => app.indexOf(start)).filter((index) => index >= 0));
  assert.ok(Number.isFinite(at), `the page has ${name}`);
  const end = app.indexOf('\n}\n', at);
  return app.slice(at, end + 3);
}

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this._text = ''; this.attributes = {}; this.dataset = {}; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  click() { this.listeners.click && this.listeners.click(); }
}
const texts = (node) => [node._text, ...(node.children || []).flatMap(texts)].filter(Boolean);
const button = (node, text) => (node._text === text ? node : (node.children || []).map((child) => button(child, text)).find(Boolean));

// --- the stop (48a4) ---------------------------------------------------------------------------------------------------------------
{
  const gone = [];
  const context = vm.createContext({ document: { createElement: (tag) => new Element(tag) }, activeDelivery: null,
    goTurn: (entry, choice) => gone.push([entry.turnId, choice]), continueTurn: () => gone.push(['continue']),
    discardTurn: () => gone.push(['discard']), openAiSharing: () => {} });
  vm.runInContext(fn('renderWaiting') + fn('renderStopped'), context);
  const entry = { turnId: 't1', stopped: { code: 'waiting', why: 'NM is waiting for your go-ahead on this matter.',
    waiting: { after: 'understood', next: 'research',
      done_said: 'NM has read your papers and understood the matter: its disputes and their legal questions are on the board.',
      next_said: 'Next: research the law for each dispute.',
      gos: [{ choice: 'next', said: 'Go ahead: research' }, { choice: 'end_to_end', said: 'End to end' },
        { choice: 'done', said: 'Done: save as it stands' }],
      noticed: ['A time limit may have run: filing the appeal - the last day was 2026-10-01, 39 days ago.'] } } };
  const card = context.renderStopped(entry);
  assert.equal(card.className, 'waiting-card', 'waiting is not a failure: not red');
  assert.deepEqual(texts(card), [
    'NM has read your papers and understood the matter: its disputes and their legal questions are on the board.',
    'Next: research the law for each dispute.',
    'NM noticed, though you did not ask - say if you want it looked at:',
    'A time limit may have run: filing the appeal - the last day was 2026-10-01, 39 days ago.',
    'Go ahead: research', 'End to end', 'Done: save as it stands']);
  assert.ok(!texts(card).includes('Continue') && !texts(card).includes('Discard'));
  button(card, 'Go ahead: research').click();
  button(card, 'End to end').click();
  button(card, 'Done: save as it stands').click();
  assert.deepEqual(gone, [['t1', 'next'], ['t1', 'end_to_end'], ['t1', 'done']]);
  // While another answer is worked on, no go-ahead can be given.
  context.activeDelivery = { entry: {} };
  assert.equal(button(context.renderStopped(entry), 'Go ahead: research').disabled, true);
  // Any other stop is still the red message.
  context.activeDelivery = null;
  const red = context.renderStopped({ turnId: 't2', stopped: { code: 'stopped', why: 'You stopped NM.', finished: [],
    unfinished: [], needs: null, waiting: null } });
  assert.equal(red.className, 'failure stopped');
}

// --- each go-ahead goes by its own route (48a3) ---------------------------------------------------------------------------------
{
  const delivered = [];
  const context = vm.createContext({ activeDelivery: null, ownsIntent: () => true,
    deliver: (entry) => delivered.push([entry.endpoint, entry.envelope]) });
  vm.runInContext(fn('goTurn'), context);
  const entry = { turnId: 't1', context: { chatId: 'c1' }, stopped: { code: 'waiting' }, goError: 'earlier' };
  context.goTurn(entry, 'end_to_end');
  assert.deepEqual(delivered, [['/api/turn/go', JSON.stringify({ chat_id: 'c1', turn_id: 't1', choice: 'end_to_end' })]]);
  assert.equal(entry.stopped, null);
  assert.equal(entry.goError, null);
  context.activeDelivery = { entry: {} };
  context.goTurn(entry, 'next');
  assert.equal(delivered.length, 1, 'never while another answer is worked on');
}

// --- every message is sent step by step (D134) ----------------------------------------------------------------------------------
{
  const send = app.slice(app.indexOf('entry.envelope = JSON.stringify({\n    message: entry.brief'));
  assert.ok(send.slice(0, send.indexOf('});')).includes("steps: 'interactive'"), 'the envelope asks for steps');
}

// --- the history says where a conversation waits (D164) -------------------------------------------------------------------------
{
  const context = vm.createContext({ document: { createElement: (tag) => new Element(tag) }, state: { railGeneration: 1,
    sessionGeneration: 1 }, historyWhen: () => '', restorePendingChat: () => Promise.resolve() });
  vm.runInContext(fn('historyTitle') + fn('historyChatRow'), context);
  const row = context.historyChatRow({ chat_id: 'c1', preview: 'The shop lease', title: 'Shop lease', turn_count: 1,
    waiting: 'Waiting for you: research' }, 1, 1);
  assert.ok(texts(row).includes('Waiting for you: research'));
  const plain = context.historyChatRow({ chat_id: 'c2', preview: 'Another', title: 'Another', turn_count: 2 }, 1, 1);
  assert.ok(!texts(plain).some((text) => text.startsWith('Waiting')));
}

console.log('a matter step by step: ok');
