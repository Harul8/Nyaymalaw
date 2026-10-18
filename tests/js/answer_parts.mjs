// A reply answering several disputes shows each dispute's part under its numbered heading,
// all open, as the readability design shows it (owner, 18 Oct 2026: "exactly the way your
// artifact has presented"; it supersedes the decision of 15 Oct to start later parts
// collapsed under an index). Offline substitutes for the DOM; not browser QA.
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

const context = vm.createContext({ document: { createElement: el, getElementById: () => null }, String, Array });
vm.runInContext(app.slice(start, end), context);
const draw = (into, element) => into.appendChild({ drawn: element.text, children: [] });

// Two disputes: each under its numbered heading, both open; no index, nothing to collapse.
{
  const wrap = el('div');
  context.renderParts(wrap, [
    { kind: 'GREETING', text: 'Good morning.' },
    { kind: 'HEADING', text: 'Obstruction of access' },
    { kind: 'LAW', text: 'Necessity requires more.' },
    { kind: 'HEADING', text: 'The returned cheque' },
    { kind: 'LAW', text: 'Section 138 concerns…' },
  ], { turnId: 't1' }, draw);
  assert.equal(wrap.children[0].drawn, 'Good morning.', 'the opening stays above the parts');
  const parts = wrap.children.slice(1);
  assert.deepEqual(parts.map((part) => part.className), ['answer-part', 'answer-part']);
  assert.deepEqual(parts.map((part) => part.children[0].children.map((node) => [node.className, node.textContent])), [
    [['n', '1'], ['part-title', 'Obstruction of access']], [['n', '2'], ['part-title', 'The returned cheque']]]);
  const bodies = find(wrap, (n) => n.className === 'part-body');
  assert.deepEqual(bodies.map((b) => b.hidden), [false, false]);
  assert.deepEqual(bodies.map((b) => b.children[0].drawn), ['Necessity requires more.', 'Section 138 concerns…']);
  assert.equal(find(wrap, (n) => n.tagName === 'NAV' || /toggle/.test(n.className || '')).length, 0);
}

// One dispute, or none: drawn as before, with no parts.
{
  const wrap = el('div');
  context.renderParts(wrap, [{ kind: 'LAW', text: 'Only law.' }], {}, draw);
  assert.deepEqual(wrap.children.map((c) => c.drawn), ['Only law.']);
}

// An answer with a part held back (owner decision, 17 Oct 2026): code's notices about the
// whole answer, and what NM needs from the advocate (rendering v14), stay outside the parts.
{
  const wrap = el('div');
  context.renderParts(wrap, [
    { kind: 'NOTICE', text: 'This answer is incomplete: 1 of its 3 sections is held back below.' },
    { kind: 'GREETING', text: 'Good morning.' },
    { kind: 'HEADING', text: 'Obstruction of access' },
    { kind: 'LAW', text: 'Necessity requires more.' },
    { kind: 'HEADING', text: 'The returned cheque' },
    { kind: 'HELD', text: 'Held back: The returned cheque.' },
    { kind: 'NEEDS', text: 'What I need from you', items: [] },
    { kind: 'NOTICE', text: 'Shall I try the held-back section again?' },
  ], { turnId: 't2' }, draw);
  assert.equal(wrap.children[0].drawn, 'This answer is incomplete: 1 of its 3 sections is held back below.');
  assert.deepEqual(wrap.children.slice(-2).map((node) => node.drawn),
    ['What I need from you', 'Shall I try the held-back section again?']);
  const bodies = find(wrap, (n) => n.className === 'part-body');
  assert.deepEqual(bodies[1].children.map((n) => n.drawn), ['Held back: The returned cheque.']);
  assert.deepEqual(bodies.map((b) => b.hidden), [false, false], 'a held part is shown with the answer');
}

console.log('answer parts: ok');
