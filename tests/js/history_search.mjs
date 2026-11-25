// THE HISTORY'S SEARCH (plan AN.55, piece 55b; D254, D355(e)): the box at the head of the history asks the server for the
// conversations holding every word typed, once typing pauses or at once on Enter; the rows found are shown as the history is, ten
// at a time with Load more asking for the next page of the same search, each saying where its words were found, under a count
// that says what was searched; where nothing holds the words the page says what is and is not searched; an empty box is the
// whole history again. Runs the actual history code of nm/app/app.js against offline substitutes for the DOM, the clock and the
// network; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const start = app.indexOf('const HISTORY_PAGE = ');
const end = app.indexOf('function restoredTurn(', start);
assert.ok(start >= 0 && end > start, 'the history list must be shipped');
const source = app.slice(start, end);

class Element {
  constructor(tag) {
    Object.assign(this, { tag, children: [], parent: null, dataset: {}, attributes: {}, listeners: {}, className: '',
      disabled: false, _text: '' });
  }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this.children = []; this._text = String(value); }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  append(...nodes) { nodes.forEach((node) => { node.parent = this; }); this.children.push(...nodes); }
  prepend(...nodes) { nodes.forEach((node) => { node.parent = this; }); this.children.unshift(...nodes); }
  appendChild(node) { this.append(node); return node; }
  before(...nodes) { const at = this.parent.children.indexOf(this); this.parent.children.splice(at, 0, ...nodes); }
  remove() { if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  focus() {}
}

function page() {
  const elements = new Map();
  const $ = (id) => { if (!elements.has(id)) elements.set(id, new Element('div')); return elements.get(id); };
  const requests = [];
  const timers = [];
  const state = { matterListGeneration: 0, sessionGeneration: 1, railGeneration: 0 };
  const context = vm.createContext({
    $, state, Set, Date, Number, String, Array, encodeURIComponent, document: { createElement: (tag) => new Element(tag) },
    api: (url) => new Promise((resolve, reject) => requests.push({ url, resolve, reject })),
    stateBlock: (kind, text) => { const block = new Element('div'); block.className = `state ${kind}`; block.textContent = text; return block; },
    selectMatterRow: () => {},
    restorePendingChat: () => Promise.resolve(),
    historyWhen: () => '',
    setTimeout: (run, wait) => { timers.push({ run, wait }); return timers.length; },
    clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].run = null; },
  });
  vm.runInContext(source, context);
  const due = () => timers.splice(0).forEach((timer) => timer.run && timer.run());
  return { context, requests, state, due, body: $('rail-body'), meta: $('rail-meta') };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));
const found = (n, places) => ({ chat_id: `chat-${n}`, title: `Matter ${n}`, turn_count: 1, found_in: places });
const reply = (chats, extra = {}) => ({ state: 'ok', chats, chat_count: chats.length, total: chats.length, offset: 0,
  has_more: false, next_offset: null, unreadable: [], unavailable: [], ...extra });

{
  // Typing waits for a pause; only the last words typed are asked for, once.
  const p = page();
  p.context.searchHistory('Meh');
  p.context.searchHistory('Mehta  lease ');
  assert.equal(p.requests.length, 0, 'nothing is asked while typing');
  p.due();
  assert.equal(p.requests.length, 1);
  assert.equal(p.requests[0].url, '/api/work?limit=10&offset=0&q=Mehta%20%20lease', 'the words as typed, ends trimmed');
  assert.equal(p.body.children[0].textContent, 'Searching your conversations…');
  p.requests[0].resolve(reply([found(1, ['title', 'your messages'])], { searched: 'mehta lease' }));
  await settle();
  assert.equal(p.meta.textContent, '1 conversation found for “mehta lease”');
  const row = p.body.children.find((child) => child.dataset.chatId === 'chat-1');
  assert.equal(row.children.find((child) => child.className === 'hint found-in').textContent, 'Found in: title, your messages');
  // The same words again ask for nothing; Enter asks at once.
  p.context.searchHistory('Mehta  lease', { now: true });
  assert.equal(p.requests.length, 1);
  p.context.searchHistory('asha', { now: true });
  assert.equal(p.requests.length, 2);
  assert.equal(p.requests[1].url, '/api/work?limit=10&offset=0&q=asha');
}

{
  // Load more asks for the next page of the same search.
  const p = page();
  p.context.searchHistory('lease', { now: true });
  p.requests[0].resolve(reply(Array.from({ length: 10 }, (_, i) => found(i + 1, ['your messages'])),
    { chat_count: 12, has_more: true, next_offset: 10, searched: 'lease' }));
  await settle();
  const more = p.body.children.find((child) => child.className === 'rail-more');
  (more.children.find((child) => child.tag === 'button').listeners.click || []).forEach((handler) => handler({}));
  assert.equal(p.requests[1].url, '/api/work?limit=10&offset=10&q=lease');
}

{
  // Nothing found: said, with what is and is not searched; an empty box is the whole history again.
  const p = page();
  p.context.searchHistory('nothing holds this', { now: true });
  p.requests[0].resolve(reply([], { searched: 'nothing holds this' }));
  await settle();
  assert.equal(p.meta.textContent, '0 conversations found for “nothing holds this”');
  assert.equal(p.body.children[0].textContent, 'No conversation holds every one of these words. A title, the particulars and '
    + 'your own messages are searched; the words of answers and papers are not.');
  p.context.searchHistory('', { now: true });
  assert.equal(p.requests[1].url, '/api/work?limit=10&offset=0');
  p.requests[1].resolve(reply([], {}));
  await settle();
  assert.equal(p.body.children[0].textContent, 'No conversations yet. Start one with + New matter.');
}

{
  // A search over a history part of which could not be read says both.
  const p = page();
  p.context.searchHistory('lease', { now: true });
  p.requests[0].resolve(reply([], { state: 'partial', unreadable: ['m1'], searched: 'lease' }));
  await settle();
  assert.deepEqual(p.body.children.map((child) => child.className), ['state unbuildable', 'state empty']);
}

console.log('history_search.mjs: ok');
