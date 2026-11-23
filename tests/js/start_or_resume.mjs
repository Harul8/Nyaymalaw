// Start or resume (plan AN.77; owner decision D333, 23 Nov 2026), on the page: the opening view's short list of recent work is
// loaded when opened and emptied when closed; it keeps its own generation, so loading it never cancels the history list's loading,
// nor that list this one's; a reply that comes after the list was closed paints nothing; a conversation that cannot be opened is
// said in the list its row is in, even after the history list has loaded again. The Attach button keeps its short word on screen
// and says in full what it does. Runs the actual showRecentWork and historyChatRow of nm/app/app.js against offline substitutes for
// the DOM and the server; the conversations are invented. Not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const page = readFileSync(new URL('../../nm/app/index.html', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
function fn(name) {
  const starts = [`\nfunction ${name}(`, `\nasync function ${name}(`];
  const at = Math.min(...starts.map((start) => app.indexOf(start)).filter((index) => index >= 0));
  assert.ok(Number.isFinite(at), `the page has ${name}`);
  const end = app.indexOf('\n}\n', at);
  return app.slice(at, end + 3);
}

class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.listeners = {}; this._text = '';
    this.parentElement = null;
  }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  adopt(children) { for (const child of children) child.parentElement = this; }
  replaceChildren(...children) { this._text = ''; this.adopt(children); this.children = children; }
  append(...children) { this.adopt(children); this.children.push(...children); }
  appendChild(child) { this.append(child); return child; }
  prepend(...children) { this.adopt(children); this.children.unshift(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(event, handler) { this.listeners[event] = handler; }
}

const list = new Element('div');
const replies = [];
const asked = [];
const opened = [];
const state = { sessionGeneration: 1, matterListGeneration: 7, recentWorkGeneration: 0, railGeneration: 0 };
const context = vm.createContext({
  document: { createElement: (tag) => new Element(tag) },
  state,
  $: (id) => { assert.equal(id, 'recent-work-list'); return list; },
  api: (url) => { asked.push(url); return replies.shift()(); },
  historyTitle: (chat) => chat.title,
  historyWhen: () => '',
  restorePendingChat: (chatId) => { opened.push(chatId); return Promise.reject(new Error('It is not there')); },
  stateBlock: (kind, text) => Object.assign(new Element('div'), { className: kind, _text: text }),
});
vm.runInContext(fn('historyChatRow') + fn('showRecentWork'), context);
const chats = [{ chat_id: 'c3', title: 'Shop lease', turn_count: 2 }, { chat_id: 'c2', title: 'Cheque returned', turn_count: 1 },
  { chat_id: 'c1', title: 'Boundary wall', turn_count: 4 }];
const later = () => { let answer; const promise = new Promise((resolve) => { answer = resolve; }); return { promise, answer }; };

// Opened: three conversations, newest first, asked for once; the history list's generation is left alone.
{
  const reply = later();
  replies.push(() => reply.promise);
  const disclosure = { open: true };
  const loading = context.showRecentWork(disclosure);
  assert.equal(list.textContent, 'Loading recent work…');
  assert.equal(state.recentWorkGeneration, 1);
  assert.equal(state.matterListGeneration, 7, 'opening the short list never cancels the history list');
  reply.answer({ state: 'ok', chats });
  await loading;
  assert.deepEqual(asked, ['/api/work?limit=3&offset=0']);
  assert.deepEqual(list.children.map((row) => row.dataset.chatId), ['c3', 'c2', 'c1']);

  // The history list loads again meanwhile; a conversation of the short list that cannot be opened is still said, in its list.
  state.matterListGeneration += 1;
  await list.children[1].onclick();
  assert.deepEqual(opened, ['c2']);
  assert.equal(list.children[0].textContent, 'The chat could not be read: It is not there');

  // Closed: emptied.
  disclosure.open = false;
  await context.showRecentWork(disclosure);
  assert.equal(list.children.length, 0);
  assert.equal(list.textContent, '');
}

// A reply that comes after the list was closed paints nothing; nor does one overtaken by a later opening.
{
  const slow = later();
  replies.push(() => slow.promise);
  const disclosure = { open: true };
  const loading = context.showRecentWork(disclosure);
  disclosure.open = false;
  await context.showRecentWork(disclosure);
  slow.answer({ state: 'ok', chats });
  await loading;
  assert.equal(list.children.length, 0, 'a closed list stays empty');

  const first = later();
  const second = later();
  replies.push(() => first.promise, () => second.promise);
  const again = { open: true };
  const overtaken = context.showRecentWork(again);
  const latest = context.showRecentWork(again);
  second.answer({ state: 'ok', chats: chats.slice(0, 1) });
  await latest;
  first.answer({ state: 'ok', chats });
  await overtaken;
  assert.deepEqual(list.children.map((row) => row.dataset.chatId), ['c3'], 'only the latest opening paints');
}

// What the server could not give is said, in code's words.
{
  replies.push(() => Promise.resolve({ state: 'partial', chats: chats.slice(0, 1) }));
  await context.showRecentWork({ open: true });
  assert.equal(list.children[0].textContent, 'Some recent work could not be loaded.');
  assert.equal(list.children[1].dataset.chatId, 'c3');
  replies.push(() => Promise.resolve({ state: 'ok', chats: [] }));
  await context.showRecentWork({ open: true });
  assert.equal(list.textContent, 'No recent work yet.');
  replies.push(() => Promise.reject(new Error('offline')));
  await context.showRecentWork({ open: true });
  assert.equal(list.textContent, 'Recent work is unavailable. Open the full list to try again.');
}

// The Attach button: its short word shown, and its full description said to a screen reader and when pointed at (D333).
{
  const at = page.indexOf('id="plus-toggle"');
  const button = page.slice(page.lastIndexOf('<button', at), page.indexOf('</button>', at));
  const full = 'Attach documents, photos or recordings, or record a voice note';
  assert.match(button, new RegExp(`aria-label="${full}"`));
  assert.match(button, new RegExp(`title="${full}"`));
  assert.match(button, /<span>Attach<\/span>/, 'the word shown begins the name said, as WCAG label-in-name asks');
}

console.log('start_or_resume.mjs: the short list of recent work and the Attach button are as D333 decided');
