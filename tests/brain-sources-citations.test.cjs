/* The shipped source-link script in a minimal DOM; no server or provider calls. */
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function element(tag) {
  return {tag, children: [], attributes: {}, className: '', textContent: '', listeners: {},
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, handler) { this.listeners[name] = handler; },
    focus() {}, showModal() { this.open = true; }, close() { this.open = false; }};
}

function load() {
  const nodes = {};
  const document = {
    getElementById: (id) => (nodes[id] ||= element('div')),
    createElement: (tag) => element(tag),
    createTextNode: (text) => ({text: true, textContent: text}),
  };
  const window = {addEventListener() {}};
  const code = fs.readFileSync(path.join(__dirname, '..', 'nm', 'app', 'brain-sources.js'), 'utf8');
  vm.runInNewContext(code, {window, document, JSON, Number, Array, Set, Map, Object, String});
  return window.NmBrainSources;
}

const source = (n) => ({brain: true, kind: 'provision', id: `provision:${n}`, digest: `d${n}`,
  label: `Act ${n}`, locator: `s.${n}`, text: `Words of section ${n}.`});

function answerFor(el) {
  return {turn_id: 'turn', chat_id: 'chat', elements: [el]};
}

function rendered(el) {
  const host = element('p');
  const count = load().appendBody(host, answerFor(el), el);
  return {count, parts: host.children.map((c) => c.text ? ['text', c.textContent]
    : [c.className, c.textContent])};
}

test('v4 links sit at saved offsets and unnamed sources follow as markers', () => {
  const text = 'Under section 1 the deposit is refundable. Section 1 also applies.';
  const el = {text, sources: [source(1), source(2)], refs: ['s.1', 's.2'],
    inline_citations: [{text: 'Section 1', source_id: 'provision:1', source_index: 0, start: 43, end: 52}],
    citation_markers: [{source_id: 'provision:2', source_index: 1}]};
  const {count, parts} = rendered(el);
  assert.equal(count, 2);
  assert.deepEqual(parts, [
    ['text', 'Under section 1 the deposit is refundable. '],
    ['citation-link', 'Section 1'],
    ['text', ' also applies.'],
    ['text', ' '],
    ['citation-link citation-marker', 'Act 2 · s.2'],
  ]);
});

test('an offset that does not hold the saved words links nothing', () => {
  const el = {text: 'Section 1 applies.', sources: [source(1)], refs: ['s.1'],
    inline_citations: [{text: 'Section 1', source_id: 'provision:1', source_index: 0, start: 2, end: 11}],
    citation_markers: []};
  assert.deepEqual(rendered(el), {count: 0, parts: [['text', 'Section 1 applies.']]});
});

test('earlier versions keep the unique-phrase rule and have no markers', () => {
  const el = {text: 'Act 1 and Act 1.', sources: [source(1)], refs: ['s.1'],
    inline_citations: [{text: 'Act 1', source_id: 'provision:1', source_index: 0}]};
  assert.deepEqual(rendered(el), {count: 0, parts: [['text', 'Act 1 and Act 1.']]});
  const whole = {text: 'The paragraph.', sources: [source(1)], refs: ['s.1'],
    inline_citations: [{text: 'The paragraph.', source_id: 'provision:1', source_index: 0}]};
  assert.deepEqual(rendered(whole).parts, [['text', ''], ['citation-link', 'The paragraph.'], ['text', '']]);
});

test('a marker for a source the answer does not bind is not drawn', () => {
  const foreign = {...source(2), id: 'provision:other'};
  const el = {text: 'Plain words.', sources: [source(1), foreign], refs: ['s.1', 's.2'],
    inline_citations: [], citation_markers: [{source_id: 'provision:2', source_index: 1},
      {source_id: 'provision:1', source_index: 0}]};
  const {count, parts} = rendered(el);
  assert.equal(count, 1);
  assert.deepEqual(parts.slice(-1), [['citation-link citation-marker', 'Act 1 · s.1']]);
});
