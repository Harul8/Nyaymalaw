// Renaming a conversation from the page (plan AN.55, piece 55c3; D255, D355): Rename beside Delete under the conversation's
// heading opens a dialog holding the name shown; Save sends the advocate's words as they are and the server keeps them; the
// heading shows the new name at once and the history is read again. Where the server refuses - a name it cannot keep, NM at work
// on the conversation - its own words are said, the dialog stays and nothing else changes. Runs the actual functions of
// nm/app/app.js against offline stand-ins; the words are invented.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
function fn(name) {
  let at = app.indexOf(`\nfunction ${name}(`);
  if (at < 0) at = app.indexOf(`\nasync function ${name}(`);
  assert.ok(at >= 0, `the page has ${name}`);
  return app.slice(at, app.indexOf('\n}\n', at) + 3);
}

class Element {
  constructor(tag) {
    Object.assign(this, { tag, children: [], attributes: {}, dataset: {}, textContent: '', title: '', className: '', value: '',
      disabled: false, open: false, listeners: {} });
  }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(kind, listener) { (this.listeners[kind] ||= []).push(listener); }
  click() { return Promise.all((this.listeners.click || []).map((listener) => listener())); }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

function refused(message, status) {
  return Object.assign(new Error(message), { status });
}

function aPage(answer) {
  const elements = new Map();
  const seen = { calls: [], bodies: [], painted: 0, listed: 0 };
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag) },
    $: (id) => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); },
    api: async (path, options = {}) => {
      seen.calls.push(`${options.method || 'GET'} ${path}`);
      seen.bodies.push(options.body && JSON.parse(options.body));
      assert.equal(options.headers['content-type'], 'application/json');
      if (answer instanceof Error) throw answer;
      return answer;
    },
    state: { turns: [{ turnId: 't1', chatId: 'c1', brief: 'A first message' }], chatTitle: { chatId: 'c1', text: 'Lease of a shop' } },
    activeIntent: { chatId: 'c1' },
    repaint: () => { seen.painted += 1; },
    loadMatterList: () => { seen.listed += 1; },
    askToDeleteChat: () => {},
    askForParticulars: () => {},
  });
  vm.runInContext(['shownChatId', 'threadTitle', 'askToRenameChat', 'renameChat'].map(fn).join(''), context);
  return { page: context, $: context.$, seen };
}

// ------------------------------------------------------------- Rename beside Delete, holding the name shown ---
{
  const { page, $, seen } = aPage({ state: 'saved', chat_id: 'c1', title: 'Mehta lease renewal', named: true });
  const [heading, actions] = page.threadTitle();
  assert.equal(heading.textContent, 'Lease of a shop');
  assert.deepEqual(actions.children.map((button) => button.textContent), ['Rename', 'Particulars', 'Delete']);
  const rename = actions.children[0];
  assert.equal(rename.attributes['aria-label'], 'Rename this conversation');
  await rename.click();
  const dialog = $('rename-chat-dialog');
  assert.ok(dialog.open && dialog.dataset.chatId === 'c1');
  assert.equal($('rename-chat-name').value, 'Lease of a shop', 'it opens on the name shown');
  assert.ok($('rename-chat-name').focused);

  $('rename-chat-name').value = '  Mehta  lease renewal ';
  await page.renameChat();
  assert.deepEqual(seen.calls, ['PUT /api/chats/c1/name']);
  assert.deepEqual(seen.bodies, [{ name: '  Mehta  lease renewal ' }], 'the advocate\'s words go as they are; the server keeps them');
  assert.ok(!dialog.open && dialog.dataset.chatId === undefined);
  assert.deepEqual({ ...page.state.chatTitle }, { chatId: 'c1', text: 'Mehta lease renewal' }, 'the heading shows the name the server kept');
  assert.equal(seen.painted, 1);
  assert.equal(seen.listed, 1, 'the history is read again');
}

// ----------------------------------------------- an empty name: NM's title, as the server says, or none yet ---
{
  const { page, $ } = aPage({ state: 'saved', chat_id: 'c1', title: null, named: false });
  await page.threadTitle()[1].children[0].click();
  $('rename-chat-name').value = '';
  await page.renameChat();
  assert.deepEqual({ ...page.state.chatTitle }, { chatId: 'c1', text: null });
}

// ------------------------------------------------------- the server's own words where it refuses; nothing else ---
for (const [error, said] of [
  [refused('The name has 121 characters; at most 120 are kept.', 422), 'The name has 121 characters; at most 120 are kept.'],
  [refused('NM is working on this conversation. Rename it once NM has finished or stopped.', 409),
    'NM is working on this conversation. Rename it once NM has finished or stopped.'],
  [refused('The server could not be reached.', 503), 'It could not be renamed: The server could not be reached.'],
]) {
  const { page, $, seen } = aPage(error);
  await page.threadTitle()[1].children[0].click();
  await page.renameChat();
  const dialog = $('rename-chat-dialog');
  assert.ok(dialog.open, 'the dialog stays');
  assert.equal($('rename-chat-status').textContent, said);
  assert.equal($('rename-chat-save').disabled, false, 'Save can be pressed again');
  assert.deepEqual({ ...page.state.chatTitle }, { chatId: 'c1', text: 'Lease of a shop' }, 'the heading is as it was');
  assert.equal(seen.listed + seen.painted, 0);
}

// ------------------------------------------- another conversation renamed: the one shown keeps its heading ---
{
  const { page, $ } = aPage({ state: 'saved', chat_id: 'c2', title: 'Another name', named: true });
  page.askToRenameChat('c2', 'Old name');
  await page.renameChat();
  assert.ok(!$('rename-chat-dialog').open);
  assert.deepEqual({ ...page.state.chatTitle }, { chatId: 'c1', text: 'Lease of a shop' });
}

console.log('a_conversation_is_renamed.mjs: ok');
