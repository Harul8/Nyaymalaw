// What makes the case stronger (plan AN.35, D31-D32; piece 35c3d): beside each dispute's section of the answer (rendering v20),
// each element with its mark, who must prove it, why, the law's own words and where they stand (or that NM could not find them in
// the law it read) and the pages of its points; what to get, also under "What I need from you"; what the other side will rely on;
// and on the board, under each dispute and in its detail (checklist v3). Runs the actual renderTurn, renderDisputeCard and
// renderDisputeDetail from nm/app/app.js against a stub DOM, as papers_table.mjs does; not browser QA. The matter is invented.
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
for (const name of ['function renderCaseBlock(', 'function renderDisputeCard(', 'function renderDisputeDetail(']) {
  if (!rendererSource.includes(name)) throw new Error(`renderer boundary moved: ${name}`);
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
  state: { matterId: null, ended: false, advocate: null, turns: [] },
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
const view = {
  state: 'checked',
  elements: [
    { element: 'Possession for the period the law requires', proves: 'client', status: 'shown',
      why: 'The revenue entries show it year after year.',
      law: { found: true, kind: 'provision', title: 'Imagined Relief Act, 1907', locator: 'Section 4',
        words: 'possession for twelve years', source_id: 'P:abc' },
      points: [{ what: 'The entries name the client as in possession.', located: true,
        pages: [{ document: 'entries.pdf', page: 'page 2', source_id: 't1:d1p2' }] }] },
    { element: 'Notice before the suit', proves: 'client', status: 'missing', called: 'shown',
      why: 'Nothing yet shows a notice was sent.', law: { found: false, words: 'notice in writing' }, points: [] },
  ],
  to_get: [{ what: 'The postal receipt', from_whom: 'the client', why: 'It proves the date of posting.',
    helps: 'It shows the notice was sent in time.', for: 'Notice before the suit' }],
  other_side: [{ relies_on: 'Their own later entry in the record', answer: 'It was made after the suit was filed.', law: null,
    points: [] }],
};
const elements = [
  label('HEADING', 'The boundary dispute'),
  label('CASE', 'What makes the case stronger', { case: view, dispute: { id: 'D1', name: 'The boundary dispute' } }),
  label('NEEDS', 'What I need from you'),
  label('NEED_CASE', 'The postal receipt', { need: view.to_get[0], dispute: { id: 'D1', name: 'The boundary dispute' } }),
];
const turn = context.renderTurn({ brief: 'What do we need?', answer: {
  turn_id: 't1', chat_id: 'c1', elements, metrics: { gates_fired: [], outcome: 'ok', latency_ms: 1, llm_calls: 1,
    tokens: { in: 1, out: 1 }, cost_usd: 0, violations: [], tier_downgrades: [] } } });

const walk = (root) => { const all = []; (function go(node) { all.push(node); for (const kid of node.children) go(kid); })(root); return all; };
const has = (name) => (node) => String(node.className).split(/\s+/).includes(name);
const [beside] = walk(turn).filter(has('answer-case'));
assert.ok(beside, 'the case is drawn beside the section');
assert.equal(beside.tagName, 'DETAILS');
// Plan AN.49 (49a; D177, D185, D187a-b): the answer opens on the advice. The whole account is folded, drawn closed; what must not
// be missed stands outside the fold, in code's words.
assert.equal(beside.open, false, 'closed: the answer opens on the advice');
assert.ok(beside.children[0].textContent.startsWith('What makes the case stronger: the whole list ('), 'the fold says how long it is');
const [outside] = walk(turn).filter(has('case-summary'));
assert.ok(outside && !walk(beside).includes(outside), 'the summary stands outside the fold');
const said = outside.textContent;
for (const part of [`NM set out ${view.elements.length} things the law requires for this dispute:`, 'shown by the papers', 'shown only weakly',
  'not yet shown.', `${view.to_get.length} to get.`, 'NM could not find the quoted words in the law it read.',
  'This is NM’s working list:', 'It did not go through the independent review that the sections of an answer do.',
  'Show this dispute on the matter board']) {
  assert.ok(said.includes(part), part);
}
// 'Show this dispute on the matter board' opens the dispute's card where the board shows one at a time (49c), and leaves an
// open card as it is.
{
  const [show] = walk(outside).filter((node) => node.tagName === 'BUTTON' && node.textContent === 'Show this dispute on the matter board');
  for (const [expanded, clicks] of [['false', 1], ['true', 0]]) {
    const toggle = Object.assign(el('button'), { clicks: 0, click() { this.clicks += 1; }, getAttribute: () => expanded });
    const title = Object.assign(el('button'), { focused: false, focus() { this.focused = true; } });
    const card = { getAttribute: (name) => (name === 'aria-label' ? 'The boundary dispute' : null), scrollIntoView() {},
      querySelector: (selector) => ({ '.dispute-toggle': toggle, '.dtitle': title })[selector] || null };
    document.querySelectorAll = () => [card];
    show.handlers.click();
    assert.equal(toggle.clicks, clicks, `a card ${expanded === 'false' ? 'closed is opened' : 'open is left as it is'}`);
    assert.equal(title.focused, true);
  }
  document.querySelectorAll = () => [];
}
const counted = (status) => view.elements.filter((item) => item.status === status).length;
assert.ok(said.includes(`${counted('shown')} shown by the papers, ${counted('weak')} shown only weakly, `
  + `${view.elements.length - counted('shown') - counted('weak')} not yet shown.`), 'the counts are the saved case’s own');
// A second look that could not be made is said outside the fold, never only inside it; a case with no requirement stays open.
const turnOf = (given) => context.renderTurn({ brief: 'What do we need?', answer: { turn_id: 't2', chat_id: 'c1',
  elements: [label('HEADING', 'The boundary dispute'), label('CASE', 'What makes the case stronger',
    { case: given, dispute: { id: 'D1', name: 'The boundary dispute' } })],
  metrics: { gates_fired: [], outcome: 'ok', latency_ms: 1, llm_calls: 1, tokens: { in: 1, out: 1 }, cost_usd: 0, violations: [],
    tier_downgrades: [] } } });
const [unsure] = walk(turnOf({ ...view, state: 'unchecked' })).filter(has('case-summary'));
assert.ok(unsure.textContent.includes('NM’s second look at this list could not be made'), 'said outside the fold');
assert.ok(!unsure.textContent.includes('a second look checked it'), 'no second look is claimed where none was made');
const unset = walk(turnOf({ state: 'unavailable', elements: [], to_get: [], other_side: [] }));
assert.equal(unset.filter(has('case-summary')).length, 0);
assert.equal(unset.filter(has('answer-case'))[0].open, true, 'one sentence is not folded');
const text = beside.textContent;
for (const part of ['What makes the case stronger', 'What the law requires',
  'Possession for the period the law requires', 'Shown by the papers · For your client to prove',
  'The revenue entries show it year after year.', 'possession for twelve years', 'Section 4, Imagined Relief Act, 1907',
  'The entries name the client as in possession. · entries.pdf, page 2',
  'Notice before the suit', 'Not yet shown · For your client to prove', 'Called shown, but none of its points was found on its page.',
  'NM could not find these words in the law it read: “notice in writing”',
  'What to get', 'The postal receipt — from the client', 'For: Notice before the suit', 'It proves the date of posting.',
  'What the other side will rely on', 'Their own later entry in the record', 'What answers it: It was made after the suit was filed.']) {
  assert.ok(text.includes(part), part);
}
const marks = walk(beside).filter(has('st')).map((node) => node.className);
assert.deepEqual(marks, ['st st--in_hand', 'st st--not_given'], 'each element carries its mark');
const [needs] = walk(turn).filter(has('need'));
assert.ok(needs && needs.textContent.includes('The postal receipt — from the client. It proves the date of posting.'),
  'what to get stands under What I need from you');

// A case NM could not set out says so, and claims nothing.
const failed = context.renderCaseBlock({ state: 'unavailable', elements: [], to_get: [], other_side: [] });
assert.deepEqual(Array.from(failed, (node) => node.textContent), [
  'NM could not set out what would make this case stronger this time. The rest stands as checked.']);
const unchecked = context.renderCaseBlock({ ...view, state: 'unchecked' });
assert.ok(unchecked[0].textContent.startsWith('NM’s second look at this list could not be made'));

// The board: under the dispute, each element with its mark and how many the papers show; the detail holds the whole case.
const dispute = { id: 'D1', name: 'The boundary dispute', between: ['the client', 'the neighbour'], fact_ids: [], questions: [],
  rights_at_stake: [], relief_sought: [], still_needed: [], law: { state: 'assessed', why: '' },
  checklist: { name: 'The boundary dispute', answered_at: '2026-11-02T10:00:00+00:00', time_limits: [], items: [], in_hand: 0,
    case: view } };
const board = { facts: [], related_points: [] };
const card = context.renderDisputeCard(dispute, board, 1);
const cardText = card.textContent;
for (const part of ['1 · The boundary dispute', '1 of 2 shown by the papers', 'What the law requires',
  'Possession for the period the law requires', 'Notice before the suit', '1 to get', 'The other side will rely on (1)']) {
  assert.ok(cardText.includes(part), part);
}
// Plan AN.49 (49c; D180): on the board the other side is one line with its count; what they rely on is in the pane.
assert.ok(!cardText.includes('Their own later entry in the record'), 'the other side is one line on the board');
assert.ok(!cardText.includes('NM found nothing this dispute needs'), 'a case is never read as an empty checklist');
const detail = context.renderDisputeDetail(dispute, board);
const detailText = detail.map((node) => node.textContent).join('\n');
// Plan AN.49 (49b; D179): the whole-dispute view is a summary with folds. The case is its lines under one closed fold, each
// opening alone; the whole account is not drawn again, and how it was checked is said outside the fold.
const caseFold = detail.find((node) => node.tagName === 'DETAILS' && node.children[0].textContent.startsWith('The case ('));
assert.ok(caseFold && caseFold.open === false, 'the case is one closed fold');
assert.ok(caseFold.children[0].textContent.includes(`of ${view.elements.length} shown by the papers`));
assert.ok(caseFold.textContent.includes('Possession for the period the law requires') && caseFold.textContent.includes('Notice before the suit'));
assert.ok(!detailText.includes('The revenue entries show it year after year.'), 'the whole account is not repeated in this view');
assert.ok(detail.some((node) => node.tagName !== 'DETAILS' && node.textContent.startsWith('This is NM’s working list:')),
  'how the case was checked stands outside the fold');
const none = context.renderDisputeCard({ ...dispute, checklist: { ...dispute.checklist, case: null } }, board, 1);
assert.ok(none.textContent.includes('NM could not set out what would make this case stronger when it last answered.'));

// THE BOARD IN SHORT PHRASES, EACH POINT ALONE IN THE READING PANE (plan AN.39, D52, D55-D57; owner, 4 Nov 2026): on the board each
// element and each thing the other side relies on is one line - its short name, or a saved case's own words - and opens alone in the
// pane: how it stands and who proves it, why it is needed with its law, where it stands with its pages, what to get for it, and the
// buttons where the papers do not show it. Its law and its pages open from the saved record of the answer that holds the case.
{
  const opened = [];
  const passages = [];
  context.window.NmBrainSources = { ...context.window.NmBrainSources,
    showContent: (title, content, opener, back, kind) => opened.push({ title, content: Array.from(content), opener, kind }),
    openPassage: (where, tag, opener, given) => passages.push({ where, tag, given }) };
  const message = Object.assign(el('textarea'), { value: '', dispatchEvent() {} });
  byId.set('message', message);
  context.sizeComposer = () => {};
  context.Event = class { constructor(type) { this.type = type; } };
  const named = structuredClone(view);
  named.elements[0].label = 'Possession for twelve years';
  named.other_side[0].label = 'Their later entry';
  const labelled = { ...dispute, checklist: { ...dispute.checklist, case: named } };
  const caseElement = label('CASE', 'What makes the case stronger', { case: named, dispute: { id: 'D1', name: 'The boundary dispute' } });
  context.state.turns = [{ answer: { chat_id: 'c1', turn_id: 't1', elements: [caseElement] } }];
  const card = context.renderDisputeCard(labelled, board, 1);
  const rows = walk(card).filter((node) => node.tagName === 'BUTTON' && has('item')(node));
  assert.deepEqual(Array.from(rows, (row) => row.children[1].children[0].textContent),
    ['Possession for twelve years', 'Notice before the suit'], 'short names; a saved case\'s own words where none');
  assert.ok(!card.textContent.includes('The revenue entries show it'), 'the detail is in the pane, not on the board');
  const said = (pane) => pane.content.map((node) => node.textContent).join('\n');
  const within = (pane, test) => pane.content.flatMap(walk).filter(test);

  // A point the papers show: only that point, and no buttons.
  rows[0].handlers.click();
  let pane = opened.at(-1);
  assert.equal(pane.title, 'Possession for twelve years');
  assert.equal(pane.kind, 'What the law requires · Dispute 1');
  for (const part of ['Shown by the papers · For your client to prove', 'Possession for the period the law requires', 'Why it is needed',
    'The revenue entries show it year after year.', 'Section 4, Imagined Relief Act, 1907', 'Where it stands',
    'The entries name the client as in possession. · entries.pdf, page 2']) {
    assert.ok(said(pane).includes(part), part);
  }
  assert.ok(!said(pane).includes('Notice before the suit') && !said(pane).includes('Tell NM'), 'only this point; no buttons');
  const cites = within(pane, (node) => node.tagName === 'BUTTON' && has('cite')(node));
  cites[0].handlers.click();
  assert.deepEqual(JSON.parse(JSON.stringify(passages.at(-1))), { where: { chat_id: 'c1', turn_id: 't1' }, tag: 'P:abc',
    given: { words: 'possession for twelve years', phrase: 'Possession for twelve years', title: 'Imagined Relief Act, 1907' } });
  cites[1].handlers.click();
  assert.equal(passages.at(-1).tag, 't1:d1p2', 'the page opens from the answer\'s record');

  // A point not yet shown: where it stands, what to get for it, and the two buttons, each putting a start in the message box.
  rows[1].handlers.click();
  pane = opened.at(-1);
  for (const part of ['Not yet shown · For your client to prove', 'NM could not find these words in the law it read: “notice in writing”',
    'Called shown, but none of its points was found on its page.', 'Not in your messages or documents yet.', 'What to get',
    'The postal receipt — from the client', 'It proves the date of posting.', 'It shows the notice was sent in time.']) {
    assert.ok(said(pane).includes(part), part);
  }
  const acts = within(pane, (node) => has('act')(node));
  assert.deepEqual(Array.from(acts, (node) => node.textContent), ['Tell NM about this', 'Not available']);
  acts[0].handlers.click();
  assert.equal(message.value, 'About "Notice before the suit" (The boundary dispute): ');
  acts[1].handlers.click();
  assert.equal(message.value, 'About "Notice before the suit" (The boundary dispute):\n'
    + 'About "Notice before the suit" (The boundary dispute): this is not available.');

  // What the other side will rely on: one line on the board that opens its list (49c), where each thing opens alone, with what answers it.
  const [theirLine] = walk(card).filter((node) => node.tagName === 'BUTTON' && has('board-line')(node));
  assert.equal(theirLine.textContent, 'The other side will rely on (1)');
  theirLine.handlers.click();
  pane = opened.at(-1);
  assert.equal(pane.title, 'The other side will rely on');
  assert.equal(pane.kind, 'Dispute 1');
  const [theirs] = within(pane, (node) => node.tagName === 'BUTTON' && has('item')(node));
  assert.equal(theirs.children[1].children[0].textContent, 'Their later entry');
  theirs.handlers.click();
  pane = opened.at(-1);
  assert.equal(pane.kind, 'The other side will rely on · Dispute 1');
  assert.ok(said(pane).includes('Their own later entry in the record') && said(pane).includes('What answers it')
    && said(pane).includes('It was made after the suit was filed.'));
  assert.deepEqual(Array.from(within(pane, (node) => has('act')(node)), (node) => node.textContent), ['Tell NM what answers it']);

  // Without an answer on the page that holds the case, the law shows its words alone, as before.
  context.state.turns = [];
  context.renderDisputeCard(labelled, board, 1);
  const bare = walk(context.renderDisputeCard(labelled, board, 1)).filter((node) => node.tagName === 'BUTTON' && has('item')(node));
  bare[0].handlers.click();
  const before = passages.length;
  within(opened.at(-1), (node) => node.tagName === 'BUTTON' && has('cite')(node))[0].handlers.click();
  assert.equal(passages.length, before, 'no saved passage is asked for without the answer that holds it');

  // What I need from you: what to get opens the point it is for (D55).
  const asked = context.renderTurn({ brief: 'What do we need?', answer: { turn_id: 't1', chat_id: 'c1', elements: [
    label('HEADING', 'The boundary dispute'), caseElement, label('NEEDS', 'What I need from you'),
    label('NEED_CASE', 'The postal receipt', { need: named.to_get[0], dispute: { id: 'D1', name: 'The boundary dispute' } })],
    metrics: { gates_fired: [], outcome: 'ok', latency_ms: 1, llm_calls: 1, tokens: { in: 1, out: 1 }, cost_usd: 0, violations: [],
      tier_downgrades: [] } } });
  const need = walk(asked).find((node) => has('need-item')(node));
  assert.equal(need.textContent, 'The postal receipt');
  need.handlers.click();
  assert.equal(opened.at(-1).title, 'Notice before the suit');
  assert.equal(opened.at(-1).kind, 'What the law requires · The boundary dispute');

  // The legend says what a case's marks mean, above the disputes.
  const [legend] = context.renderChatBoard({ state: 'ready', disputes: [labelled], facts: [], instructions: [], related_points: [],
    parties: [], subjects: [] });
  assert.equal(legend.className, 'legend');
  assert.deepEqual(Array.from(legend.children, (entry) => entry.textContent), ['Shown by the papers', 'Shown only weakly', 'Not yet shown']);
}

// ONE DISPUTE OPEN AT A TIME (plan AN.49, 49c; D180): on a board of several disputes the first is open and the others show their name
// and counts with a button; opening one closes the other; a board of one dispute has no such button.
{
  const second = { ...dispute, id: 'D2', name: 'The rent dispute' };
  context.state.boardOpen = undefined;
  const draw = () => context.renderChatBoard({ state: 'ready', disputes: [dispute, second], facts: [], instructions: [],
    related_points: [], parties: [], subjects: [] });
  const cardsOf = (nodes) => nodes.flatMap(walk).filter(has('dispute'));
  const toggleOf = (card) => walk(card).find(has('dispute-toggle'));
  const bodyOf = (card) => walk(card).find(has('dispute-body'));
  let [first, other] = cardsOf(draw());
  assert.equal(bodyOf(first).hidden, false, 'the first, the most urgent, is open');
  assert.equal(bodyOf(other).hidden, true);
  assert.equal(toggleOf(first).textContent, 'Hide its points');
  assert.equal(toggleOf(other).textContent, `Show its points (${view.elements.length})`);
  assert.ok(other.textContent.includes('2 · The rent dispute') && other.textContent.includes('shown by the papers'),
    'a closed card keeps its name and counts');
  toggleOf(other).handlers.click();
  assert.equal(bodyOf(other).hidden, false);
  assert.equal(bodyOf(first).hidden, true, 'opening one closes the other');
  // Which one is open is kept for the visit: the board drawn again shows the same one.
  [first, other] = cardsOf(draw());
  assert.equal(bodyOf(other).hidden, false);
  assert.equal(bodyOf(first).hidden, true);
  toggleOf(other).handlers.click();
  assert.equal(bodyOf(other).hidden, true, 'the open one can be closed');
  [first, other] = cardsOf(draw());
  assert.ok(bodyOf(first).hidden && bodyOf(other).hidden, 'and stays closed');
  const [alone] = cardsOf(context.renderChatBoard({ state: 'ready', disputes: [dispute], facts: [], instructions: [],
    related_points: [], parties: [], subjects: [] }));
  assert.equal(toggleOf(alone), undefined, 'a board of one dispute has no fold');
}
// THE CASE GATHERED (plan AN.49, 49e; D182, D185): a case of the gathered version shows under its dispute code's line on how it was
// checked, what most decides it, and each heading as one line with how many of its requirements the papers show. A heading opens its
// requirements in the pane, each opening alone as before; a thing that decides it opens what it concerns; a thing to get is listed
// under every requirement it serves. A case saved earlier is drawn as before (above).
{
  const opened = [];
  context.window.NmBrainSources = { ...context.window.NmBrainSources,
    showContent: (title, content, opener, back, kind) => opened.push({ title, content: Array.from(content), opener, kind }) };
  context.state.turns = [];
  const gathered = {
    state: 'unchecked',
    headings: ['Possession', 'Notice'],
    elements: [
      { ...view.elements[0], label: 'Possession for twelve years', heading: 1 },
      { element: 'Possession that was open', label: 'Open possession', proves: 'client', status: 'weak', why: 'One entry only.',
        law: null, points: [], heading: 1 },
      { ...view.elements[1], heading: 2 },
    ],
    to_get: [{ what: 'The client’s statement', from_whom: 'the client', why: 'It speaks to both.', helps: 'It fills the gaps.',
      for: 'Possession that was open', serves: ['Possession that was open', 'Notice before the suit'] }],
    other_side: [{ ...view.other_side[0], label: 'Their later entry', attacks: 1 }],
    decides: [{ what: 'Whether the possession was open', why: 'Everything turns on it.', elements: [2], other_side: [1] }],
  };
  const gatheredDispute = { ...dispute, checklist: { ...dispute.checklist, case: gathered } };
  const card = context.renderDisputeCard(gatheredDispute, board, 1);
  const lines = walk(card).filter((node) => node.tagName === 'BUTTON' && has('item')(node));
  assert.deepEqual(lines.map((row) => row.children[1].children.map((part) => part.textContent)), [
    ['Whether the possession was open'], ['Possession', '1 of 2 shown'], ['Notice', '0 of 1 shown']], 'three lines for the case');
  assert.deepEqual(lines.map((row) => row.className),
    ['item item--coming_or_unclear', 'item item--coming_or_unclear', 'item item--not_given'], 'each marked as its least-shown requirement');
  const cardText = card.textContent;
  const at = (part) => { const index = cardText.indexOf(part); assert.ok(index >= 0, part); return index; };
  assert.ok(at('NM’s second look at this list could not be made') < at('This is NM’s working list: code looked for each quotation')
    && at('This is NM’s working list:') < at('Most needs attention now') && at('Most needs attention now') < at('What the law requires'),
    'how it was checked stands above its lines');
  for (const part of ['1 of 3 shown by the papers', '1 to get', 'The other side will rely on (1)']) at(part);
  assert.ok(!cardText.includes('a second look checked it'), 'no second look is claimed where none was made');
  assert.ok(!cardText.includes('Possession for twelve years'), 'the requirements are under their headings');

  lines[1].handlers.click();
  let pane = opened.at(-1);
  assert.equal(pane.title, 'Possession');
  assert.equal(pane.kind, 'What the law requires · Dispute 1');
  const under = pane.content.flatMap(walk).filter((node) => node.tagName === 'BUTTON' && has('item')(node));
  assert.deepEqual(under.map((row) => row.children[1].children[0].textContent), ['Possession for twelve years', 'Open possession']);
  under[1].handlers.click();
  pane = opened.at(-1);
  assert.equal(pane.title, 'Open possession');
  assert.ok(pane.content.map((node) => node.textContent).join('\n').includes('The client’s statement — from the client'));
  lines[2].handlers.click();
  opened.at(-1).content.flatMap(walk).filter((node) => node.tagName === 'BUTTON' && has('item')(node))[0].handlers.click();
  assert.equal(opened.at(-1).title, 'Notice before the suit');
  assert.ok(opened.at(-1).content.map((node) => node.textContent).join('\n').includes('The client’s statement — from the client'),
    'a thing to get is listed under every requirement it serves');

  lines[0].handlers.click();
  pane = opened.at(-1);
  assert.equal(pane.title, 'Whether the possession was open');
  assert.equal(pane.kind, 'Most needs attention now · Dispute 1');
  const decided = pane.content.map((node) => node.textContent).join('\n');
  for (const part of ['Everything turns on it.', 'What the law requires', 'Open possession', 'What the other side will rely on',
    'Their later entry']) {
    assert.ok(decided.includes(part), part);
  }
  assert.ok(!decided.includes('Possession for twelve years'), 'only what it concerns');

  const whole = context.renderCaseBlock(gathered).map((node) => node.textContent).join('\n');
  assert.ok(whole.includes('For: Possession that was open; Notice before the suit'), 'the answer names every requirement it serves');
  const detail = context.renderDisputeDetail(gatheredDispute, board);
  const caseFold = detail.find((node) => node.tagName === 'DETAILS' && node.children[0].textContent.startsWith('The case ('));
  assert.ok(caseFold.textContent.includes('Most needs attention now') && caseFold.textContent.includes('1 of 2 shown'),
    'the whole-dispute view draws the same gathered lines');
}
// SEVERAL THINGS IN ONE REPLY (plan AN.49, 49f; D183): 'Tell NM about these' on a dispute opens the answers window of AN.37 with a row
// for each thing to get of a gathered case or, for a case saved earlier, each requirement not yet shown; what is written goes as one
// message, each part in the words the single 'Tell NM about this' uses; what was written and not sent is kept while the page is open.
{
  const sent = [];
  Object.assign(context, { attachments: [], usageUsedUp: () => false, attachmentsBlockSend: () => '', heldSend: null,
    activeDelivery: null, send: (message) => sent.push(message), repaint() {} });
  const dialogs = [];
  const create = document.createElement;
  document.createElement = (tag) => {
    const node = create(tag);
    if (tag === 'dialog') Object.assign(node, { showModal() { dialogs.push(node); }, close() { node.closed = true; } });
    return node;
  };
  context.state.turns = [];
  const tellOf = (card) => walk(card).find((node) => node.tagName === 'BUTTON' && node.textContent === 'Tell NM about these');
  const rowsOf = (shown) => walk(shown).filter(has('need-answer-question')).map((node) => node.textContent);
  const boxesOf = (shown) => walk(shown).filter((node) => node.tagName === 'TEXTAREA');
  const press = (shown, words) => walk(shown).find((node) => node.tagName === 'BUTTON' && node.textContent === words).handlers.click();
  const write = (box, words) => { box.value = words; box.handlers.input(); };

  // A case saved earlier: a row for each requirement not yet shown.
  tellOf(context.renderDisputeCard(dispute, board, 1)).handlers.click();
  let dialog = dialogs.at(-1);
  assert.equal(walk(dialog).find((node) => node.tagName === 'H2').textContent, 'Tell NM about these');
  assert.deepEqual(rowsOf(dialog), ['Notice before the suit · Not yet shown']);
  press(dialog, 'Send answers');
  assert.equal(sent.length, 0, 'nothing written, nothing sent');
  assert.ok(dialog.textContent.includes('Write about at least one of them.'));
  write(boxesOf(dialog)[0], ' It was posted on 3 March. ');
  press(dialog, 'Send answers');
  assert.deepEqual(sent, ['About "Notice before the suit" (The boundary dispute): It was posted on 3 March.'],
    'in the words the single button puts in the message box');

  // A gathered case: a row for each thing to get, with every requirement it serves; one message for what was written.
  const asked = { state: 'checked', headings: ['Notice'], elements: [{ ...view.elements[1], heading: 1 }], other_side: [], decides: [],
    to_get: [{ what: 'The postal receipt', from_whom: 'the client', why: 'It proves the posting.', helps: '',
      for: 'Notice before the suit', serves: ['Notice before the suit'] },
    { what: 'The acknowledgment card', from_whom: 'the post office', why: 'It proves receipt.', helps: '',
      for: 'Notice before the suit', serves: ['Notice before the suit'] }] };
  const askedDispute = { ...dispute, checklist: { ...dispute.checklist, case: asked } };
  tellOf(context.renderDisputeCard(askedDispute, board, 1)).handlers.click();
  dialog = dialogs.at(-1);
  assert.deepEqual(rowsOf(dialog), ['The postal receipt — from the client (for: Notice before the suit)',
    'The acknowledgment card — from the post office (for: Notice before the suit)']);
  write(boxesOf(dialog)[1], 'We will have it next week.');
  press(dialog, 'Cancel');
  tellOf(context.renderDisputeCard(askedDispute, board, 1)).handlers.click();
  dialog = dialogs.at(-1);
  assert.deepEqual(boxesOf(dialog).map((box) => box.value), ['', 'We will have it next week.'], 'what was written is kept');
  write(boxesOf(dialog)[0], 'The client has it.');
  press(dialog, 'Send answers');
  assert.equal(sent.at(-1), 'About "The postal receipt" (The boundary dispute): The client has it.\n\n'
    + 'About "The acknowledgment card" (The boundary dispute): We will have it next week.');

  // Nothing to tell: no button where the papers show every requirement, or a gathered case has nothing to get.
  const allShown = { ...view, elements: [view.elements[0]], to_get: [] };
  assert.equal(tellOf(context.renderDisputeCard({ ...dispute, checklist: { ...dispute.checklist, case: allShown } }, board, 1)), undefined);
  assert.equal(tellOf(context.renderDisputeCard({ ...askedDispute, checklist: { ...askedDispute.checklist,
    case: { ...asked, to_get: [] } } }, board, 1)), undefined);
  document.createElement = create;
}
console.log('case_strength.mjs: ok');
