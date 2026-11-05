// Each conversation in the history under its title (plan AN.43, D81; owner, 5 Nov 2026: "put a small name to the matters in the
// list instead of large text"): the title the model wrote; until there is one, the first message's first ten words; the first message
// itself on hover. Runs the actual historyTitle and historyChatRow of nm/app/app.js against offline stand-ins; the words are invented.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
function fn(name) {
  const at = app.indexOf(`\nfunction ${name}(`);
  assert.ok(at >= 0, `the page has ${name}`);
  return app.slice(at, app.indexOf('\n}\n', at) + 3);
}

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.dataset = {}; this.textContent = ''; this.title = ''; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
}
const context = vm.createContext({ document: { createElement: (tag) => new Element(tag) }, historyWhen: () => ' · 4 Nov',
  restorePendingChat: async () => {}, state: {} });
vm.runInContext(fn('historyTitle') + fn('historyChatRow'), context);

const message = 'Please analyse the attached sale deed and the two notices from the bank and tell me what we can do';
const titled = context.historyChatRow({ chat_id: 'c1', title: 'Asha Rao v. Greenfield Builders', preview: message, turn_count: 2 }, 1, 1);
const [title, details] = titled.children;
assert.equal(title.textContent, 'Asha Rao v. Greenfield Builders');
assert.equal(title.title, message, 'the first message on hover');
assert.equal(titled.attributes['aria-label'], 'Open conversation: Asha Rao v. Greenfield Builders');
assert.equal(details.textContent, '2 messages · 4 Nov');
// Until there is a title: the first ten words, and an ellipsis where there is more.
const untitled = context.historyChatRow({ chat_id: 'c2', title: null, preview: message, turn_count: 1 }, 1, 1);
assert.equal(untitled.children[0].textContent, 'Please analyse the attached sale deed and the two notices…');
assert.equal(context.historyTitle({ preview: 'Analyse this' }), 'Analyse this');
assert.equal(context.historyTitle({ preview: '' }), 'Conversation');

console.log('history_titles.mjs: ok');
