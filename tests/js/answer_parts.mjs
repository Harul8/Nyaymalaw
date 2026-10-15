// A reply answering several disputes shows links to each, the first dispute open
// and every later one collapsed under its heading (owner decision, 15 Oct 2026).
// Offline substitutes for the DOM; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function renderParts(');
const end = app.indexOf('function repaint() {', start);
assert.ok(start >= 0 && end > start, 'renderParts moved');

function el(tag) {
  const node = {
    tagName: tag.toUpperCase(), className: '', children: [], attributes: {}, handlers: {},
    textContent: '', hidden: false, id: '', href: '', type: '',
    setAttribute(name, value) { this.attributes[name] = String(value); },
    append(...kids) { this.children.push(...kids); },
    appendChild(kid) { this.children.push(kid); return kid; },
    addEventListener(name, fn) { this.handlers[name] = fn; },
  };
  return node;
}
const find = (node, test, found = []) => {
  if (test(node)) found.push(node);
  for (const kid of node.children || []) find(kid, test, found);
  return found;
};

let repaints = 0;
const context = vm.createContext({
  document: { createElement: el, getElementById: () => null },
  repaint: () => { repaints += 1; },
  String, Array, Boolean,
});
vm.runInContext(app.slice(start, end), context);
const draw = (into, element) => into.appendChild({ drawn: element.text, children: [] });

// Two disputes: links, the first open, the second collapsed.
{
  const wrap = el('div');
  const entry = { turnId: 't 1/a' };
  context.renderParts(wrap, [
    { kind: 'GREETING', text: 'Good morning.' },
    { kind: 'HEADING', text: 'Obstruction of access' },
    { kind: 'LAW', text: 'Necessity requires more.' },
    { kind: 'HEADING', text: 'The returned cheque' },
    { kind: 'LAW', text: 'Section 138 concerns…' },
  ], entry, draw);
  assert.equal(wrap.children[0].drawn, 'Good morning.', 'the opening stays above the parts');
  const nav = wrap.children[1];
  assert.equal(nav.tagName, 'NAV');
  assert.deepEqual(nav.children.map((a) => a.textContent), ['1 · Obstruction of access', '2 · The returned cheque']);
  const bodies = find(wrap, (n) => n.className === 'part-body');
  assert.deepEqual(bodies.map((b) => b.hidden), [false, true]);
  assert.deepEqual(bodies.map((b) => b.children[0].drawn), ['Necessity requires more.', 'Section 138 concerns…']);
  assert.equal(bodies[0].id, 'part-t-1-a-0', 'ids are safe for any turn id');
  const toggles = find(wrap, (n) => n.className === 'ghost part-toggle');
  assert.deepEqual(toggles.map((t) => t.attributes['aria-expanded']), ['true', 'false']);
  toggles[1].handlers.click();
  assert.equal(JSON.stringify(entry.openParts), '[true,true]');
  assert.equal(repaints, 1);
  nav.children[0].handlers.click({ preventDefault() {} });
  assert.equal(repaints, 2);
}

// One dispute, or none: drawn as before, with no links or parts.
{
  const wrap = el('div');
  context.renderParts(wrap, [{ kind: 'LAW', text: 'Only law.' }], {}, draw);
  assert.deepEqual(wrap.children.map((c) => c.drawn), ['Only law.']);
}

console.log('answer parts: ok');
