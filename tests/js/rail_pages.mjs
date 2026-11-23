// CONVERSATION HISTORY, TEN AT A TIME (owner decision O29; plan AN.23): the page asks for the first ten items and
// shows them; Load more adds the next ten each time, each item once; a press that fails says so and keeps what is
// shown; an answer that arrives after the list was replaced, or the session ended, paints nothing. The history lists
// conversations only (plan AN.57, D292): the earlier matter records the server lists after them are no rows, are not
// counted, and a page that would hold only them is not offered. Offline substitutes for the DOM and the network; not
// browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('const HISTORY_PAGE = ');
const end = app.indexOf('function restoredTurn(', start);
assert.ok(start >= 0 && end > start, 'the history list must be shipped');
const source = app.slice(start, end);

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.parent = null;
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.className = '';
    this.disabled = false;
    this.type = '';
    this.tabIndex = -1;
    this._text = '';
  }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  // The element a row is in, as the DOM's parentElement says (a failed open is said in the row's own list).
  get parentElement() { return this.parent; }
  set textContent(value) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this._text = String(value); }
  adopt(nodes) { nodes.forEach((node) => { if (node.parent) node.remove(); node.parent = this; }); }
  replaceChildren(...nodes) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this._text = ''; this.append(...nodes); }
  append(...nodes) { this.adopt(nodes); this.children.push(...nodes); }
  prepend(...nodes) { this.adopt(nodes); this.children.unshift(...nodes); }
  appendChild(node) { this.append(node); return node; }
  before(...nodes) {
    const parent = this.parent;
    parent.adopt(nodes);
    parent.children.splice(parent.children.indexOf(this), 0, ...nodes);
  }
  remove() {
    if (!this.parent) return;
    this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  focus() { focused = this; }
}

let focused = null;

function page() {
  const elements = new Map();
  const $ = (id) => { if (!elements.has(id)) elements.set(id, new Element('div')); return elements.get(id); };
  const requests = [];
  const opened = [];
  const state = { matterListGeneration: 0, sessionGeneration: 1, railGeneration: 0 };
  const selections = { count: 0 };
  const behaviour = { chat: () => Promise.resolve() };
  const context = vm.createContext({
    $, state, Set, Date, Number, document: { createElement: (tag) => new Element(tag) },
    api: (url) => new Promise((resolve, reject) => requests.push({ url, resolve, reject })),
    stateBlock: (kind, text) => { const block = new Element('div'); block.className = `state ${kind}`; block.textContent = text; return block; },
    selectMatterRow: () => { selections.count += 1; },
    restorePendingChat: (chatId) => { opened.push(chatId); return behaviour.chat(chatId); },
  });
  vm.runInContext(source, context);
  return { context, $, requests, opened, state, selections, behaviour, body: $('rail-body'), meta: $('rail-meta') };
}

const chat = (n) => ({ chat_id: `chat-${n}`, preview: `First message ${n}`, turn_count: n, last_updated: '2026-10-20T10:00:00+00:00' });
const matter = (n) => ({ matter_id: `matter-${n}`, matter: `Earlier matter ${n}`, state: 'historical', last_updated: '2026-09-01T10:00:00+00:00' });
// The server's answer: 25 conversations, then 70 earlier matter records, ten items a page.
const answer = (chats, matters, extra = {}) => ({
  state: 'ok', chats, matters, chat_count: 25, row_count: 70, total: 95, offset: 0,
  has_more: true, next_offset: 10, unreadable: [], unavailable: [], ...extra });
const range = (from, to) => Array.from({ length: to - from }, (_, i) => from + i);
const settle = () => new Promise((resolve) => setImmediate(resolve));
const rows = (body) => body.children.filter((child) => child.dataset.chatId || child.dataset.matterId);
const ids = (body) => rows(body).map((row) => row.dataset.chatId || row.dataset.matterId);
const footer = (body) => body.children.find((child) => child.className === 'rail-more');
const part = (box, tag) => box.children.find((child) => child.tag === tag);
function press(button) {
  if (button.disabled) return;   // a button that is switched off gives no press
  (button.listeners.click || []).forEach((handler) => handler({}));
}
const firstPage = answer(range(1, 11).map(chat), []);

// The source asks for ten, never for the whole list.
assert.equal(vm.runInNewContext(`${source}; HISTORY_PAGE`, { Set, Date, Number, document: {}, $: () => ({}) }), 10);
assert.ok(!/api\('\/api\/work'\)/.test(app), 'the page must never ask for the whole history');

{
  // The first sight: ten conversations, in the server's order, with the count of the whole history's conversations and Load more.
  const p = page();
  const loading = p.context.loadMatterList();
  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].url, '/api/work?limit=10&offset=0');
  assert.equal(p.body.children[0].textContent, 'Loading your conversations…');
  p.requests[0].resolve(firstPage);
  await loading;
  assert.deepEqual(ids(p.body), range(1, 11).map((n) => `chat-${n}`));
  assert.equal(p.meta.textContent, '25 conversations', 'the count is of the whole history, conversations only');
  const more = footer(p.body);
  assert.ok(more && p.body.children[p.body.children.length - 1] === more, 'the button comes after the rows');
  assert.equal(part(more, 'button').textContent, 'Load more');
  assert.equal(part(more, 'button').disabled, false);
  assert.equal(part(more, 'p').textContent, 'Showing 10 of 25');
  assert.equal(part(more, 'p').attributes.role, 'status', 'the count is spoken as it changes');
  assert.ok(p.selections.count >= 1, 'the open conversation is marked');
  assert.equal(p.requests.length, 1, 'nothing more is asked for until it is pressed');
}

{
  // Load more asks where the server said the next page begins, adds the rows before the button, once each, and ends with the
  // last conversations: the earlier matter records on that page are no rows, and the pages after it, which hold only them, are not
  // offered.
  const p = page();
  const loading = p.context.loadMatterList();
  p.requests[0].resolve(firstPage);
  await loading;
  const button = part(footer(p.body), 'button');
  const before = p.selections.count;
  press(button);
  assert.equal(button.disabled, true, 'pressed once while it is being asked');
  assert.equal(part(footer(p.body), 'p').textContent, 'Loading more…');
  press(button);
  assert.equal(p.requests.length, 2, 'a second press while waiting asks for nothing');
  assert.equal(p.requests[1].url, '/api/work?limit=10&offset=10');
  p.requests[1].resolve(answer(range(11, 21).map(chat), [], { offset: 10, next_offset: 20 }));
  await settle();
  assert.deepEqual(ids(p.body).slice(10), range(11, 21).map((n) => `chat-${n}`));
  assert.ok(p.body.children[p.body.children.length - 1] === footer(p.body), 'the button stays last');
  assert.equal(part(footer(p.body), 'p').textContent, 'Showing 20 of 25');
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'Load more');
  assert.ok(focused === rows(p.body)[10], 'the focus goes to the first row that was added');
  assert.ok(p.selections.count > before);
  // The next press asks from where the second answer said; the server goes on to the earlier records, which are not shown.
  press(button);
  assert.equal(p.requests[2].url, '/api/work?limit=10&offset=20');
  p.requests[2].resolve(answer(range(21, 26).map(chat), range(1, 6).map(matter),
    { offset: 20, next_offset: 30, chat_count: 26, total: 96 }));
  await settle();
  assert.equal(footer(p.body), undefined, 'no conversation remains, so the button goes');
  assert.equal(ids(p.body).length, 25, 'ten, then ten, then the last five');
  assert.ok(ids(p.body).every((id) => id.startsWith('chat-')), 'no earlier matter record is a row');
  assert.ok(!p.body.textContent.includes('Earlier matter'));
  assert.equal(p.meta.textContent, '26 conversations', 'the count is taken from the latest answer');
  assert.equal(p.requests.length, 3);
}

{
  // Ten conversations or fewer: no button, whatever earlier records follow them.
  const p = page();
  const loading = p.context.loadMatterList();
  p.requests[0].resolve(answer(range(1, 4).map(chat), range(1, 8).map(matter), { chat_count: 3, row_count: 7, total: 10,
    has_more: false, next_offset: null }));
  await loading;
  assert.equal(footer(p.body), undefined);
  assert.equal(ids(p.body).length, 3);
  assert.equal(p.meta.textContent, '3 conversations');
}

{
  // The button is offered only when the server says there is more, says where it begins, and a conversation is there.
  for (const [label, extra] of [['has_more is false', { has_more: false, next_offset: 10 }],
                                ['no next page is named', { has_more: true, next_offset: null }],
                                ['only earlier records follow', { has_more: true, next_offset: 10, chat_count: 10 }]]) {
    const p = page();
    const loading = p.context.loadMatterList();
    p.requests[0].resolve({ ...firstPage, ...extra });
    await loading;
    assert.equal(footer(p.body), undefined, label);
    assert.equal(ids(p.body).length, 10, label);
  }
}

{
  // A conversation moved down by a newer one is not listed twice, and the count shown is of what is shown.
  const p = page();
  const loading = p.context.loadMatterList();
  p.requests[0].resolve(firstPage);
  await loading;
  const button = part(footer(p.body), 'button');
  press(button);
  p.requests[1].resolve(answer([chat(10), ...range(11, 20).map(chat)], [], { offset: 10, next_offset: 20, chat_count: 35 }));
  await settle();
  assert.equal(ids(p.body).length, 20 - 1);
  assert.equal(new Set(ids(p.body)).size, ids(p.body).length, 'every item once');
  assert.equal(part(footer(p.body), 'p').textContent, 'Showing 19 of 35');
  // A page of nothing but repeats leaves the button usable and the focus on it.
  press(button);
  assert.equal(p.requests[2].url, '/api/work?limit=10&offset=20', 'where the server said, not where the page counted');
  p.requests[2].resolve(answer([chat(5), chat(1)], [], { offset: 20, next_offset: 30, chat_count: 35 }));
  await settle();
  assert.equal(ids(p.body).length, 19);
  assert.equal(button.disabled, false);
  assert.ok(focused === button);
}

{
  // A press that fails says so, keeps the rows, and asks for the same page again when pressed again.
  const p = page();
  const loading = p.context.loadMatterList();
  p.requests[0].resolve(firstPage);
  await loading;
  const button = part(footer(p.body), 'button');
  const shown = ids(p.body);
  press(button);
  p.requests[1].reject(new Error('The server did not answer'));
  await settle();
  assert.deepEqual(ids(p.body), shown, 'what is shown stays');
  assert.equal(part(footer(p.body), 'p').textContent, 'More could not be loaded: The server did not answer. What is shown stays.');
  assert.equal(button.textContent, 'Try again');
  assert.equal(button.disabled, false);
  press(button);
  assert.equal(p.requests[2].url, '/api/work?limit=10&offset=10', 'the same page is asked for again');
  p.requests[2].resolve(answer(range(11, 21).map(chat), [], { offset: 10, next_offset: 20 }));
  await settle();
  assert.equal(ids(p.body).length, 20);
  assert.equal(button.textContent, 'Load more');
  assert.equal(part(footer(p.body), 'p').textContent, 'Showing 20 of 25');
}

{
  // A list that is replaced while a press is being answered, or a session that ends, is not painted over.
  for (const change of ['the list is opened again', 'the session ends']) {
    for (const how of ['answers', 'fails']) {
      const p = page();
      const loading = p.context.loadMatterList();
      p.requests[0].resolve(firstPage);
      await loading;
      const button = part(footer(p.body), 'button');
      press(button);
      const old = footer(p.body);
      if (change === 'the list is opened again') p.state.matterListGeneration += 1;
      else p.state.sessionGeneration += 1;
      const now = p.body.children.slice();
      if (how === 'answers') p.requests[1].resolve(answer(range(11, 21).map(chat), [], { offset: 10, next_offset: 20 }));
      else p.requests[1].reject(new Error('late'));
      await settle();
      assert.equal(p.body.children.length, now.length, `${change}, then the old press ${how}: nothing is painted`);
      now.forEach((node, index) => assert.ok(p.body.children[index] === node, `${change}, then the old press ${how}: position ${index}`));
      assert.equal(part(old, 'p').textContent, 'Loading more…', 'the old footer is left alone');
    }
  }
}

{
  // The first request failing is still said as a failure to read, never an empty list; no button.
  const p = page();
  const loading = p.context.loadMatterList();
  p.requests[0].reject(new Error('503'));
  await loading;
  assert.match(p.body.children[0].textContent, /The matter list could not be built: 503\. This is a failure to read, not a statement that you have no matters\./);
  assert.equal(p.meta.textContent, 'Matter list unavailable');
  assert.equal(footer(p.body), undefined);
}

{
  // No conversation at all says so - earlier records or none; a partial history keeps its notice at the top, above the rows and
  // the button.
  for (const matters of [[], range(1, 4).map(matter)]) {
    const empty = page();
    const loading = empty.context.loadMatterList();
    empty.requests[0].resolve(answer([], matters, { chat_count: 0, row_count: matters.length, total: matters.length,
      has_more: false, next_offset: null }));
    await loading;
    assert.equal(empty.body.children[0].textContent, 'No conversations yet. Start one with + New matter.');
    assert.equal(empty.meta.textContent, '0 conversations');
  }
  const partial = page();
  const second = partial.context.loadMatterList();
  partial.requests[0].resolve({ ...firstPage, state: 'partial', unavailable: ['m_lost'], unreadable: ['m_lost'] });
  await second;
  assert.match(partial.body.children[0].textContent, /Some work could not be loaded\. This list may be incomplete\./);
  assert.ok(partial.body.children[partial.body.children.length - 1] === footer(partial.body));
}

{
  // Rows on a later page open as the first page's do.
  const p = page();
  const loading = p.context.loadMatterList();
  p.requests[0].resolve(firstPage);
  await loading;
  press(part(footer(p.body), 'button'));
  p.requests[1].resolve(answer([chat(19)], [matter(40)], { offset: 10, next_offset: 20 }));
  await settle();
  assert.deepEqual(ids(p.body).slice(10), ['chat-19'], 'the earlier record on that page is no row');
  const later = rows(p.body)[10];
  assert.equal(later.attributes.role, 'button');
  assert.equal(later.tabIndex, 0);
  later.onclick();
  const key = rows(p.body)[0];
  key.listeners.keydown[0]({ key: ' ', preventDefault() {} });
  assert.deepEqual(p.opened, ['chat-19', 'chat-1']);
  assert.match(later.attributes['aria-label'], /^Open conversation: First message 19$/);
}

{
  // A conversation that cannot be opened from the list says so at the top of it - unless the list has been replaced.
  for (const replaced of [false, true]) {
    const p = page();
    const loading = p.context.loadMatterList();
    p.requests[0].resolve(firstPage);
    await loading;
    press(part(footer(p.body), 'button'));
    p.requests[1].resolve(answer([chat(19)], [], { offset: 10, next_offset: 20 }));
    await settle();
    const later = rows(p.body).find((row) => row.dataset.chatId === 'chat-19');
    p.behaviour.chat = () => Promise.reject(new Error('It is not there'));
    const attempt = later.onclick();
    if (replaced) p.state.matterListGeneration += 1;
    await attempt;
    const said = p.body.children[0].textContent;
    if (replaced) assert.ok(!said.includes('could not be read'), 'a replaced list is not painted over');
    else assert.equal(said, 'The chat could not be read: It is not there');
  }
}
console.log('rail pages: ok');
