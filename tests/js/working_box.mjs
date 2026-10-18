// A time limit's Working box (item 9, 15 Oct 2026): the browser draws the labelled rows
// and lists the server saved, exactly as given; it computes, labels and words nothing
// (the rows themselves are tested with the rendering, tests/test_core_calculation.py).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const from = app.indexOf("// A TIME LIMIT'S WORKING");
const to = app.indexOf('// A REPLY ANSWERING SEVERAL DISPUTES', from);
assert.ok(from >= 0 && to > from);

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.handlers = {}; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  appendChild(node) { this.children.push(node); return node; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
}
const opened = [];
const context = vm.createContext({ document: { createElement: (tag) => new Node(tag) },
  window: { NmBrainSources: { showContent: (title, content, opener, back, kind) => opened.push({ title, content, kind }) } } });
vm.runInContext(app.slice(from, to), context);
// The table writes a saved calendar day as the design does ('14 Oct 2026').
vm.runInContext(app.slice(app.indexOf('function dayDate(iso) {'), app.indexOf('// The day and month of a moment saved')),
  context);

const drawn = (box) => box.children.map((node) => [node.tag, node.className,
  node.children.length ? node.children.map((child) => `${child.tag}:${child.textContent}`) : node.textContent]);
const rows = [['Provision', 's.142(1)(b), The Negotiable Instruments Act, 1881'], ['Period', '“one month”'],
  ['Last day', '14 October 2026 (Wednesday)'], ['Result', 'Early'], ['Days before the earliest day', '2']];
const worked = context.renderWorking({ kind: 'WORKING', text: 'Last day to file the complaint',
  working: { what: 'Last day to file the complaint', last_day: '2026-10-14', rows,
    lists: [['Assumed', ['The dates are as reported.']], ['May extend time (not counted)', ['Proviso to s.142(1)(b).']]] } });
assert.equal(worked.className, 'el WORKING working-box');
assert.equal(worked.attributes['aria-label'], 'Working: Last day to file the complaint');
assert.deepEqual(drawn(worked), [
  ['p', 'working-label', 'Working'],
  ['p', 'working-result', 'Last day to file the complaint'],
  ['dl', 'working-rows', rows.flatMap(([label, value]) => [`dt:${label}`, `dd:${value}`])],
  ['p', 'working-label', 'Assumed'],
  ['ul', 'working-list', ['li:The dates are as reported.']],
  ['p', 'working-label', 'May extend time (not counted)'],
  ['ul', 'working-list', ['li:Proviso to s.142(1)(b).']]]);

const skipped = context.renderWorking({ kind: 'WORKING', text: 'A period',
  working: { what: 'A period', not_assessed: 'the words are not in the held text',
    rows: [['Not assessed', 'the words are not in the held text']], lists: [] } });
assert.deepEqual(drawn(skipped).slice(1), [['p', 'working-result', 'A period'],
  ['dl', 'working-rows', ['dt:Not assessed', 'dd:the words are not in the held text']]]);

// "In short" and the time limits (owner decisions, 17 Oct 2026): runs of summaries and of
// time-limit boxes are gathered where they stand, nothing dropped or reordered.
const working = (what, rows) => ({ kind: 'WORKING', text: what, working: { what, rows, lists: [] } });
const closed = ['Court closed on the last day', 'Limitation Act s.4 not applied: the court calendar is not held'];
const suit = working('Last day to file the suit', [['Provision', 'Article 54, The Limitation Act, 1963'],
  ['Last day', '10 January 2027 (Sunday)'], ['As of', '17 October 2026 (Saturday)'], ['Result', 'Open'],
  ['Days left', '85'], closed]);
const notice = working('Last day to reply to the notice', [['Last day', '16 October 2026 (Friday)'],
  ['As of', '17 October 2026 (Saturday)'], ['Result', 'Passed'], ['Days since the last day', '1'], closed]);
const unread = working('A period', [['Not assessed', 'the words are not in the held text']]);
const grouped = context.groupAnswerElements([{ kind: 'GREETING', text: 'Good morning.' },
  { kind: 'SUMMARY', text: 'One.' }, { kind: 'SUMMARY', text: 'Two.' }, suit, notice, unread,
  { kind: 'HEADING', text: 'Dispute 1' }, { kind: 'LAW', text: 'Law.' }, { kind: 'SUMMARY', text: 'Three.' },
  { kind: 'WORKING', text: 'No saved working.' }]);
assert.deepEqual(Array.from(grouped, (el) => [el.kind, el.items ? Array.from(el.items, (item) => item.text) : el.text]), [
  ['GREETING', 'Good morning.'], ['IN_SHORT', ['One.', 'Two.']],
  ['TIME_LIMITS', ['Last day to file the suit', 'Last day to reply to the notice', 'A period']],
  ['HEADING', 'Dispute 1'], ['LAW', 'Law.'], ['IN_SHORT', ['Three.']], ['WORKING', 'No saved working.']]);

// The table, as the design shows it (18 Oct 2026): each limit, its last day and what is left,
// from the saved rows; why a limit was not worked out stays under its name; the day counts
// were made and the counting's caveat are each said once under it; the working opens in the
// reading pane.
const table = context.renderTimeLimits([suit, notice, unread]);
assert.equal(table.className, 'el time-limits');
assert.equal(table.attributes['aria-label'], 'Time limits');
const [scroll, ...notes] = table.children;
assert.deepEqual(notes.map((note) => [note.className, note.textContent]), [
  ['time-limit-note', 'Days are counted as of 17 October 2026 (Saturday).'], ['time-limit-note', closed[1]]]);
const [thead, tbody] = scroll.children[0].children;
assert.deepEqual(thead.children[0].children.map((cell) => cell.textContent), ['Time limit', 'Last day', 'Left']);
assert.deepEqual(tbody.children.map((row) => row.children.map((cell) => cell.textContent)), [
  ['Last day to file the suit · working', '10 January 2027 (Sunday)', '85 days left'],
  ['Last day to reply to the notice · working', '16 October 2026 (Friday)', 'Passed · 1 day since the last day'],
  ['A period · workingNot worked out: the words are not in the held text', '—', '—']]);
const link = tbody.children[1].children[0].children[1];
assert.equal(link.className, 'cite');
link.handlers.click();
assert.equal(opened[0].title, 'Last day to reply to the notice');
assert.equal(opened[0].kind, 'Time limit · worked out by code');
assert.deepEqual(Array.from(opened[0].content, (node) => node.textContent).slice(0, 1), ['Last day16 October 2026 (Friday)As of17 October 2026 (Saturday)ResultPassedDays since the last day1Court closed on the last day' + closed[1]]);
// A saved calendar day is written short where the server saved it.
const dated = context.renderTimeLimits([{ ...suit, working: { ...suit.working, last_day: '2027-01-10' } }]);
assert.equal(dated.children[0].children[0].children[1].children[0].children[1].textContent, '10 Jan 2027');
console.log('working box: ok');
