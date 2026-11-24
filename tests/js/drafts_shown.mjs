// A draft the advocate asked for, drawn in the conversation (plan AN.67, piece 23d3; D331): beneath the answer it was saved with,
// or beneath the stop that drafted it - never on the board or in the reading pane (D60). The server gives the draft as code's view
// of it; the page only draws it: the parts in order, each particular the papers do not give highlighted where it goes, what code
// and the review still find, the notes for the advocate, and each version's Word file. A conversation opened from the history
// carries each saved answer's drafts; an answer just given and a stop that has drafted ask for them once.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const from = app.indexOf('// A DRAFT THE ADVOCATE ASKED FOR');
const to = app.indexOf('// THE LIMITS OF THE SEARCH', from);
assert.ok(from >= 0 && to > from);

class Node {
  constructor(tag) {
    this.tag = tag; this.children = []; this._text = ''; this.hidden = false; this.className = ''; this.attributes = {};
    this.listeners = {};
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(kind, listener) { this.listeners[kind] = listener; }
  find(test) {
    const found = [];
    const walk = (node) => { if (test(node)) found.push(node); (node.children || []).forEach(walk); };
    walk(this);
    return found;
  }
}

function harness(reply) {
  const asked = [], saved = [];
  const context = vm.createContext({
    document: { createElement: (tag) => new Node(tag), createTextNode: (text) => { const node = new Node('#text'); node._text = text; return node; } },
    encodeURIComponent, JSON, Set, Object, Array, String, Boolean,
    api: async (url) => { asked.push(url); if (reply instanceof Error) throw reply; return reply; },
    saveWordFile: async (url, status, said) => { saved.push({ url, said }); },
  });
  vm.runInContext(app.slice(from, to), context);
  return { context, asked, saved };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));

const draft = {
  dispute: 'D1', name: 'Dispute 1', versions: 1, title: 'Demand notice', state: 'for_advocate_review',
  parts: [
    { part_id: 'heading', title: 'Notice', paragraphs: ['Dated [particular needed: the date of the notice], sent by post.'],
      faults: [], found: [] },
    { part_id: 'cheque', title: 'The cheque', paragraphs: ['Cheque no. [particular needed: the cheque\'s number] of the drawer.'],
      faults: ['NM\'s own checks still find that this part does not stand.'],
      found: ['An independent review found that this part states what nothing given bears out: the date.'] },
  ],
  beside: ['The review also said: name the bank.'], reviewed: null, notes: ['Check the thirty days.'],
  said: 'Drafted by Nyaymalaw for your review.',
};
const answer = { chat_id: 'chat 1', turn_id: 't/1', blocked: false, committed: true };

// Opened from the history: the answer carries its drafts; drawn at once, folded, and nothing is asked of the server.
{
  const { context, asked, saved } = harness({});
  const box = context.answerDrafts({ ...answer, drafts: [draft] });
  assert.equal(box.className, 'drafts');
  assert.equal(box.hidden, false);
  const [block] = box.children;
  assert.equal(block.className, 'draft-block');
  const [fold, foot] = block.children;
  assert.equal(fold.tag, 'details');
  assert.equal(fold.open, false, 'folded beneath a saved answer, as its detail is');
  assert.equal(fold.children[0].textContent,
    'Draft for your review: Demand notice (Dispute 1) · 2 particulars the papers do not give');
  assert.deepEqual(fold.find((node) => node.tag === 'h4').map((node) => node.textContent), ['Notice', 'The cheque']);
  // Each particular the papers do not give, highlighted where it goes; the words around it as they are.
  const marks = fold.find((node) => node.tag === 'mark');
  assert.deepEqual(marks.map((node) => [node.className, node.textContent]), [
    ['draft-needed', '[particular needed: the date of the notice]'], ['draft-needed', '[particular needed: the cheque\'s number]']]);
  const first = fold.find((node) => node.className === 'draft-paragraph')[0];
  assert.equal(first.textContent, draft.parts[0].paragraphs[0]);
  // What code and the review still find, under its part; the notes apart from the document; the foot's words.
  assert.deepEqual(fold.find((node) => node.className === 'draft-finding').map((node) => node.textContent),
    [...draft.parts[1].faults, ...draft.parts[1].found]);
  assert.deepEqual(fold.find((node) => node.tag === 'li').map((node) => node.textContent),
    ['The review also said: name the bank.', 'Check the thirty days.']);
  assert.equal(fold.find((node) => node.className === 'draft-said')[0].textContent, draft.said);
  assert.equal(fold.find((node) => node.className === 'draft-unreviewed').length, 0, 'reviewed: nothing said of it');
  // Its Word file, at the draft's own address.
  const buttons = foot.find((node) => node.tag === 'button');
  assert.deepEqual(buttons.map((node) => node.textContent), ['Word']);
  await buttons[0].listeners.click();
  assert.deepEqual(saved.map((item) => item.url), ['/api/chats/chat%201/turns/t%2F1/drafts/D1/1.docx']);
  assert.equal(saved[0].said.saved, 'Draft saved as a Word file');
  assert.deepEqual(asked, []);
}

// Several versions (23d4): the latest shown, each earlier one its own Word file; a draft not reviewed says so.
{
  const { context, saved } = harness({});
  const box = context.answerDrafts({ ...answer, drafts: [{ ...draft, versions: 3, name: null,
    reviewed: 'This draft as it stands was not reviewed independently.' }] });
  const [fold, foot] = box.children[0].children;
  assert.equal(fold.children[0].textContent,
    'Draft for your review: Demand notice · version 3 · 2 particulars the papers do not give');
  assert.equal(fold.children[1].textContent, 'This draft as it stands was not reviewed independently.');
  const buttons = foot.find((node) => node.tag === 'button');
  assert.deepEqual(buttons.map((node) => node.textContent), ['Word', 'Version 1', 'Version 2']);
  for (const button of buttons) await button.listeners.click();
  assert.deepEqual(saved.map((item) => item.url.split('/drafts/')[1]), ['D1/3.docx', 'D1/1.docx', 'D1/2.docx']);
}

// An answer just given: asked for once, at its own address, hidden until it comes, and kept on the answer.
{
  const { context, asked } = harness({ drafts: [draft] });
  const given = { ...answer, committed: 'committed' };
  const box = context.answerDrafts(given);
  assert.equal(box.hidden, true);
  await settle();
  assert.deepEqual(asked, ['/api/chats/chat%201/turns/t%2F1/drafts']);
  assert.equal(box.hidden, false);
  assert.equal(given.drafts.length, 1);
}

// An answer with no draft shows nothing, and one known to have none asks for nothing; not a saved answer, nothing at all.
{
  const { context, asked } = harness({ drafts: [] });
  assert.equal(context.answerDrafts({ ...answer, drafts: [] }), null);
  const given = { ...answer, committed: 'committed' };
  const box = context.answerDrafts(given);
  await settle();
  assert.equal(box.hidden, true);
  assert.deepEqual(given.drafts, []);
  for (const not of [{ ...answer, committed: 'unconfirmed' }, { ...answer, blocked: true }, { turn_id: 't1', committed: true }, null]) {
    assert.equal(context.answerDrafts(not), null);
  }
  assert.equal(asked.length, 1);
}

// Beneath a stop that has drafted: asked for once, open; drawn again from what was had while what it drafted is the same, and
// asked for again when that changes. A stop that has drafted nothing asks for nothing.
{
  const { context, asked } = harness({ drafts: [draft] });
  const entry = { turnId: 'turn-1', chatId: 'chat 1', stopped: { code: 'waiting', waiting: { drafted: { D1: 1 } } } };
  const box = context.heldDrafts(entry);
  await settle();
  assert.equal(box.hidden, false);
  assert.equal(box.children[0].children[0].open, true, 'open where the stop has just drafted it');
  context.heldDrafts(entry);
  assert.deepEqual(asked, ['/api/chats/chat%201/turns/turn-1/drafts']);
  entry.stopped.waiting.drafted = { D1: 2 };
  context.heldDrafts(entry);
  assert.equal(asked.length, 2);
  assert.equal(context.heldDrafts({ turnId: 'turn-1', chatId: 'chat 1', stopped: { code: 'waiting', waiting: {} } }), null);
  assert.equal(context.heldDrafts({ turnId: 'turn-1', chatId: 'chat 1', stopped: { code: 'waiting', waiting: { drafted: {} } } }), null);
  assert.equal(asked.length, 2);
}

// The drafts could not be fetched: that is said in plain words, and the answer stands.
{
  const { context } = harness(new Error('HTTP 500'));
  const box = context.answerDrafts({ ...answer, committed: 'committed' });
  await settle();
  assert.equal(box.hidden, false);
  assert.match(box.textContent, /could not be shown just now/);
  assert.doesNotMatch(box.textContent, /HTTP|500/);
}

// The draft is drawn beneath the answer and beneath the stop, and nowhere on the board or in the reading pane (D60).
{
  const stopped = app.slice(app.indexOf("if (entry.state === 'stopped' && !entry.answer) {"), app.indexOf("if (entry.state === 'reconnecting'"));
  assert.match(stopped, /heldDrafts\(entry\)/);
  assert.match(app, /wrap\.appendChild\(replyFooter\(entry[^\n]*\n[^\n]*\n\s*const drafted = answerDrafts\(entry\.answer\);/);
  assert.equal((app.match(/answerDrafts\(|heldDrafts\(/g) || []).length, 4, 'two definitions and one use of each');
}

console.log('drafts_shown: ok');
