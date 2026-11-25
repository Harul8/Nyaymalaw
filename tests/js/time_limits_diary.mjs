// THE DIARY OF TIME LIMITS (plan AN.55, piece 55e2; D257, D332, D355(f)): Time limits, beside Recently deleted, opens the
// diary the server reads: code's own note first; then the time limits still to come and those passed, each with its last day,
// the days from today, what it is, its provision, how it stood when worked out and the conversation it is in, which opens from
// there; then those not worked out, with why. Where some conversations could not be read the page says so above the rest, and
// where the diary itself cannot be read it says that is a failure to read it, never that there are none. Runs the actual
// functions of nm/app/app.js against offline stand-ins for the DOM and the network; the words are invented; not browser QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const start = app.indexOf('// THE DIARY OF TIME LIMITS');
const end = app.indexOf('async function openDeletedChats() {', start);
assert.ok(start >= 0 && end > start, 'the diary must be shipped');
const titled = app.indexOf('\nfunction historyTitle(');
assert.ok(titled >= 0, 'the page has historyTitle');
const source = app.slice(titled, app.indexOf('\n}\n', titled) + 3) + app.slice(start, end);
assert.match(app, /\$\('time-limits-open'\)\.addEventListener\('click', \(\) => openTimeLimits\(\)\);/,
  'Time limits opens the diary');
const html = readFileSync(new URL('../../nm/app/index.html', import.meta.url), 'utf8');
assert.match(html, /id="deleted-chats-open"[^\n]*\n[^\n]*\n\s*<button type="button" id="time-limits-open"/,
  'Time limits is beside Recently deleted');

class Element {
  constructor(tag) {
    Object.assign(this, { tag, children: [], attributes: {}, listeners: {}, className: '', open: false, _text: '' });
  }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  set textContent(value) { this.children = []; this._text = String(value); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(kind, listener) { (this.listeners[kind] ||= []).push(listener); }
  click() { return Promise.all((this.listeners.click || []).map((listener) => listener())); }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

function aPage(answer, { restored = () => Promise.resolve() } = {}) {
  const elements = new Map();
  const seen = { calls: [], opened: [] };
  const context = vm.createContext({
    Date, Array, Number, String,
    document: { createElement: (tag) => new Element(tag) },
    $: (id) => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); },
    api: async (path) => {
      seen.calls.push(path);
      if (answer instanceof Error) throw answer;
      return answer;
    },
    stateBlock: (kind, text) => { const block = new Element('div'); block.className = `state ${kind}`; block.textContent = text; return block; },
    restorePendingChat: (chatId) => { seen.opened.push(chatId); return restored(chatId); },
  });
  vm.runInContext(source, context);
  return { page: context, $: context.$, ...seen };
}

const day = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN',
  { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
const SAID = 'These are the last days NM worked out in each conversation\'s latest answer that worked any out. It is not a court diary.';
const about = (n) => ({ chat_id: `chat-${n}`, title: `Matter ${n}`, preview: 'An invented first message' });
const limit = (n, what, lastDay, days, stood = 'open', extra = {}) => ({ ...about(n), what, provision: 'Article 54',
  act: 'The Limitation Act, 1963', last_day: lastDay, stood, taken: stood === 'in_time', worked_on: '2026-11-01',
  days_from_today: days, ...extra });
const DIARY = {
  state: 'ok', today: '2026-11-25', said: SAID, unavailable: [],
  coming: [limit(1, 'Reply to the notice', '2026-11-28', 3, 'in_time'), limit(2, 'Complaint on the cheque', '2026-11-26', 1)],
  passed: [limit(1, 'Notice before suit', '2026-11-20', -5, 'expired')],
  not_worked: [{ ...about(3), what: null, why: 'the time limits could not be worked out' },
    { ...about(1), what: 'Appeal against the decree', why: 'The date of the decree is not given.' }],
};
const settle = () => new Promise((resolve) => setImmediate(resolve));

// ------------------------------------------------------------- the diary, code's note first, in its sections ---
{
  const { page, $, calls } = aPage(DIARY);
  await page.openTimeLimits();
  assert.deepEqual(calls, ['/api/time-limits']);
  assert.equal($('time-limits-dialog').open, true);
  assert.equal($('time-limits-said').textContent, SAID, "code's own note, as the server says it");
  assert.equal($('time-limits-status').textContent, '');
  const shown = $('time-limits-list').children;
  assert.deepEqual(shown.filter((node) => node.tag === 'h3').map((node) => node.textContent),
    ['Still to come', 'Passed', 'Not worked out']);
  const [reply, cheque] = shown[1].children;
  assert.deepEqual(reply.children.map((node) => node.textContent), [
    `${day('2026-11-28')} · in 3 days`,
    'Reply to the notice — Article 54, The Limitation Act, 1963',
    `The step was taken in time · worked out on ${day('2026-11-01')}`,
    'Matter 1']);
  assert.equal(cheque.children[0].textContent, `${day('2026-11-26')} · tomorrow`);
  assert.equal(cheque.children[2].textContent, `Still open when worked out · worked out on ${day('2026-11-01')}`);
  const [passed] = shown[3].children;
  assert.equal(passed.children[0].textContent, `${day('2026-11-20')} · 5 days ago`);
  assert.equal(passed.children[2].textContent, `Already passed when worked out · worked out on ${day('2026-11-01')}`);
  const [failed, appeal] = shown[5].children;
  assert.deepEqual(failed.children.map((node) => node.textContent),
    ['Its time limits', 'the time limits could not be worked out', 'Matter 3']);
  assert.deepEqual(appeal.children.map((node) => node.textContent),
    ['Appeal against the decree', 'The date of the decree is not given.', 'Matter 1']);
  assert.equal(reply.children[3].attributes['aria-label'], 'Open conversation: Matter 1');
}

// ------------------------------------------------------------------------------ the days said in words ---
{
  const { page } = aPage(DIARY);
  assert.deepEqual([0, 1, -1, 12, -40].map((days) => page.daysSaid(days)),
    ['today', 'tomorrow', 'yesterday', 'in 12 days', '40 days ago']);
  assert.equal(page.limitDay('not a day'), '', 'a day that cannot be read is not shown as one');
}

// ------------------------------------------------- a conversation opens from the diary, which then closes ---
{
  const { page, $, opened } = aPage(DIARY);
  await page.openTimeLimits();
  await $('time-limits-list').children[1].children[1].children[3].click();
  assert.deepEqual(opened, ['chat-2']);
  assert.equal($('time-limits-dialog').open, false);
}
{
  const { page, $, opened } = aPage(DIARY,
    { restored: () => Promise.reject(new Error('The saved conversation is incomplete.')) });
  await page.openTimeLimits();
  await $('time-limits-list').children[1].children[0].children[3].click();
  assert.deepEqual(opened, ['chat-1']);
  assert.equal($('time-limits-dialog').open, true, 'the diary stays where the conversation could not be read');
  assert.equal($('time-limits-status').textContent, 'That conversation could not be read: The saved conversation is incomplete.');
}

// ------------------------------------------- some conversations unread; none worked out; the diary unread ---
{
  const { page, $ } = aPage({ ...DIARY, state: 'partial', unavailable: ['chat-9'] });
  await page.openTimeLimits();
  const [first] = $('time-limits-list').children;
  assert.equal(first.className, 'state unbuildable');
  assert.equal(first.textContent,
    'Some conversations could not be read, so their time limits are not here. Retry before relying on this list.');
}
{
  const { page, $ } = aPage({ ...DIARY, coming: [], passed: [], not_worked: [] });
  await page.openTimeLimits();
  assert.equal($('time-limits-list').children.length, 0);
  assert.equal($('time-limits-status').textContent, 'None of your conversations has time limits worked out yet.');
  assert.equal($('time-limits-said').textContent, SAID);
}
{
  const { page, $ } = aPage(new Error('The server is not available.'));
  await page.openTimeLimits();
  assert.equal($('time-limits-status').textContent, 'The time limits could not be read: The server is not available. '
    + 'This is a failure to read them, not a statement that there are none.');
  assert.equal($('time-limits-list').children.length, 0);
}
{
  const { page, $ } = aPage(Object.assign(new Error('An earlier session.'), { obsolete: true }));
  await page.openTimeLimits();
  await settle();
  assert.equal($('time-limits-status').textContent, 'Reading your time limits…', 'an ended session writes nothing');
}

console.log('time_limits_diary.mjs: ok');
