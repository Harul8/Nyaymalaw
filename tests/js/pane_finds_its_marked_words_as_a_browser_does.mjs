// THE READING PANE FINDS ITS MARKED WORDS AS A BROWSER HOLDS THEM (5 Nov 2026; owner's screenshot: "The saved passage could not be
// read. passage?.children?.find is not a function"). In a browser an element's children are a live collection, not a list: it has no
// find. The pane asked it for one after drawing each passage, and every passage it opened - a judgment, a section, a page - then said it
// could not be read. The other page tests' stand-ins give children as a list, which is why none caught it. Here the stand-in holds them
// as a browser does. Runs the pane's actual finish() from nm/app/brain-sources.js; not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const pane = readFileSync(new URL('../../nm/app/brain-sources.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const at = pane.indexOf('\n  function finish(shown, kept) {');
assert.ok(at >= 0, 'the pane has finish()');
const finish = pane.slice(at, pane.indexOf('\n  }\n', at) + 4);

// A browser's collection of child elements: indexed, with a length, and none of a list's methods.
function collection(items) {
  const held = { length: items.length, item: (index) => items[index] ?? null };
  items.forEach((item, index) => { held[index] = item; });
  return held;
}
const scrolled = [];
const mark = { tagName: 'MARK', scrollIntoView: (how) => scrolled.push(how) };
const passage = { className: 'brain-source-text passage', children: collection([mark]),
  querySelector: (selector) => (selector === 'mark' ? mark : null) };
const body = { scrollTop: 7, replaceChildren(...nodes) { this.shown = nodes; } };
const status = { textContent: 'Opening the saved passage…' };
const context = vm.createContext({ node: (id) => (id === 'brain-source-body' ? body : status) });
vm.runInContext(finish, context);

assert.doesNotThrow(() => context.finish([{ className: 'hint' }, passage], null), 'a passage drawn is never then said unreadable');
assert.deepEqual(body.shown[1], passage);
assert.equal(body.scrollTop, 0);
assert.equal(status.textContent, '');
assert.equal(JSON.stringify(scrolled), '[{"block":"center"}]', 'the words used are brought into view');
// Where the advocate had scrolled, that place is kept and nothing is brought into view.
context.finish([passage], { scroll: 120 });
assert.equal(body.scrollTop, 120);
assert.equal(scrolled.length, 1);
// A passage with nothing marked opens as well.
assert.doesNotThrow(() => context.finish([{ className: 'brain-source-text passage', children: collection([]),
  querySelector: () => null }], null));

console.log('pane_finds_its_marked_words_as_a_browser_does.mjs: ok');
