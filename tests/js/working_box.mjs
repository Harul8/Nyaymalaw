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
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(name, value) { this.attributes[name] = value; }
}
const context = vm.createContext({ document: { createElement: (tag) => new Node(tag) } });
vm.runInContext(app.slice(from, to), context);

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
console.log('working box: ok');
