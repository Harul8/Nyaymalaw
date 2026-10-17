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
    // The reading pane listens for Escape on the page (since 16 Oct 2026).
    addEventListener() {},
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

// An earlier answer (rendering v4 to v10) keeps its markers, folded under one "Sources"
// control after the paragraph (owner decision 6, 17 Oct 2026).
function folded(host) {
  const toggle = host.children.find((c) => c.className === 'citation-link citation-sources');
  const fold = host.children.find((c) => c.className === 'citation-fold');
  return {toggle, fold, chips: fold ? fold.children.filter((c) => !c.text).map((c) => [c.className, c.textContent]) : []};
}

test('v4 links sit at saved offsets and unnamed sources fold under one Sources control', () => {
  const text = 'Under section 1 the deposit is refundable. Section 1 also applies.';
  const el = {text, sources: [source(1), source(2)], refs: ['s.1', 's.2'],
    inline_citations: [{text: 'Section 1', source_id: 'provision:1', source_index: 0, start: 43, end: 52}],
    citation_markers: [{source_id: 'provision:2', source_index: 1}]};
  const host = element('p');
  const sources = load();
  const answer = answerFor(el);
  assert.equal(sources.appendBody(host, answer, el), 2);
  assert.deepEqual(host.children.map((c) => c.text ? ['text', c.textContent] : [c.className, c.textContent]), [
    ['text', 'Under section 1 the deposit is refundable. '],
    ['citation-link', 'Section 1'],
    ['text', ' also applies.'],
    ['text', ' '],
    ['citation-link citation-sources', 'Sources (1)'],
    ['text', ' '],
    ['citation-fold', ''],
  ]);
  const {toggle, fold, chips} = folded(host);
  assert.deepEqual(chips, [['citation-link citation-marker', 'Act 2 · s.2']]);
  assert.equal(fold.hidden, true);
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  toggle.listeners.click();
  assert.equal(fold.hidden, false);
  assert.equal(toggle.attributes['aria-expanded'], 'true');
  // The thread is redrawn while a later answer is prepared: an opened fold stays open.
  const redrawn = element('p');
  sources.appendBody(redrawn, answer, el);
  assert.equal(folded(redrawn).fold.hidden, false);
  assert.equal(folded(redrawn).toggle.attributes['aria-expanded'], 'true');
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
  const host = element('p');
  assert.equal(load().appendBody(host, answerFor(el), el), 1);
  const {toggle, chips} = folded(host);
  assert.equal(toggle.textContent, 'Sources (1)');
  assert.deepEqual(chips, [['citation-link citation-marker', 'Act 1 · s.1']]);
  // With no marker it may draw, there is no Sources control at all.
  const none = {...el, citation_markers: [{source_id: 'provision:2', source_index: 1}]};
  const bare = element('p');
  assert.equal(load().appendBody(bare, answerFor(none), none), 0);
  assert.deepEqual(folded(bare), {toggle: undefined, fold: undefined, chips: []});
});
