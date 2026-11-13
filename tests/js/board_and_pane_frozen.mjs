// THE MATTER BOARD AND THE READING PANE ARE FROZEN (plan AN.39, D60; owner, 4 Nov 2026: "after the above are implemented, freeze the UI
// and structure for matter board and reading pane -- unless there is an explicit approval from me, don't change it").
//
// This pins the structure and the fixed words of the board and of the pane - each element's tag, classes and, for headings, buttons and
// links, its words - as the actual renderers draw an invented matter. A failure here means the board or the pane would change: ask the
// owner, naming what would change, before changing anything; re-pin (node tests/js/board_and_pane_frozen.mjs --print) only after their
// explicit approval, and record it on the plan. Not browser QA: offline substitutes for the DOM, as the other page tests use.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(here, '..', '..', 'nm', 'app', name), 'utf8');
const app = read('app.js');
const between = (start, end) => {
  const a = app.indexOf(start);
  const b = app.indexOf(end, a + start.length);
  if (a < 0 || b < 0 || b <= a) throw new Error(`renderer boundary moved: ${start}`);
  return app.slice(a, b);
};

function el(tag) {
  return {
    tagName: tag.toUpperCase(), className: '', children: [], _text: '', open: false, dataset: {}, style: {}, hidden: false,
    attributes: {}, handlers: {}, type: '', title: '', value: '', isConnected: true,
    classList: { add() {}, remove() {} },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    append(...kids) { for (const k of kids) this.children.push(k); },
    appendChild(k) { this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = kids; this._text = ''; },
    addEventListener(name, handler) { this.handlers[name] = handler; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute() {}, focus() {}, show() { this.open = true; }, showModal() { this.open = true; }, close() { this.open = false; },
    dispatchEvent() {}, querySelector() { return null; }, querySelectorAll() { return []; }, closest() { return null; },
  };
}
const byId = new Map();
const document = {
  createElement: el,
  createTextNode: (t) => Object.assign(el('#text'), { _text: String(t) }),
  getElementById: (id) => { if (!byId.has(id)) byId.set(id, el('div')); return byId.get(id); },
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, body: el('body'),
};

// The outline of what a renderer draws: each element's tag and classes, and the words of headings, buttons, links and summaries.
const WORDED = new Set(['BUTTON', 'A', 'H3', 'H4', 'SUMMARY']);
function outline(node) {
  if (!node || node.tagName === '#TEXT') return null;
  const classes = String(node.className || '').trim().split(/\s+/).filter(Boolean);
  const name = [node.tagName.toLowerCase(), ...classes].join('.') + (WORDED.has(node.tagName) ? ` "${node.textContent}"` : '');
  const kids = (node.children || []).map(outline).filter(Boolean);
  return kids.length ? [name, kids] : name;
}
const outlines = (nodes) => Array.from(nodes, outline).filter(Boolean);

// The page's renderers, with the reading pane captured as it is given its content.
const opened = [];
const context = {
  document, console, setTimeout, clearTimeout,
  window: { location: { hash: '', reload() {} }, addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: { userAgent: 'node' }, ResizeObserver: class { observe() {} },
  state: { matterId: null, ended: false, advocate: null, turns: [] },
  renderOpeningNote: () => el('div'), renderBoardNote: () => null,
  stateBlock: (_kind, message) => Object.assign(el('div'), { textContent: message }),
  replyFooter: () => el('div'), openSourceReader() {}, $: (id) => document.getElementById(id), withOpeningNotes: (turns) => turns,
  reconcileIntent() {}, sizeComposer() {}, Event: class { constructor(type) { this.type = type; } },
  // Plan AN.49 (49f): the answers window that a dispute's 'Tell NM about these' opens reads the files under the message box.
  attachments: [],
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(read('brain-sources.js'), context, { filename: 'nm/app/brain-sources.js' });
const pane = context.window.NmBrainSources;
vm.runInContext(between('function appendReplyBody(', 'const REPLY_ICONS') + '\n'
  + between('function renderTurn(entry) {', 'function repaint()'), context, { filename: 'nm/app/app.js' });
context.window.NmBrainSources = { ...pane,
  showContent: (title, content, opener, back, kind) => opened.push({ title, kind, content: outlines(content) }),
  openPassage: () => {} };

const view = {
  state: 'checked',
  elements: [
    { element: 'Possession for the period the law requires', label: 'Possession for twelve years', proves: 'client', status: 'shown',
      why: 'The revenue entries show it year after year.',
      law: { found: true, kind: 'provision', title: 'Imagined Relief Act, 1907', locator: 's.4', words: 'possession for twelve years',
        source_id: 'P:abc' },
      points: [{ what: 'The entries name the client as in possession.', located: true,
        pages: [{ document: 'entries.pdf', page: 'page 2', source_id: 't1:d1p2' }] }] },
    { element: 'Notice before the suit', label: 'Notice before the suit', proves: 'client', status: 'weak',
      why: 'Only the client says it was sent.', law: { found: false, words: 'notice in writing' },
      points: [{ what: 'The client says the notice went by post.', located: false, pages: [] }] }],
  to_get: [{ what: 'The postal receipt', from_whom: 'the client', why: 'It proves the date of posting.',
    helps: 'It shows the notice was sent in time.', for: 'Notice before the suit' }],
  other_side: [{ relies_on: 'Their own later entry in the record', label: 'Their later entry', answer: 'It was made after the suit.',
    law: null, points: [] }],
};
const dispute = { id: 'D1', name: 'The boundary dispute', between: ['the client', 'the neighbour'], fact_ids: [], questions: [],
  rights_at_stake: [], relief_sought: [], still_needed: [], law: { state: 'assessed', why: '' },
  checklist: { name: 'The boundary dispute', answered_at: '2026-11-04T10:00:00+00:00', items: [], in_hand: 0, case: view,
    time_limits: [{ what: 'Last day to file the suit', last_day: '2029-03-10',
      rows: [['Last day', '10 March 2029'], ['Result', 'Open'], ['Days left', '856']] }] } };
const board = {
  state: 'ready', understanding: { confirmed: false, open_points: ['The chronology is not set out.'] }, disputes: [dispute],
  // Plan AN.48 (48g, D148; register item 3, re-pinned for it alone): a fact and an event the advocate corrected.
  facts: [{ id: 'F1', fact: 'The gate was locked.', certainty: 'reported', from: 'advocate', corrected: { value: 'The gate was open.' } }],
  instructions: ['Do not write to them.'],
  related_points: [], parties: [], subjects: [],
  timeline: { state: 'ready', events: [{ id: 'E1', date: '1 May 2020', dated: true, kind: 'other', what: 'The sum was agreed.',
    said_by: 'a caller', document: 'call.pdf', pages: [1], words: 'agreed', located: true, corrected: { value: '1 June 2020' } }],
  documents: [{ name: 'call.pdf', pages_read: 1, events: 1, state: 'read', why: '' }] },
  copies: [{ first: { document: 'a.pdf', page: 2 }, second: { document: 'b.pdf', page: 5 }, figures: [{ first: '6.06', second: '6.16', after: '' }] }],
  set_aside: [{ what: 'A sale read twice', document: 'a.pdf', why: 'The page does not record it.' }],
};
context.state.turns = [{ answer: { chat_id: 'c1', turn_id: 't1', elements: [{ kind: 'CASE', text: 'x', case: view,
  dispute: { id: 'D1', name: 'The boundary dispute' } }] } }];

const drawn = {};
drawn.board = outlines(context.renderChatBoard(board));
const card = context.renderChatBoard(board).find((node) => node.className === 'board-disputes').children[0];
const walk = (node) => [node, ...(node.children || []).flatMap(walk)];
const rows = walk(card).filter((node) => node.tagName === 'BUTTON');
for (const row of rows) row.handlers.click();
for (const line of context.renderChatBoard(board).filter((node) => node.className === 'board-line')) line.handlers.click();
drawn.pane = opened.map(({ title, kind, content }) => ({ title, kind, content }));

// The reading pane itself: a passage of law opened from a point, and the whole Act, as the pane draws them.
const nodes = ['brain-source-reader', 'brain-source-title', 'brain-source-close', 'brain-source-status', 'brain-source-body',
  'brain-source-back', 'brain-source-kind', 'pane-advise'];
const reads = [];
pane.configure({ scope: () => ({}), request: (url) => new Promise((resolve) => reads.push({ url, resolve })) });
const passage = pane.openPassage({ chat_id: 'c1', turn_id: 't1' }, 'P:abc', el('button'), { words: 'possession for twelve years',
  phrase: 'Possession for twelve years' });
reads.at(-1).resolve({ brain: true, id: 'P:abc', kind: 'provision', label: 'Imagined Relief Act, 1907', title: 'Imagined Relief Act, 1907',
  locator: 's.4', text: '4. Title by possession for twelve years, and not otherwise.', digest: 'd', whole: true });
await passage;
const body = () => byId.get('brain-source-body');
const shown = () => ({ kind: byId.get('brain-source-kind').textContent, title: byId.get('brain-source-title').textContent,
  body: outlines(body().children) });
drawn.passage = shown();
const whole = body().children.find((node) => node.className === 'source-expand').handlers.click();
reads.at(-1).resolve({ kind: 'provision', title: 'Imagined Relief Act, 1907', changed: false, found: true, parts: [
  { locator: 's.3', heading: 'Three', text: '3. Before.', here: false }, { locator: 's.4', heading: 'Four', text: '4. Title.', here: true }] });
await whole;
drawn.whole = shown();
assert.ok(nodes.every((id) => byId.has(id)), 'the pane uses its own elements');

if (process.argv.includes('--print')) {
  console.log(JSON.stringify(drawn, null, 1));
  process.exit(0);
}
const PINNED = JSON.parse(readFileSync(join(here, 'board_and_pane_frozen.json'), 'utf8'));
for (const part of Object.keys(PINNED)) {
  assert.deepEqual(JSON.parse(JSON.stringify(drawn[part])), PINNED[part],
    `The ${part} would change. The board and the reading pane are frozen (plan AN.39, D60): ask the owner first.`);
}
assert.deepEqual(Object.keys(drawn).sort(), Object.keys(PINNED).sort());
console.log('board_and_pane_frozen.mjs: the board and the reading pane are as pinned');
