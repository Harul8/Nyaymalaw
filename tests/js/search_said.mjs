// The limits of the search, drawn under an answer (plan AN.51, piece 51e; D199, D253): code's account, worked out by the
// server from the saved research. The page only draws it: folded, its summary on the fold; a conversation opened from the
// history carries it with each turn, an answer just given is asked for once; an answer that searched nothing shows nothing.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const from = app.indexOf('// THE LIMITS OF THE SEARCH');
const to = app.indexOf('// LB-90.', from);
assert.ok(from >= 0 && to > from);

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this._text = ''; this.hidden = false; this.className = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(' '); }
  appendChild(node) { this.children.push(node); return node; }
}

function harness(reply) {
  const asked = [];
  const context = vm.createContext({
    document: { createElement: (tag) => new Node(tag) }, encodeURIComponent,
    api: async (url) => { asked.push(url); if (reply instanceof Error) throw reply; return reply; },
  });
  vm.runInContext(app.slice(from, to), context);
  return { context, asked };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));

const said = { summary: 'NM searched only the law it holds.', lines: ['2 questions were searched.', 'Currency is not checked.'] };
const saved = { chat_id: 'chat 1', turn_id: 't/1', blocked: false, committed: true };

// Opened from the history: the turn carries the account; it is drawn at once and nothing is asked of the server.
{
  const { context, asked } = harness({});
  const fold = context.searchSaid({ ...saved, search_said: said });
  assert.equal(fold.tag, 'details');
  assert.equal(fold.hidden, false);
  assert.equal(fold.className, 'answer-checked answer-search');
  assert.deepEqual(fold.children.map((child) => [child.tag, child.textContent]), [
    ['summary', 'How far NM searched: NM searched only the law it holds.'],
    ['p', '2 questions were searched.'], ['p', 'Currency is not checked.']]);
  assert.deepEqual(asked, []);
}

// An answer just given: asked for once, at its own address, hidden until it comes, and kept on the answer.
{
  const { context, asked } = harness({ search_said: said });
  const answer = { ...saved, committed: 'committed' };
  const fold = context.searchSaid(answer);
  assert.equal(fold.hidden, true);
  await settle();
  assert.deepEqual(asked, ['/api/chats/chat%201/turns/t%2F1/search-said']);
  assert.equal(fold.hidden, false);
  assert.equal(fold.children[0].textContent, 'How far NM searched: NM searched only the law it holds.');
  assert.equal(answer.search_said, said);
}

// A turn that searched nothing (a greeting): nothing is shown, from the history or just given.
{
  const { context, asked } = harness({ search_said: null });
  assert.equal(context.searchSaid({ ...saved, search_said: null }), null);
  const answer = { ...saved, committed: 'committed' };
  const fold = context.searchSaid(answer);
  await settle();
  assert.equal(fold.hidden, true);
  assert.equal(answer.search_said, null);
  assert.equal(asked.length, 1);
}

// Not a saved answer - one still being written, a refused one, one with no conversation - has no account and asks for none.
{
  const { context, asked } = harness({ search_said: said });
  assert.equal(context.searchSaid({ ...saved, committed: 'unconfirmed' }), null);
  assert.equal(context.searchSaid({ ...saved, committed: undefined }), null);
  assert.equal(context.searchSaid({ ...saved, blocked: true }), null);
  assert.equal(context.searchSaid({ turn_id: 't1', committed: true }), null);
  assert.equal(context.searchSaid(null), null);
  assert.deepEqual(asked, []);
}

// Plan AN.79 (D343): a conversation opened from the history - the answer as the page rebuilds it from the saved turn
// (restoredTurn) - draws the account the server sent with that turn, at once; a turn that searched nothing shows nothing.
// Before D343 the rebuilt answer carried neither field, so a reopened answer never showed it.
{
  const restore = app.slice(app.indexOf('function restoredTurn(turn) {'), app.indexOf('// LB-83. WHEN THE ANSWER WAS SAVED'));
  const asked = [];
  const context = vm.createContext({
    document: { createElement: (tag) => new Node(tag) }, encodeURIComponent,
    api: async (url) => { asked.push(url); return { search_said: said }; },
  });
  vm.runInContext(app.slice(from, to) + '\n' + restore, context);
  const turn = { committed: true, release_state: 'released', chat_id: 'chat 1', turn_id: 't/1', blocked: false, elements: [],
    message: 'Asked.', search_said: said };
  const fold = context.searchSaid(context.restoredTurn(turn).answer);
  assert.equal(fold.hidden, false);
  assert.equal(fold.children[0].textContent, 'How far NM searched: NM searched only the law it holds.');
  assert.equal(context.searchSaid(context.restoredTurn({ ...turn, search_said: null }).answer), null);
  assert.deepEqual(asked, [], 'a reopened answer asks the server for nothing');
  // A turn not established as saved and released is not an answer, and has no account.
  assert.equal(context.restoredTurn({ ...turn, committed: false }).answer, undefined);
}

// The account could not be fetched: that is said under the answer, in plain words, and the answer stands.
{
  const { context } = harness(new Error('HTTP 500'));
  const fold = context.searchSaid({ ...saved, committed: 'committed' });
  await settle();
  assert.equal(fold.hidden, false);
  assert.equal(fold.children.length, 1);
  assert.match(fold.children[0].textContent, /could not be shown just now/);
  assert.doesNotMatch(fold.textContent, /HTTP|500/);
}

console.log('search_said: ok');
