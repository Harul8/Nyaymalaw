// What your papers record (plan AN.33, D20; piece 33m): every point NM read from the papers, folded at the end of the answer as
// code built it from the record - each event once, what NM could not find on a page and a date it finds nowhere said as such, the
// points read side by side with the differences between papers, what was set aside with why, and what could not be read. Runs the
// actual renderTurn from nm/app/app.js, with the board's event rows it reuses, against a stub DOM, as answer_v18.mjs does; not
// browser QA. The papers are invented.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const app = readFileSync(join(here, '..', '..', 'nm', 'app', 'app.js'), 'utf8');
const between = (start, end) => {
  const a = app.indexOf(start);
  const b = app.indexOf(end, a + start.length);
  if (a < 0 || b < 0 || b <= a) throw new Error(`renderer boundary moved: ${start}`);
  return app.slice(a, b);
};
const rendererSource = between('function appendReplyBody(', 'const REPLY_ICONS')
  + '\n' + between('function renderTurn(entry) {', 'function showConversationFromStart()')
  + '\n' + between('function showConversationFromStart()', 'function repaint()');
// The board's event rows and point labels, which the folded record reuses, stand within that stretch of the page's code.
if (!rendererSource.includes('function eventRows(') || !rendererSource.includes('const SIDE_BY_SIDE = ')) {
  throw new Error('renderer boundary moved: the board helpers the record reuses');
}

function el(tag) {
  const node = {
    tagName: tag.toUpperCase(), className: '', children: [], _text: '', open: false, dataset: {}, style: {},
    hidden: false, attributes: {}, handlers: {}, colSpan: 1, scope: '', type: '', title: '',
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set innerHTML(v) { this._text = String(v); },
    get innerHTML() { return this._text; },
    append(...kids) { for (const k of kids) this.children.push(k); },
    appendChild(k) { this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = kids; },
    addEventListener(name, handler) { this.handlers[name] = handler; },
    querySelector() { return el('span'); },
    querySelectorAll() { return []; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute() {},
    closest() { return null; },
    focus() {},
  };
  return node;
}
const byId = new Map();
const document = {
  createElement: el,
  createTextNode: (t) => Object.assign(el('#text'), { _text: String(t) }),
  getElementById: (id) => { if (!byId.has(id)) byId.set(id, el('div')); return byId.get(id); },
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, body: el('body'),
};
const context = {
  document, console, setTimeout, clearTimeout,
  window: { location: { hash: '', reload() {} }, addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  fetch: async () => ({ ok: true, status: 200, json: async () => ({}) }),
  navigator: { userAgent: 'node' },
  ResizeObserver: class { observe() {} },
  state: { matterId: null, ended: false, advocate: null },
  renderOpeningNote: () => el('div'), renderBoardNote: () => null,
  stateBlock: (_kind, message) => Object.assign(el('div'), { textContent: message }),
  replyFooter: (_entry, copyText) => Object.assign(el('div'), { copyText }),
  openSourceReader() {}, $: (id) => document.getElementById(id), withOpeningNotes: (turns) => turns,
  reconcileIntent() {},
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(readFileSync(join(here, '..', '..', 'nm', 'app', 'brain-sources.js'), 'utf8'), context,
  { filename: 'nm/app/brain-sources.js' });
vm.runInContext(rendererSource, context, { filename: 'nm/app/app.js' });

const label = (kind, text, extra = {}) => ({
  kind, text, source: null, sources: [], refs: [], inline_citations: [], citation_markers: [], ...extra });
const papers = {
  events: [
    { id: 'E1', date: '4-5-2003', dated: true, kind: 'transaction', what: 'A sale of 15 acres.', said_by: 'the deed',
      document: 'deed.pdf', pages: [1], words: 'Sale deed No. 418/2003 dated 4-5-2003', located: true,
      also_in: [{ document: 'copy.pdf', pages: [1] }] },
    { id: 'E2', date: '14-5-2003', dated: true, kind: 'statement', what: 'The buyer says the vendor sold him 12 acres.',
      said_by: 'the buyer', document: 'letter.pdf', pages: [], words: 'the vendor sold 12 acres to me', located: false },
    { id: 'E3', date: 'undated', dated: false, date_as_read: '9-9-2009', kind: 'pending', what: 'A suit is pending.',
      said_by: 'the letter', document: 'letter.pdf', pages: [1], words: 'the suit is pending', located: true },
  ],
  together: [{ id: 'C1', kind: 'papers_differ', point: 'The deed and the letter give the sale a different date.',
    why: 'Which date binds is open.', located: true,
    places: [{ document: 'deed.pdf', page: 1 }, { document: 'letter.pdf', page: 1 }] }],
  set_aside: [{ kind: 'event', document: 'letter.pdf', what: 'An order of the court.', why: 'No such order is on the pages.' }],
  unread: [{ document: 'notes.pdf', pages: '3-4' }],
};
const elements = [
  label('IN_SHORT', 'In short'),
  label('PAPERS', 'What your papers record', { papers }),
  label('CHECKED', 'How NM checked this answer', { checked: [] }),
];
const turn = context.renderTurn({ brief: 'Look at the sale.', answer: {
  turn_id: 't1', chat_id: 'c1', elements, metrics: { gates_fired: [], outcome: 'ok', latency_ms: 1, llm_calls: 1,
    tokens: { in: 1, out: 1 }, cost_usd: 0, violations: [], tier_downgrades: [] } } });

const all = [];
(function walk(node) { all.push(node); for (const kid of node.children) walk(kid); })(turn);
const has = (name) => (node) => String(node.className).split(/\s+/).includes(name);
const [fold] = all.filter(has('answer-papers'));
assert.ok(fold, 'the record of the papers is drawn');
assert.equal(fold.tagName, 'DETAILS', 'folded');
const text = fold.textContent;
for (const part of ['What your papers record (3 points)', 'whether or not the advice above takes it up',
  'In date order', '4-5-2003 ', 'A sale of 15 acres.', 'deed.pdf, page 1', 'also in copy.pdf, page 1',
  'NM could not find these words on the page; check the paper.',
  'Not dated in the paper', 'read as 9-9-2009, a date NM finds nowhere in your papers',
  'Read side by side', 'Where your papers differ: The deed and the letter give the sale a different date. — Which date binds is open.',
  'deed.pdf, page 1; letter.pdf, page 1',
  'Set aside after checking', 'An order of the court. · letter.pdf · No such order is on the pages.',
  'Not read', 'notes.pdf, pages 3-4: NM could not read these, so nothing on them is listed']) {
  assert.ok(text.includes(part), part);
}
assert.ok(!text.includes('9-9-2009 A suit'), 'a date found nowhere is never shown as the event\'s date');
// It stands outside the answer's parts, before how NM checked the answer.
const order = all.filter((node) => has('answer-papers')(node) || has('answer-checked')(node) && !has('answer-papers')(node));
assert.ok(order.length >= 1 && has('answer-papers')(order[0]), 'the record comes before the checks');

console.log('papers table: ok');
