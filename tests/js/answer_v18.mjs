// Rendering v18 on the page (owner decisions P39-P41 and P44, 24 Oct 2026; plan AN.6 piece 6):
// "In short" as one table with the line on what to do first, each section's risks and next
// steps as lists, "More on this" folded, what NM needs grouped by dispute with each item opening
// in the reading pane, and the check's suggestions folded last. Runs the actual renderTurn from
// nm/app/app.js against a stub DOM, as render_turn_partition.mjs does; not browser QA.
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

function el(tag) {
  const node = {
    tagName: tag.toUpperCase(), className: '', children: [], _text: '', open: false, dataset: {}, style: {},
    hidden: false, attributes: {}, handlers: {}, colSpan: 1, scope: '', type: '',
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
const opened = [];
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
// An ask opens its item as the page wires it; what an item opens is the reading pane's, here recorded.
const real = context.window.NmBrainSources;
real.configure({ request: async () => ({}), scope: () => ({}),
  openAsk: (answer, element, ask, opener) => context.openAskedItem(answer, ask, opener) });
context.window.NmBrainSources = { ...real, showContent: (...args) => { opened.push(args[0]); } };

const para = (kind, text, section, unit, extra = {}) => ({
  kind, text, source: null, sources: [], refs: [], inline_citations: [], citation_markers: [], section, unit, ...extra });
const label = (kind, text, extra = {}) => ({
  kind, text, source: null, sources: [], refs: [], inline_citations: [], citation_markers: [], ...extra });
const item = { need: 'The cheque and the return memo', group: 'needed', status: 'not_given', why: 'It proves it.' };
const ask = { start: 11, end: 41, text: 'the cheque and the return memo', item,
  dispute: { id: 'D1', name: 'Cheque of Rs 4,80,000' } };
const box = (what, outside = false) => ({ ...label('WORKING', what), ...(outside ? { outside: true } : {}), working: {
  what, last_day: '2026-11-04', rows: [['Last day', '4 November 2026 (Wednesday)'], ['Result', 'Open'],
    ['Days left', '14']], lists: [] } });
const elements = [
  label('IN_SHORT', 'In short'),
  label('ROW', 'Cheque of Rs 4,80,000', { row: { status: 'shown', by_when: {
    what: 'Make a written complaint', last_day: '2026-11-04', day: '4 November 2026 (Wednesday)', result: 'Open',
    days: 14, days_label: 'Days left', as_of: '21 October 2026 (Wednesday)' } } }),
  para('ROW_ACTION', 'Criminal complaint under section 138', 1, 0),
  para('ROW_READY', 'Have ready the cheque and the return memo', 1, 1, { asks: [ask] }),
  label('ROW', 'Goods of Rs 2,10,000', { row: { status: 'note', why: 'the AI service did not respond' } }),
  para('DO_FIRST', 'File the cheque complaint first.', 'overview', 0),
  para('TIES', 'Both debts are owed by one buyer.', 'overview', 1),
  label('HEADING', 'Cheque of Rs 4,80,000: Criminal complaint under section 138', { dispute: 'Cheque of Rs 4,80,000' }),
  para('BASIS', 'On the dates you gave.', 1, 2),
  para('ADVICE', 'File by Wednesday 4 November 2026.', 1, 3),
  label('SUBHEAD', 'What could still go wrong', { section: 1 }),
  para('RISK', 'The presentation date is not given.', 1, 4),
  label('SUBHEAD', 'Next steps', { section: 1 }),
  para('STEP', 'Collect the originals.', 1, 5),
  para('STEP', 'File the complaint.', 1, 6),
  box('Make a written complaint'),
  para('MORE', 'Proof can be given by affidavit.', 1, 7),
  label('HEADING', 'Goods of Rs 2,10,000'),
  { ...label('FALLBACK', 'Not a full answer on Goods of Rs 2,10,000.'), disclosure: true,
    fallback: { facts: [], provisions: [], still_needed: [], questions: [] } },
  box('Sue for the price', true),
  label('NEEDS', 'What I need from you'),
  label('NEED_GROUP', 'Cheque of Rs 4,80,000'),
  label('NEED_ITEM', 'The cheque and the return memo', { item, dispute: { id: 'D1', name: 'Cheque of Rs 4,80,000' } }),
  para('ASK', 'Was any part-payment made before presentation?', 1, 8),
  label('YOUR_CALL', 'Your call'),
  para('ASK', 'Pursue both debts together, or separately?', 'overview', 2),
  label('CHECKED', 'How NM checked this answer', { checked: [{ part: 'Cheque of Rs 4,80,000', suggestions: [
    { kind: 'better', text: 'Say which court hears it.' }, { kind: 'could_go', text: 'A paragraph repeats itself.' }] }] }),
];
const turn = context.renderTurn({ brief: 'Two problems with one buyer.', answer: {
  turn_id: 't1', chat_id: 'c1', elements, metrics: { gates_fired: [], outcome: 'ok', latency_ms: 1, llm_calls: 1,
    tokens: { in: 1, out: 1 }, cost_usd: 0, violations: [], tier_downgrades: [] } } });

const all = [];
(function walk(node, parents) {
  all.push({ node, parents });
  for (const kid of node.children) walk(kid, [...parents, node]);
})(turn, []);
const find = (test) => all.filter(({ node }) => test(node));
const has = (name) => (node) => String(node.className).split(/\s+/).includes(name);

// In short: one table, a row for each dispute, the line on what to do first under it.
const [shortBox] = find(has('in-short'));
assert.ok(shortBox, 'In short is drawn');
const table = find(has('in-short-table'))[0].node;
const rows = table.children[1].children;
assert.equal(rows.length, 2);
const [name, action, when, ready] = rows[0].children.map((cell) => cell.textContent);
assert.deepEqual([name, action, ready], ['Cheque of Rs 4,80,000', 'Criminal complaint under section 138',
  'Have ready the cheque and the return memo']);
// By when: code's last day and the days left as of when it was worked out.
assert.ok(when.includes('2026') && when.endsWith('14 days left'), when);
assert.equal(rows[1].children[1].textContent, 'Not a full answer: the AI service did not respond.');
assert.equal(rows[1].children[1].colSpan, 3);
assert.ok(shortBox.node.textContent.includes('Days are counted as of 21 October 2026 (Wednesday).'));
assert.ok(shortBox.node.textContent.includes('Do first: File the cheque complaint first.'));
// The row's line on what to have ready keeps its ask, which opens the checklist item.
const asked = find((node) => has('ask-link')(node) && node.textContent === 'the cheque and the return memo');
assert.equal(asked.length, 1, 'the ask in the row opens its item');
asked[0].node.handlers.click({ preventDefault() {} });
assert.deepEqual(opened, ['The cheque and the return memo']);
opened.length = 0;

// Each section: risks a list, next steps numbered, More on this folded, the parts numbered.
const titles = find(has('part-title')).map(({ node }) => node.textContent);
assert.deepEqual(titles, ['Cheque of Rs 4,80,000: Criminal complaint under section 138', 'Goods of Rs 2,10,000']);
assert.equal(find((node) => node.tagName === 'UL' && has('risks')(node))[0].node.children.length, 1);
assert.equal(find((node) => node.tagName === 'OL' && has('steps')(node))[0].node.children.length, 2);
assert.deepEqual(find(has('answer-subhead')).map(({ node }) => node.textContent), ['What could still go wrong', 'Next steps']);
const more = find(has('more-fold'))[0].node;
assert.equal(more.tagName, 'DETAILS');
assert.equal(more.children[0].textContent, 'More on this');
assert.ok(more.textContent.includes('Proof can be given by affidavit.'));
// No disclosure is ever folded: the note in the goods section's place stays open.
for (const { node, parents } of find(has('disclosure'))) {
  assert.ok(!parents.some((parent) => parent.tagName === 'DETAILS'), 'a disclosure is inside a fold');
}
// The time limit no section names stands outside the parts; a section's own stays in it.
const tables = find(has('time-limits'));
assert.equal(tables.length, 2);
const inPart = (entry) => entry.parents.some(has('part-body'));
assert.deepEqual(tables.map(inPart), [true, false]);

// What I need from you: grouped by dispute, the item opening in the reading pane, Your call last.
const need = find(has('need'))[0].node;
assert.deepEqual(need.children.map((node) => node.className), ['need-title', 'need-group', 'need-list', 'need-group', 'need-list']);
assert.deepEqual(find(has('need-group')).map(({ node }) => node.textContent), ['Cheque of Rs 4,80,000', 'Your call']);
const open = find(has('need-item'))[0].node;
assert.equal(open.textContent, 'The cheque and the return memo');
open.handlers.click();
assert.deepEqual(opened, ['The cheque and the return memo']);
assert.ok(need.textContent.includes('Was any part-payment made before presentation?'));
assert.ok(need.textContent.includes('Pursue both debts together, or separately?'));

// How NM checked this answer: folded, last, by part, each suggestion said as what it is.
const checked = find(has('answer-checked'))[0].node;
assert.equal(checked.tagName, 'DETAILS');
assert.equal(checked.children[0].textContent, 'How NM checked this answer');
assert.ok(checked.textContent.includes('Could add or put better: Say which court hears it.'));
assert.ok(checked.textContent.includes('Could go: A paragraph repeats itself.'));
assert.ok(!find(has('part-body')).some(({ node }) => node.children.includes(checked)), 'the checks stand outside the parts');

console.log('answer v18: ok');
