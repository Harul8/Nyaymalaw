// WHAT AN ANSWER HAS SHOWN SO FAR (owner decisions P26-P27, 19 Oct 2026): while the answer is
// still being written, each dispute's section that passed its checks is drawn plainly under
// the progress - headings, "In short", paragraphs, code's notes and the places still being
// written - and the saved answer replaces it. Offline substitutes for the DOM; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const slice = (from, to) => {
  const start = app.indexOf(from);
  const end = app.indexOf(to, start);
  assert.ok(start >= 0 && end > start, `${from} moved`);
  return app.slice(start, end);
};

function el(tag) {
  return {
    tagName: tag.toUpperCase(), className: '', children: [], attributes: {}, textContent: '',
    setAttribute(name, value) { this.attributes[name] = String(value); },
    append(...kids) { this.children.push(...kids); },
    appendChild(kid) { this.children.push(kid); return kid; },
  };
}
const context = vm.createContext({ document: { createElement: el }, String, Array, Number });
vm.runInContext(slice('function groupAnswerElements(', '// THE TIME LIMITS AS ONE SMALL TABLE'), context);
vm.runInContext(slice('function renderShownSoFar(', 'function repaint() {'), context);
context.renderTimeLimits = (items) => ({ tagName: 'SECTION', className: 'time-limits', children: [], items });

const plain = (kind, text, extra = {}) => ({ kind, text, ...extra });
const box = context.renderShownSoFar([
  plain('SUMMARY', 'File the complaint first.'),
  plain('SUMMARY', 'The lease needs its deed.'),
  plain('HEADING', 'The cheque'),
  plain('NEXT_STEP', 'File by Tuesday.'),
  plain('NOTE', 'Left out of this section: 1 paragraph.', { disclosure: true }),
  plain('HEADING', 'The lease'),
  plain('FALLBACK', 'Not a full answer on The lease: the AI service did not respond.\nWhat you told me: “x”.',
    { disclosure: true }),
  plain('HEADING', 'The notice'),
  plain('WAITING', 'Still being written and checked: The notice.', { disclosure: true }),
  plain('NEEDS', 'What I need from you'),
  plain('QUESTION', 'When was the cheque returned?'),
]);
const drawn = box.children.map((node) => [node.tagName, node.className, node.textContent,
  (node.children || []).map((kid) => kid.textContent)]);
assert.equal(box.className, 'shown-so-far');
assert.equal(box.attributes['aria-label'], 'Shown so far');
assert.deepEqual(drawn.slice(1), [
  ['H4', 'shown-so-far-title', 'In short', []],
  ['UL', 'in-short-list', '', ['File the complaint first.', 'The lease needs its deed.']],
  ['H3', 'part-title', 'The cheque', []],
  ['P', 'el NEXT_STEP', 'File by Tuesday.', []],
  ['P', 'el NOTE disclosure', 'Left out of this section: 1 paragraph.', []],
  ['H3', 'part-title', 'The lease', []],
  ['P', 'el FALLBACK disclosure', 'Not a full answer on The lease: the AI service did not respond.', []],
  ['H3', 'part-title', 'The notice', []],
  ['P', 'el WAITING disclosure', 'Still being written and checked: The notice.', []],
  ['H4', 'shown-so-far-title', 'What I need from you', []],
  ['UL', 'need-list', '', ['When was the cheque returned?']],
]);
console.log('OK  what an answer has shown so far is drawn plainly, in its order');
