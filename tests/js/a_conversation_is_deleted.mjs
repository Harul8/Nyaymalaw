// Deleting a conversation from the page (plan AN.53, D241, piece 53h3b): the conversation's own Delete, asked first and naming
// it; Delete takes it out of the history at once and says how to put it back; Erase now erases it for good; Recently deleted
// lists what can still be put back and until when, and puts one back or erases it now, asking first. Where the server refuses,
// its own words are said and nothing else changes; where an erasure fails after the deletion, the page says it was deleted.
// Runs the actual functions of nm/app/app.js against offline stand-ins; the words are invented.
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
    Object.assign(this, { tag, children: [], attributes: {}, dataset: {}, textContent: '', title: '', className: '',
      disabled: false, open: false, listeners: {} });
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(kind, listener) { (this.listeners[kind] ||= []).push(listener); }
  click() { return Promise.all((this.listeners.click || []).map((listener) => listener())); }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

function refused(message, status, extra = {}) {
  return Object.assign(new Error(message), { status }, extra);
}

function aPage({ answers = {}, confirmed = true } = {}) {
  const elements = new Map();
  const seen = { calls: [], left: [], listed: [], asked: [] };
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag) },
    $: (id) => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); },
    api: async (path, options = {}) => {
      const asked = `${options.method || 'GET'} ${path}`;
      seen.calls.push(asked);
      const answer = answers[asked];
      if (answer instanceof Error) throw answer;
      return answer;
    },
    state: { turns: [] },
    activeIntent: { chatId: null },
    startMatter: () => seen.left.push('a new matter'),
    loadMatterList: () => seen.listed.push('the history read again'),
    window: { confirm: (words) => { seen.asked.push(words); return confirmed; } },
    setTimeout: () => 0,
    clearTimeout: () => {},
  });
  vm.runInContext(['historyTitle', 'shownChatId', 'threadTitle', 'deletedDay', 'askToDeleteChat', 'deleteChat',
    'showDeletedChats', 'changeDeletedChat'].map(fn).join(''), context);
  return { page: context, $: context.$, ...seen };
}

const FIRST = 'Please look at the dishonoured cheque and the demand notice the bank sent last week';
const DELETED = { state: 'deleted', chat_id: 'new_c1', ref: 'chat_r1', deleted_at: '2026-11-14T09:00:00+00:00',
  erased_after: '2026-12-14T09:00:00+00:00' };

// ------------------------------------------------------------------ the conversation's own Delete, asked first ---
{
  const { page, $ } = withAFirstMessage();
  assert.equal(page.threadTitle().length, 2, 'a heading and its Delete');
  const [, remove] = page.threadTitle();
  assert.equal(remove.textContent, 'Delete');
  assert.equal(remove.attributes['aria-label'], 'Delete this conversation');
  await remove.click();
  const dialog = $('delete-chat-dialog');
  assert.ok(dialog.open, 'Delete asks first');
  assert.equal(dialog.dataset.chatId, 'new_c1', 'known by the turn\'s progress before its answer names it');
  assert.equal($('delete-chat-named').textContent, '“Please look at the dishonoured cheque and the demand notice…”',
    'an untitled conversation is named by its first message\'s first words');
  assert.ok($('delete-chat-confirm').focused);

  page.state.chatTitle = { chatId: 'new_c1', text: 'Asha Rao v. Greenfield Builders' };
  await page.threadTitle()[1].click();
  assert.equal($('delete-chat-named').textContent, '“Asha Rao v. Greenfield Builders”', 'a named one by its name');
}
{
  const { page } = aPage();
  assert.equal(page.threadTitle().length, 0, 'nothing before the first message is sent');
  page.state.turns = [{ turnId: 't1' }];
  assert.equal(page.threadTitle().length, 1, 'no Delete until the conversation is known');
}

function withAFirstMessage(options) {
  const made = aPage(options);
  made.page.state.turns = [{ turnId: 't1', chatId: 'new_c1', brief: FIRST }];
  return made;
}

async function asked(made) {
  await made.page.threadTitle()[1].click();
  return made.$('delete-chat-dialog');
}

// ----------------------------------------------------------------------------------- Delete, and Erase now ---
{
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': DELETED } });
  const dialog = await asked(made);
  await made.page.deleteChat();
  assert.deepEqual(made.calls, ['DELETE /api/chats/new_c1']);
  assert.ok(!dialog.open && dialog.dataset.chatId === undefined);
  assert.deepEqual(made.left, ['a new matter'], 'the page leaves the conversation it deleted');
  assert.deepEqual(made.listed, ['the history read again'], 'and the history no longer has it');
  assert.equal(made.$('deleted-said').textContent,
    'The conversation was deleted. For 30 days you can put it back from Recently deleted, in the conversation history.');
}
{
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': DELETED,
    'POST /api/deleted-chats/chat_r1/erase': { state: 'erased', chat_id: 'new_c1', left: 0 } } });
  await asked(made);
  await made.page.deleteChat({ erase: true });
  assert.deepEqual(made.calls, ['DELETE /api/chats/new_c1', 'POST /api/deleted-chats/chat_r1/erase'],
    'Erase now deletes, then erases what it deleted by its own reference');
  assert.equal(made.$('deleted-said').textContent, 'The conversation was erased.');
  assert.deepEqual(made.left, ['a new matter']);
}
{
  // NM is working on it: the server refuses, in its own words, and nothing on the page changes.
  const busy = 'NM is working on this conversation. Stop it, or let it finish, and then delete it.';  // the server's words
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': refused(busy, 409) } });
  const dialog = await asked(made);
  await made.page.deleteChat();
  assert.ok(dialog.open && dialog.dataset.chatId === 'new_c1', 'the question stays, to be answered again');
  assert.equal(made.$('delete-chat-status').textContent, busy);
  assert.ok(!made.$('delete-chat-confirm').disabled && !made.$('delete-chat-erase').disabled);
  assert.deepEqual([made.left, made.listed, made.$('deleted-said').textContent], [[], [], '']);
}
{
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': refused('The store refused.', 503) } });
  await asked(made);
  await made.page.deleteChat({ erase: true });
  assert.equal(made.$('delete-chat-status').textContent, 'It could not be erased: The store refused.');
  assert.deepEqual(made.calls, ['DELETE /api/chats/new_c1'], 'nothing is erased that was not deleted');
}
{
  // Deleted, but the erasure failed: the page says it WAS deleted, and where to erase it from.
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': DELETED,
    'POST /api/deleted-chats/chat_r1/erase': refused('Its key could not be destroyed.', 503) } });
  const dialog = await asked(made);
  await made.page.deleteChat({ erase: true });
  assert.ok(!dialog.open);
  assert.deepEqual(made.left, ['a new matter'], 'it has left the history all the same');
  assert.equal(made.$('deleted-said').textContent, 'The conversation was deleted, but it could not be erased now: Its key could '
    + 'not be destroyed. You can erase it, or put it back, from Recently deleted, in the conversation history.');
}
{
  // Another conversation is open by the time it is deleted (the question answered late): the page stays where it is.
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': DELETED } });
  await asked(made);
  made.page.activeIntent = { chatId: 'new_c9' };
  await made.page.deleteChat();
  assert.deepEqual(made.left, []);
  assert.deepEqual(made.listed, ['the history read again']);
}
{
  // The sign-in changed while it was being deleted: nothing is said here for the session that ended.
  const made = withAFirstMessage({ answers: { 'DELETE /api/chats/new_c1': refused('changed', 0, { obsolete: true }) } });
  await asked(made);
  await made.page.deleteChat();
  assert.deepEqual([made.left, made.listed, made.$('deleted-said').textContent], [[], [], '']);
}

// --------------------------------------------------------------------------------------- Recently deleted ---
const LISTED = { deleted: [
  { ref: 'chat_r1', chat_id: 'new_c1', title: 'Asha Rao v. Greenfield Builders', preview: FIRST,
    deleted_at: '2026-11-14T09:00:00+00:00', erased_after: '2026-12-14T09:00:00+00:00' },
  { ref: 'chat_r2', chat_id: 'new_c2', title: null, preview: 'Draft a reply to the notice',
    deleted_at: '2026-11-10T09:00:00+00:00', erased_after: '2026-12-10T09:00:00+00:00' },
] };
{
  const made = aPage({ answers: { 'GET /api/deleted-chats': LISTED } });
  await made.page.showDeletedChats();
  const rows = made.$('deleted-chats-list').children;
  assert.equal(rows.length, 2);
  const [name, when, back, erase] = rows[0].children;
  assert.equal(rows[0].dataset.deletedChatId, 'new_c1');
  assert.equal(name.textContent, 'Asha Rao v. Greenfield Builders');
  assert.equal(name.title, FIRST, 'its first words on hover, to tell like-named ones apart');
  assert.equal(when.textContent, 'Deleted 14 Nov 2026 · erased for good after 14 Dec 2026');
  assert.deepEqual([back.textContent, erase.textContent], ['Put back', 'Erase now']);
  assert.equal(back.attributes['aria-label'], 'Put back: Asha Rao v. Greenfield Builders');
  assert.equal(rows[1].children[0].textContent, 'Draft a reply to the notice', 'an untitled one by its first words');
  assert.equal(made.$('deleted-chats-status').textContent, '');
}
{
  const made = aPage({ answers: { 'GET /api/deleted-chats': { deleted: [] } } });
  await made.page.showDeletedChats();
  assert.equal(made.$('deleted-chats-status').textContent, 'Nothing you deleted is waiting to be erased.');
}
{
  const made = aPage({ answers: { 'GET /api/deleted-chats': refused('The store refused.', 503) } });
  await made.page.showDeletedChats();
  assert.equal(made.$('deleted-chats-status').textContent, 'What you deleted could not be read: The store refused. Nothing was changed.',
    'the server\'s words, said once as a sentence');
}
{
  // Put back: sent, the history read again, and the list read again saying it is back.
  const made = aPage({ answers: { 'GET /api/deleted-chats': LISTED,
    'POST /api/deleted-chats/chat_r1/put-back': { state: 'put_back', chat_id: 'new_c1' } } });
  await made.page.showDeletedChats();
  await made.$('deleted-chats-list').children[0].children[2].click();
  assert.deepEqual(made.calls, ['GET /api/deleted-chats', 'POST /api/deleted-chats/chat_r1/put-back', 'GET /api/deleted-chats']);
  assert.deepEqual(made.listed, ['the history read again']);
  assert.equal(made.$('deleted-chats-status').textContent, '“Asha Rao v. Greenfield Builders” is back in your history.');
  assert.deepEqual(made.asked, [], 'putting back asks nothing');
}
{
  // Erase now asks first; declined, nothing is sent.
  const made = aPage({ answers: { 'GET /api/deleted-chats': LISTED }, confirmed: false });
  await made.page.showDeletedChats();
  await made.$('deleted-chats-list').children[1].children[3].click();
  assert.deepEqual(made.asked, ['Erase “Draft a reply to the notice” now? This cannot be undone.']);
  assert.deepEqual(made.calls, ['GET /api/deleted-chats']);
}
{
  const made = aPage({ answers: { 'GET /api/deleted-chats': LISTED,
    'POST /api/deleted-chats/chat_r2/erase': { state: 'erased', chat_id: 'new_c2', left: 0 } } });
  await made.page.showDeletedChats();
  await made.$('deleted-chats-list').children[1].children[3].click();
  assert.deepEqual(made.calls, ['GET /api/deleted-chats', 'POST /api/deleted-chats/chat_r2/erase', 'GET /api/deleted-chats']);
  assert.equal(made.$('deleted-chats-status').textContent, '“Draft a reply to the notice” was erased.');
}
{
  // A refused Put back says so and changes nothing else.
  const made = aPage({ answers: { 'GET /api/deleted-chats': LISTED,
    'POST /api/deleted-chats/chat_r1/put-back': refused('That conversation is no longer there to put back.', 404) } });
  await made.page.showDeletedChats();
  await made.$('deleted-chats-list').children[0].children[2].click();
  assert.equal(made.$('deleted-chats-status').textContent, 'It could not be put back: That conversation is no longer there to put back.');
  assert.deepEqual(made.listed, []);
  assert.deepEqual(made.calls, ['GET /api/deleted-chats', 'POST /api/deleted-chats/chat_r1/put-back']);
}

console.log('a_conversation_is_deleted.mjs: ok');
