// What each dispute needs, on the matter board, as the readability design shows it (owner
// decisions, 17 Oct 2026; built to the design on 18 Oct): the marks' legend once, each
// dispute a numbered section with its last days and how much is in hand, each item under
// Needed and Would strengthen with its mark, an item's details in the reading pane, and the
// facts, instructions and related points folded below. Offline substitutes for the DOM;
// not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
function between(from, to) {
  const a = app.indexOf(from);
  const b = app.indexOf(to, a + from.length);
  assert.ok(a >= 0 && b > a, `slice ${from} .. ${to}`);
  return app.slice(a, b);
}

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  dispatchEvent(event) { this.dispatched = event.type; }
  focus() { this.focused = true; }
  click() { return this.listeners.click?.(); }
}
const find = (node, test, found = []) => {
  if (test(node)) found.push(node);
  for (const child of node.children || []) find(child, test, found);
  return found;
};

const shown = [];
const message = new Element('textarea');
message.value = '';
let sized = 0;
const context = vm.createContext({
  document: { createElement: (tag) => new Element(tag) },
  window: { NmBrainSources: {
    showContent: (title, content, opener, back, kind) => shown.push({ title, content, opener, kind }),
    open: (...args) => shown.push({ opened: args }) } },
  $: (id) => (id === 'message' ? message : new Element('div')),
  Event: class { constructor(type) { this.type = type; } },
  sizeComposer: () => { sized += 1; },
  stateBlock: (_kind, text) => Object.assign(new Element('p'), { textContent: text }),
  renderDisputeDetail: () => [],
  state: { turns: [] },
  CERTAINTY: { reported: 'Reported' }, QUESTION_STATUS: { researched: 'researched' },
  factPlace: () => 'From your messages',
});
vm.runInContext(between('function renderChatBoard(board) {', '// A DISPUTE IN DETAIL'), context);
vm.runInContext(between('function timeLimitStanding(rows) {', '// What is left of a time limit'), context);
vm.runInContext(between('function fileDate(iso) {', 'function fileAttention('), context);

const at = '2026-10-18T05:00:00+00:00';
const law = { kind: 'provision', title: 'The Limitation Act, 1963', locator: 'Article 54',
  words: 'Three years from the date fixed for the performance', source_id: 'provision:54', held_in: 't1' };
const item = (id, need, group, status, extra = {}) => ({ id, need, group, status, law, evidence: null,
  asked_at: null, ...extra });
const board = {
  state: 'ready', related_points: [{ point: 'Any other route', why: 'It may be quicker.', dispute_id: null }],
  instructions: ['Do not contact the buyer.'],
  facts: [{ id: 'f1', fact: 'The plot was sold twice', certainty: 'reported', from: 'advocate' }],
  disputes: [
    { id: 'D1', name: 'Possession of the plot', between: ['Client', 'Later buyer'], questions: [],
      checklist: { name: 'Possession of the plot', answered_at: at, in_hand: 1, time_limits: [
        { what: 'Last day to file the suit', last_day: '2027-01-10', rows: [['Last day', '10 January 2027 (Sunday)'],
          ['As of', '18 October 2026 (Sunday)'], ['Result', 'Open'], ['Days left', '84']] },
        { what: 'Last day to answer the notice', rows: [['Not assessed', 'the notice date is not given']] }],
      items: [
        item('K1', 'The sale agreement', 'needed', 'in_hand',
          { evidence: { from: 'document', document: 'agreement.pdf', page: 'page 1', words: 'agreed to sell',
                        given_at: at } }),
        item('K2', 'Proof the cancellation letter was received', 'needed', 'coming_or_unclear',
          { why: 'A cancellation must be answered in the suit.', note: 'not sure it arrived',
            evidence: { from: 'message', words: 'I am not sure he received it', given_at: at } }),
        item('K3', 'The date possession was refused', 'needed', 'not_given', { asked_at: at }),
        item('K4', 'The original receipt', 'would_strengthen', 'not_available',
          { evidence: { from: 'message', words: 'the receipt is lost', given_at: at } })] } },
    { id: 'D2', name: 'Cheating', between: [], questions: [],
      checklist: { name: 'Cheating', answered_at: at, in_hand: 0, time_limits: [], items: [] } },
    { id: 'D3', name: 'An earlier dispute', between: [], questions: [{ status: 'researched' }] }],
};

// Disputes first: the marks' legend once, the disputes, then one fold below.
const [legend, disputes, fold] = context.renderChatBoard(board);
assert.equal(legend.className, 'legend');
assert.equal(legend.attributes['aria-hidden'], 'true', "each item's own words are read out with it");
assert.deepEqual(legend.children.map((entry) => entry.children.map((part) => [part.className || '', part.textContent])), [
  [['st st--in_hand', ''], ['', 'In hand']], [['st st--coming_or_unclear', ''], ['', 'Coming or unclear']],
  [['st st--not_given', ''], ['', 'Not yet given']], [['st st--not_available', ''], ['', 'Not available']]]);
assert.equal(disputes.attributes['aria-label'], 'Disputes (3)');
const [first, second, third] = disputes.children;

// The dispute, numbered; under its name each last day code worked out ('By', the design's
// 'File by' being said only of a filing), a quiet word where it could not, and how much is
// in hand; then its items by group, each with its mark, its need and a note under it.
assert.equal(first.className, 'dispute');
assert.equal(first.attributes['aria-label'], 'Possession of the plot');
const [title] = find(first, (node) => node.className === 'dtitle');
assert.equal(title.textContent, '1 · Possession of the plot');
const [meta] = find(first, (node) => node.className === 'dmeta');
assert.deepEqual(meta.children.map((part) => [part.className, part.textContent]), [
  ['chip deadline open', 'By 10 Jan 2027 · 84 days left'], ['chip quiet', 'Last day not worked out'], ['count', '1 of 4 in hand']]);
assert.equal(meta.children[0].title, 'Last day to file the suit: Open · 84 days left · as of 18 October 2026 (Sunday)');
assert.deepEqual(find(first, (node) => node.className === 'group').map((node) => node.textContent),
  ['Needed', 'Would strengthen']);
const rows = find(first, (node) => /^item /.test(node.className || ''));
assert.deepEqual(rows.map((row) => [row.className, row.children[0].className,
  row.children[1].children.map((part) => [part.className, part.textContent])]), [
  ['item item--in_hand', 'st st--in_hand', [['t', 'The sale agreement'], ['sr', ' · In hand']]],
  ['item item--coming_or_unclear', 'st st--coming_or_unclear',
    [['t', 'Proof the cancellation letter was received'], ['sub', 'not sure it arrived'], ['sr', ' · Coming or unclear']]],
  ['item item--not_given', 'st st--not_given',
    [['t', 'The date possession was refused'], ['sub', 'Asked on 18 Oct'], ['sr', ' · Not yet given · asked 18 Oct 2026']]],
  ['item item--not_available', 'st st--not_available', [['t', 'The original receipt'], ['sr', ' · Not available']]]]);
assert.equal(rows[0].children[0].attributes['aria-hidden'], 'true', 'the mark is drawn; the words say it');

// An item opens in the reading pane: where it stands, why it is needed with its law (which
// opens in the pane), what the advocate said, and what they can do.
rows[1].click();
const opened = shown.pop();
assert.equal(opened.title, 'Proof the cancellation letter was received');
assert.equal(opened.kind, 'Needed · Dispute 1');
assert.equal(opened.opener, rows[1]);
assert.deepEqual(Array.from(opened.content, (node) => node.textContent), [
  'Coming or unclear',
  'Why it is neededA cancellation must be answered in the suit.Article 54, The Limitation Act, 1963',
  'Where it standsnot sure it arrivedI am not sure he received itFrom your message of 18 Oct 2026, in your words',
  'Tell NM about thisNot available']);
const [tell, unavailable] = opened.content.at(-1).children;
assert.deepEqual([tell.className, unavailable.className], ['act primary', 'act ghost']);
tell.click();
assert.equal(message.value, 'About "Proof the cancellation letter was received" (Possession of the plot): ');
assert.ok(message.focused && sized === 1 && message.dispatched === 'input');
message.value = '';
unavailable.click();
assert.equal(message.value,
  'About "Proof the cancellation letter was received" (Possession of the plot): this is not available.');
// The law link opens the saved passage where the answer that held it used it; otherwise
// the words the checklist kept.
const lawLink = opened.content[1].children.at(-1).children[0];
assert.equal(lawLink.className, 'cite');
lawLink.click();
const lawView = shown.pop();
assert.deepEqual([lawView.title, lawView.kind], ['The Limitation Act, 1963', 'Held law']);
assert.deepEqual(Array.from(lawView.content, (node) => node.textContent),
  ['Article 54', 'Legislative text', 'Three years from the date fixed for the performance']);
context.state.turns = [{ answer: { turn_id: 't1', elements: [
  { kind: 'LAW', sources: [{ id: 'other', brain: true }, { id: 'provision:54', brain: true }] }] } }];
lawLink.click();
assert.deepEqual(Array.from(shown.pop().opened).slice(2, 4), [0, 1]);

// In hand: what shows it, and nothing to do. Not given: when NM asked. Not available: what
// the advocate said, and only "Tell NM about this".
rows[0].click();
const held = Array.from(shown.pop().content, (node) => node.textContent);
assert.deepEqual(held, ['In hand', 'Why it is neededThree years from the date fixed for the performance'
  + 'Article 54, The Limitation Act, 1963', 'What shows itagreed to sellFrom agreement.pdf, page 1']);
rows[2].click();
assert.equal(shown.pop().content[2].textContent,
  'Where it standsNot in your messages or documents yet. NM asked for it on 18 Oct 2026.');
rows[3].click();
const gone = shown.pop().content;
assert.equal(gone[2].children[0].textContent, 'What you said');
assert.deepEqual(gone.at(-1).children.map((button) => button.textContent), ['Tell NM about this']);

// An answered dispute with no law-backed item says so; an earlier board is as it was.
assert.match(second.textContent, /NM found nothing this dispute needs in the law it holds/);
assert.match(third.textContent, /1 legal question · 1 researched/);
assert.equal(find(third, (node) => node.className === 'dtitle')[0].textContent, '3 · An earlier dispute');

// The facts, standing instructions and related points fold below, with what the board is.
assert.equal(fold.tag, 'details');
assert.equal(fold.children[0].textContent, 'Facts as you gave them (1) · Standing instructions (1) · Related points (1)');
assert.match(fold.textContent, /As NM understood this matter/);
assert.match(fold.textContent, /Do not contact the buyer\./);
assert.match(fold.textContent, /Any other route — It may be quicker\./);

// A passed last day says so beside its date; a single dispute is not numbered.
{
  const passed = structuredClone(board.disputes[0]);
  passed.checklist.time_limits = [{ what: 'Last day to reply', last_day: '2026-10-01', rows: [
    ['Last day', '1 October 2026 (Thursday)'], ['As of', '18 October 2026 (Sunday)'], ['Result', 'Passed'],
    ['Days since the last day', '17']] }];
  const card = context.renderDisputeCard(passed, board, null);
  const passedChip = find(card, (node) => node.className === 'dmeta')[0].children[0];
  assert.deepEqual([passedChip.className, passedChip.textContent], ['chip deadline expired', 'By 1 Oct 2026 · Passed']);
  assert.equal(find(card, (node) => node.className === 'dtitle')[0].textContent, 'Possession of the plot');
}
// How near an open last day is, in words and colour (the signed-off design, plan AN.14): a month
// or less, a week or less, one day; the days are the count code saved.
{
  const near = (left) => context.deadlineChips([{ what: 'Last day to reply', last_day: '2026-10-28', rows: [
    ['Last day', '28 October 2026 (Wednesday)'], ['As of', '18 October 2026 (Sunday)'], ['Result', 'Open'],
    ['Days left', String(left)]] }])[0];
  assert.deepEqual([near(31).className, near(31).textContent], ['chip deadline open', 'By 28 Oct 2026 · 31 days left']);
  assert.deepEqual([near(30).className, near(30).textContent], ['chip deadline soon', 'By 28 Oct 2026 · 30 days left']);
  assert.deepEqual([near(7).className, near(8).className], ['chip deadline urgent', 'chip deadline soon']);
  assert.equal(near(1).textContent, 'By 28 Oct 2026 · 1 day left');
}
// AN ASK OPENS WHAT IT ASKS FOR (rendering v16; the readability design): the item as the board
// of the same conversation now holds it, else as the answer admitted it.
{
  const ask = { start: 0, end: 15, text: 'Was it received', dispute: { id: 'D1', name: 'Possession of the plot' },
    item: { need: 'Proof the cancellation letter was received', why: 'As the answer admitted it.', note: null,
            group: 'needed', status: 'not_given', law, evidence: null, asked_in: 't1', noted_in: 't1' } };
  context.state.chatBoard = { ...board, chat_id: 'c1' };
  context.openAskedItem({ chat_id: 'c1' }, ask, 'opener');
  let view = shown.pop();
  assert.deepEqual([view.title, view.kind, view.opener], ['Proof the cancellation letter was received',
    'Needed · Dispute 1', 'opener']);
  assert.equal(view.content[0].textContent, 'Coming or unclear', 'as the board now holds it');
  context.openAskedItem({ chat_id: 'c2' }, ask, 'opener');
  view = shown.pop();
  assert.equal(view.kind, 'Needed · Possession of the plot');
  assert.deepEqual(Array.from(view.content.slice(0, 3), (node) => node.textContent), ['Not yet given',
    'Why it is neededAs the answer admitted it.Article 54, The Limitation Act, 1963',
    'Where it standsNot in your messages or documents yet.']);
  message.value = '';
  view.content.at(-1).children[0].click();
  assert.equal(message.value, 'About "Proof the cancellation letter was received" (Possession of the plot): ');
  message.value = '';
  // A paragraph is drawn with its links when a source can be read or an ask opens an item.
  assert.deepEqual([context.linkedBody({ asks: [ask] }), context.linkedBody({ asks: [] }),
    context.linkedBody({ source: { brain: true } }), context.linkedBody({})], [true, false, true, false]);
  // An item whose law is of an Act India Code does not list as in force says so (P21).
  const repealed = { ...ask, item: { ...ask.item, law: { ...law, in_force: 'not in force according to India Code' } } };
  context.openAskedItem({ chat_id: 'c2' }, repealed, 'opener');
  view = shown.pop();
  const why = view.content[1];
  assert.equal(why.children.at(-1).className, 'source-role warn');
  assert.equal(why.children.at(-1).textContent, 'Not in force according to India Code');
}
console.log('checklist board: ok');
