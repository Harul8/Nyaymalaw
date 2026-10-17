// What each dispute needs, on the matter board (owner decisions, 17 Oct 2026): its time
// limits as code worked them out, how much is in hand, each item under Needed and Would
// strengthen with its mark, an item's details in the reading pane, and the facts and
// standing instructions folded below. Offline substitutes for the DOM; not browser QA.
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
  click() { this.listeners.click?.(); }
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
  window: { NmBrainSources: { showContent: (title, content, opener) => shown.push({ title, content, opener }) } },
  $: (id) => (id === 'message' ? message : new Element('div')),
  Event: class { constructor(type) { this.type = type; } },
  sizeComposer: () => { sized += 1; },
  stateBlock: (_kind, text) => Object.assign(new Element('p'), { textContent: text }),
  openBoardPane: () => {}, renderDisputeDetail: () => [],
  CERTAINTY: { reported: 'Reported' }, QUESTION_STATUS: { researched: 'researched' },
  factPlace: () => 'From your messages',
});
vm.runInContext(between('function renderChatBoard(board) {', '// A DISPUTE IN DETAIL'), context);
vm.runInContext(between('function timeLimitStanding(rows) {', 'function renderTimeLimits(items) {'), context);
vm.runInContext(between('function fileDate(iso) {', 'function fileAttention('), context);

const at = '2026-10-18T05:00:00+00:00';
const law = { kind: 'provision', title: 'The Limitation Act, 1963', locator: 'Article 54',
  words: 'Three years from the date fixed for the performance' };
const item = (id, need, group, status, extra = {}) => ({ id, need, group, status, law, evidence: null,
  asked_at: null, ...extra });
const board = {
  state: 'ready', related_points: [], instructions: ['Do not contact the buyer.'],
  facts: [{ id: 'f1', fact: 'The plot was sold twice', certainty: 'reported', from: 'advocate' }],
  disputes: [
    { id: 'D1', name: 'Possession of the plot', between: ['Client', 'Later buyer'], questions: [],
      checklist: { name: 'Possession of the plot', answered_at: at, in_hand: 1, time_limits: [
        { what: 'Last day to file the suit', rows: [['Last day', '10 January 2027 (Sunday)'],
          ['As of', '18 October 2026 (Sunday)'], ['Result', 'Open'], ['Days left', '84']] },
        { what: 'Last day to answer the notice', rows: [['Not assessed', 'the notice date is not given']] }],
      items: [
        item('K1', 'The sale agreement', 'needed', 'in_hand',
          { evidence: { from: 'document', document: 'agreement.pdf', page: 'page 1', words: 'agreed to sell',
                        given_at: at } }),
        item('K2', 'Proof the cancellation letter was received', 'needed', 'coming_or_unclear',
          { evidence: { from: 'message', words: 'I am not sure he received it', given_at: at } }),
        item('K3', 'The date possession was refused', 'needed', 'not_given', { asked_at: at }),
        item('K4', 'The original receipt', 'would_strengthen', 'not_available',
          { evidence: { from: 'message', words: 'the receipt is lost', given_at: at } })] } },
    { id: 'D2', name: 'Cheating', between: [], questions: [],
      checklist: { name: 'Cheating', answered_at: at, in_hand: 0, time_limits: [], items: [] } },
    { id: 'D3', name: 'An earlier dispute', between: [], questions: [{ status: 'researched' }] }],
};
const [lede, disputes, facts, instructions] = context.renderChatBoard(board);
assert.match(lede.textContent, /As NM understood this matter/);
const [heading, first, second, third] = disputes.children;
assert.equal(heading.textContent, 'Disputes (3)');

// The dispute, its time limits, how much is in hand, and its items by group with their marks.
assert.equal(first.attributes['aria-label'], 'Possession of the plot');
const open = find(first, (node) => node.className === 'dispute-open')[0];
assert.equal(open.textContent, 'Possession of the plot');
const deadlines = find(first, (node) => /^dispute-deadline( |$)/.test(node.className || ''));
assert.deepEqual(deadlines.map((line) => line.children.map((part) => part.textContent)), [
  ['Last day to file the suit', '10 January 2027 (Sunday)', 'Open · 84 days left · as of 18 October 2026 (Sunday)'],
  ['Last day to answer the notice', 'Last day not worked out', 'Not assessed: the notice date is not given']]);
assert.equal(find(first, (node) => node.className === 'board-status check-count')[0].textContent, '1 of 4 in hand');
assert.deepEqual(find(first, (node) => node.className === 'check-group').map((node) => node.textContent),
  ['Needed', 'Would strengthen']);
const rows = find(first, (node) => /^check-item /.test(node.className || ''));
assert.deepEqual(rows.map((row) => [row.className, row.children.map((part) => part.textContent)]), [
  ['check-item check-item--in_hand', ['✓', 'The sale agreement', 'In hand']],
  ['check-item check-item--coming_or_unclear', ['◐', 'Proof the cancellation letter was received', 'Coming or unclear']],
  ['check-item check-item--not_given', ['○', 'The date possession was refused', 'Not yet given · asked 18 Oct 2026']],
  ['check-item check-item--not_available', ['✕', 'The original receipt', 'Not available']]]);
assert.equal(rows[0].children[0].attributes['aria-hidden'], 'true', 'the mark is drawn; the words say it');

// An item opens in the reading pane: where it stands, the words that show it, the law words.
rows[1].click();
const { title, content, opener } = shown.pop();
assert.equal(title, 'Proof the cancellation letter was received');
assert.equal(opener, rows[1]);
assert.deepEqual(Array.from(content, (node) => node.textContent), [
  '◐ Coming or unclear', 'Needed · Possession of the plot', 'From your message of 18 Oct 2026, in your words',
  'I am not sure he received it', 'What the law says', 'The Limitation Act, 1963 · Article 54',
  'Three years from the date fixed for the performance', 'Tell NM about this']);
rows[0].click();
assert.equal(shown.pop().content[2].textContent, 'From agreement.pdf, page 1');
content.at(-1).click();
assert.equal(message.value, 'About "Proof the cancellation letter was received" (Possession of the plot): ');
assert.ok(message.focused && sized === 1 && message.dispatched === 'input');

// An answered dispute with no law-backed item says so; an earlier board is as it was.
assert.match(second.textContent, /NM found nothing this dispute needs in the law it holds/);
assert.match(third.textContent, /1 legal question · 1 researched/);

// The facts and standing instructions fold below.
assert.equal(facts.tag, 'details');
assert.equal(facts.children[0].textContent, 'Facts, as you gave them (1)');
assert.equal(instructions.children[0].textContent, 'Your standing instructions (1)');
console.log('checklist board: ok');
