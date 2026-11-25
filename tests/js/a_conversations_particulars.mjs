// A conversation's particulars from the page (plan AN.55, piece 55d3; D256, D332, D355): Particulars beside Rename under the
// heading opens a dialog that reads what is kept and what NM proposes; each proposal says where it came from and, pressed, only
// fills its box; Save sends every box as written; the history row shows them. Where the server refuses, its own words are said
// and nothing else changes; a reading that comes back for a conversation no longer asked about is not shown. Runs the actual
// functions of nm/app/app.js against offline stand-ins; the words are invented.
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
function constant(name) {
  const at = app.indexOf(`\nconst ${name} =`);
  assert.ok(at >= 0, `the page has ${name}`);
  return app.slice(at, app.indexOf(';\n', at) + 2);
}

class Element {
  constructor(tag) {
    Object.assign(this, { tag, children: [], attributes: {}, dataset: {}, textContent: '', title: '', className: '', value: '',
      disabled: false, open: false, listeners: {} });
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); }
  replaceChildren(...nodes) { this.children = nodes; }
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

const READ = { chat_id: 'c1', particulars: { court: 'City Civil Court, Mumbai' }, proposed: {
  client: [{ value: 'Asha Rao', said: 'NM took this party as your client' },
    { value: 'Greenfield Builders', said: "A party in NM's understanding of the matter" }],
  case_number: [{ value: 'Consumer complaint no. 41 of 2025', said: 'A proceeding the papers name' }] } };

function aPage(answers) {
  const elements = new Map();
  const seen = { calls: [], bodies: [], listed: 0 };
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag) },
    $: (id) => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); },
    api: async (path, options = {}) => {
      const asked = `${options.method || 'GET'} ${path}`;
      seen.calls.push(asked);
      if (options.body) seen.bodies.push(JSON.parse(options.body));
      const answer = typeof answers[asked] === 'function' ? await answers[asked]() : answers[asked];
      if (answer instanceof Error) throw answer;
      return answer;
    },
    state: { turns: [{ turnId: 't1', chatId: 'c1' }] },
    activeIntent: { chatId: 'c1' },
    loadMatterList: () => { seen.listed += 1; },
    askToRenameChat: () => {},
    askToDeleteChat: () => {},
    historyWhen: () => ' · 4 Nov',
    restorePendingChat: async () => {},
  });
  vm.runInContext([constant('PARTICULAR_FIELDS'), constant('PROPOSED_FIELDS'),
    ...['shownChatId', 'threadTitle', 'askForParticulars', 'particularProposal', 'saveParticulars', 'historyTitle',
      'particularsLine', 'historyChatRow'].map(fn)].join(''), context);
  return { page: context, $: context.$, seen };
}

// ---------------------------------------- the dialog reads what is kept and what NM proposes, where it came from ---
{
  const { page, $, seen } = aPage({ 'GET /api/chats/c1/particulars': READ,
    'PUT /api/chats/c1/particulars': { state: 'saved', chat_id: 'c1', particulars: {} } });
  const actions = page.threadTitle()[1];
  const particulars = actions.children[1];
  assert.equal(particulars.textContent, 'Particulars');
  await particulars.click();
  const dialog = $('particulars-dialog');
  assert.ok(dialog.open && dialog.dataset.chatId === 'c1');
  assert.deepEqual(seen.calls, ['GET /api/chats/c1/particulars']);
  assert.equal($('particulars-court').value, 'City Civil Court, Mumbai');
  assert.equal($('particulars-client').value, '', 'a proposal is never filled in by itself');
  assert.ok(['client', 'court', 'case_number', 'next_date'].every((field) => !$(`particulars-${field}`).disabled));
  const offered = $('particulars-client-proposed').children;
  assert.deepEqual(offered.map((button) => button.children.map((part) => part.textContent)), [
    ['Asha Rao', 'NM took this party as your client'],
    ['Greenfield Builders', "A party in NM's understanding of the matter"]]);
  assert.equal(offered[0].attributes['aria-label'], 'Fill the box with Asha Rao (NM took this party as your client)');
  assert.equal($('particulars-case_number-proposed').children.length, 1);
  assert.equal($('particulars-status').textContent, '');
  assert.ok($('particulars-client').focused);

  await offered[0].click();
  assert.equal($('particulars-client').value, 'Asha Rao', 'pressed, it fills its box');
  assert.equal(seen.calls.length, 1, 'and saves nothing');
  $('particulars-next_date').value = '2026-12-04';
  await page.saveParticulars();
  assert.deepEqual(seen.calls.at(-1), 'PUT /api/chats/c1/particulars');
  assert.deepEqual(seen.bodies, [{ client: 'Asha Rao', court: 'City Civil Court, Mumbai', case_number: '', next_date: '2026-12-04' }],
    'every box goes as written; the server keeps what is given');
  assert.ok(!dialog.open && dialog.dataset.chatId === undefined);
  assert.equal(seen.listed, 1, 'the history is read again');
}

// --------------------------------------------------- the server's own words where it refuses; nothing else ---
for (const [error, said] of [
  [refused('The next date is not a calendar date.', 422), 'The next date is not a calendar date.'],
  [refused('NM is working on this conversation. Change its particulars once NM has finished or stopped.', 409),
    'NM is working on this conversation. Change its particulars once NM has finished or stopped.'],
  [refused('The server could not be reached.', 503), 'The particulars could not be saved: The server could not be reached.'],
]) {
  const { page, $, seen } = aPage({ 'GET /api/chats/c1/particulars': READ, 'PUT /api/chats/c1/particulars': error });
  await page.askForParticulars('c1');
  await page.saveParticulars();
  assert.ok($('particulars-dialog').open);
  assert.equal($('particulars-status').textContent, said);
  assert.equal($('particulars-save').disabled, false);
  assert.equal(seen.listed, 0);
}

// ------------------------------------------ a reading that cannot be had is said; one for another is not shown ---
{
  const { page, $ } = aPage({ 'GET /api/chats/c1/particulars': refused('Conversation not available.', 404) });
  await page.askForParticulars('c1');
  assert.equal($('particulars-status').textContent, 'The particulars could not be read: Conversation not available.');
  assert.equal($('particulars-save').disabled, true, 'nothing can be saved over particulars that were not read');
}
{
  let made;
  made = aPage({ 'GET /api/chats/c1/particulars': () => { made.$('particulars-dialog').dataset.chatId = 'c2'; return READ; } });
  await made.page.askForParticulars('c1');
  assert.equal(made.$('particulars-court').value, '', 'the reading of another conversation is not shown');
  assert.equal(made.$('particulars-client-proposed').children.length, 0);
}

// ----------------------------------------------------------------------------- the history row shows them ---
{
  const { page } = aPage({});
  const row = page.historyChatRow({ chat_id: 'c1', title: 'Mehta lease renewal', turn_count: 2,
    particulars: { client: 'Asha Rao', court: 'City Civil Court, Mumbai', case_number: 'CC 41/2025', next_date: '2026-12-04' } }, 1, 1);
  const line = row.children.find((child) => child.className === 'hint particulars-line');
  assert.equal(line.textContent, 'Client: Asha Rao · City Civil Court, Mumbai · Case: CC 41/2025 · Next date: 4 Dec 2026');
  assert.equal(page.particularsLine({ court: 'High Court of Bombay' }), 'High Court of Bombay');
  assert.equal(page.particularsLine({ next_date: 'not a date' }), '');
  assert.equal(page.particularsLine(undefined), '');
  const plain = page.historyChatRow({ chat_id: 'c2', title: 'Another', turn_count: 1 }, 1, 1);
  assert.ok(!plain.children.some((child) => child.className === 'hint particulars-line'), 'none where none was written');
}

console.log('a_conversations_particulars.mjs: ok');
