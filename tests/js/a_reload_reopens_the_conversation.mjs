// A RELOAD REOPENS THE CONVERSATION IN PROGRESS (plan AN.48, D300 and D305; the owner, 18 Nov 2026: "yes, as is from where it
// stopped"). Every load of the page opened a new matter, because which conversation was open lived only in the page's memory. The
// conversation shown is now named in the page's address after a '#'; a load or a sign-in whose address names one reopens it through
// the history's own reading, and one that cannot be opened opens a new matter that says so. A new matter's unsent words come back
// from the device too. Runs the shipped functions against offline stand-ins for the browser's address, the screen and the server;
// identifiers invented. Not a browser check.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const between = (from, to) => {
  const start = app.indexOf(from);
  const end = app.indexOf(to, start + from.length);
  assert.ok(start >= 0 && end > start, `the shipped script must hold: ${from}`);
  return app.slice(start, end);
};
const block = between('/* ------------------------------------------------- the conversation in the address --- */',
  '/* ------------------------------------------- the end of the conversation in the address --- */');
const takeBack = between('async function takeBackSavedWords(chatId) {', '\n}\n') + '\n}\n';

function page({ hash = '', view = 'opening' } = {}) {
  const made = { started: [], tookBack: [], replaced: [] };
  const element = () => ({ dataset: {}, children: [], readOnly: false, textContent: '',
    replaceChildren(...kids) { this.children = kids; }, prepend(kid) { this.children.unshift(kid); } });
  const elements = new Map();
  const $ = (id) => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
  $('pane-advise').dataset.view = view;
  const location = { hash, pathname: '/app', search: '' };
  const context = {
    window: { location }, decodeURIComponent, encodeURIComponent, String, Error,
    history: { replaceState(_state, _title, address) { made.replaced.push(address); location.hash = address.replace(/^[^#]*/, ''); } },
    state: { sessionGeneration: 1, reopening: null }, activeIntent: null, $,
    stateBlock: (kind, text) => ({ kind, text }),
    setWorkView: (next) => { $('pane-advise').dataset.view = next; },
    shownChatId: () => (context.activeIntent && context.activeIntent.chatId) || null,
    takeBackSavedWords: (chatId) => { made.tookBack.push(chatId); },
    restorePendingChat: async () => {},
  };
  context.startMatter = () => {
    made.started.push('a new matter');
    context.activeIntent = { chatId: null };
    $('pane-advise').dataset.view = 'opening';
    context.markAddress();
  };
  vm.createContext(context);
  vm.runInContext(`${block}\nthis.addressedChat = addressedChat; this.markAddress = markAddress; this.forgetAddress = forgetAddress;
    this.reopenAddressed = reopenAddressed;`, context);
  return { context, made, $, location };
}

// What the address names: a conversation after '#chat=', and nothing else - a reset link's mark, #admin, an empty address.
{
  const { context, location } = page({ hash: '#chat=new_0a1b2c' });
  assert.equal(context.addressedChat(), 'new_0a1b2c');
  for (const other of ['', '#admin', '#register', '#reset=abc', '#chat=', '#chat=a#b']) {
    location.hash = other;
    assert.equal(context.addressedChat(), null, other);
  }
  location.hash = `#chat=${encodeURIComponent('an id/with space')}`;
  assert.equal(context.addressedChat(), 'an id/with space', 'an identifier is carried whole');
}

// The address follows what is shown, and leaves alone what is not its own.
{
  const { context, made, $, location } = page();
  context.activeIntent = { chatId: 'new_0a1b2c' };
  context.markAddress();
  assert.equal(location.hash, '#chat=new_0a1b2c', 'a conversation shown is named');
  assert.equal(made.replaced.at(-1), '/app#chat=new_0a1b2c', 'in place: no new page, no step in the browser history');
  context.markAddress();
  assert.equal(made.replaced.length, 1, 'named once');
  $('pane-advise').dataset.view = 'list';
  context.markAddress();
  assert.equal(location.hash, '', 'the history shown names none');
  $('pane-advise').dataset.view = 'opening';
  context.activeIntent = { chatId: null };
  location.hash = '#admin';
  context.markAddress();
  assert.equal(location.hash, '#admin', 'a mark that names no conversation is never touched');
  location.hash = '#chat=new_0a1b2c';
  context.state.reopening = 'new_0a1b2c';
  context.markAddress();
  assert.equal(location.hash, '#chat=new_0a1b2c', 'kept while the conversation it names is being reopened');
  context.state.reopening = null;
  context.forgetAddress();
  assert.equal(location.hash, '', 'Sign out takes it out');
}

// A conversation the address names is reopened from where it stopped, through the history's own reading.
{
  const { context, made, $, location } = page({ hash: '#chat=new_0a1b2c' });
  const asked = [];
  let shownMeanwhile = null;
  context.restorePendingChat = async (chatId) => {
    asked.push(chatId);
    shownMeanwhile = { thread: $('thread').children.map((kid) => kid.text), readOnly: $('message').readOnly };
    context.markAddress();   // a repaint while it opens leaves the address as it is
    context.activeIntent = { chatId };
  };
  await context.reopenAddressed('new_0a1b2c');
  assert.deepEqual(asked, ['new_0a1b2c']);
  assert.deepEqual(shownMeanwhile, { thread: ['Opening the conversation…'], readOnly: true },
    'it says it is opening it, and the box waits for it');
  assert.equal($('message').readOnly, false);
  assert.equal(location.hash, '#chat=new_0a1b2c');
  assert.deepEqual(made.started, [], 'no new matter');
  assert.equal(context.state.reopening, null);
}

// One that cannot be opened opens a new matter, which says so and takes back the new matter's own words.
{
  const { context, made, $, location } = page({ hash: '#chat=new_gone' });
  context.restorePendingChat = async () => { throw new Error('Conversation not available.'); };
  await context.reopenAddressed('new_gone');
  assert.deepEqual(made.started, ['a new matter']);
  assert.deepEqual(made.tookBack, [null]);
  assert.equal(location.hash, '', 'the address no longer names it');
  const [note] = $('thread').children;
  assert.equal(note.kind, 'unbuildable');
  assert.equal(note.text, 'The conversation this page had open could not be opened again: Conversation not available. It is not '
    + 'changed. Open it from the conversation history.');
  assert.equal($('message').readOnly, false);
}

// Nothing is opened over where the advocate went meanwhile, nor after the session changed or the reply was for another session.
for (const meanwhile of ['the history', 'a new matter', 'another session', 'an obsolete reply']) {
  const { context, made } = page({ hash: '#chat=new_gone' });
  context.restorePendingChat = async () => {
    if (meanwhile === 'the history') context.$('pane-advise').dataset.view = 'list';
    if (meanwhile === 'a new matter') context.activeIntent = { chatId: null };
    if (meanwhile === 'another session') context.state.sessionGeneration += 1;
    const error = new Error('The session changed before this response arrived.');
    if (meanwhile === 'an obsolete reply') error.obsolete = true;
    throw error;
  };
  await context.reopenAddressed('new_gone');
  assert.deepEqual(made.started, [], meanwhile);
  assert.equal(context.$('thread').children.length, 1, `${meanwhile}: only the opening line, nothing said over it`);
}

// The page calls them where it should: a load or sign-in reads the address; every view change keeps it; Sign out forgets it.
{
  const shown = between('function showApplication(advocate, workspace, professionalApproval) {', '\n}\n');
  assert.match(shown, /const addressed = addressedChat\(\);\n {2}if \(addressed\) reopenAddressed\(addressed\);\n {2}else startMatter\(\);/);
  assert.match(shown, /draftUnlock = unlockDrafts\(\);\n[^\n]*\n {2}if \(!addressed\) takeBackSavedWords\(null\);/);
  assert.ok(!/\n {2}startMatter\(\);/.test(shown), 'a sign-in no longer opens a new matter whatever the address says');
  assert.match(between('function updateWorkspace() {', '\n}\n'), /\n {2}markAddress\(\);$/);
  assert.match(between('async function signOut() {', '\n}\n'), /clearPrivileged\(\);\n {2}forgetAddress\(\);/);
}

// A new matter's unsent words, kept on the device as they are typed, come back with it; never a sent message's, nor another's.
{
  const kept = [
    { savedAt: 3, intent: { advocate: 'a@example.test', workspace: 'w', chatId: null, text: 'The words being typed', pending: [] } },
    { savedAt: 9, intent: { advocate: 'a@example.test', workspace: 'w', chatId: null, text: '', pending: [{}] } },
    { savedAt: 8, intent: { advocate: 'a@example.test', workspace: 'w', chatId: 'new_other', text: 'Another conversation', pending: [] } },
    { savedAt: 7, intent: { advocate: 'a@example.test', workspace: 'w', matterId: 'm_old', text: 'An earlier matter', pending: [] } },
    { savedAt: 6, intent: { advocate: 'b@example.test', workspace: 'w', chatId: null, text: 'Another advocate', pending: [] } },
  ];
  const restored = [];
  const context = vm.createContext({
    String, state: { sessionGeneration: 1, advocate: 'a@example.test', workspace: 'w' },
    activeIntent: { chatId: null, text: '', pending: [] }, draftUnlock: Promise.resolve(),
    draftVault: { key: 'k', list: async () => kept },
    restoreIntent: () => restored.push(context.activeIntent.text), paintSend() {}, showDraftRestored() {},
  });
  vm.runInContext(`${takeBack}\nthis.takeBackSavedWords = takeBackSavedWords;`, context);
  await context.takeBackSavedWords(null);
  assert.deepEqual(restored, ['The words being typed']);
}

console.log('a reload reopens the conversation: ok');
