// Documents attached to a message and the documents list (owner decisions, 15 and 16 Oct 2026):
// the chips report the server's states, scanned pages are read after upload, and a
// message cannot be sent while a document is being read, held or failed.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
function between(from, to) {
  const a = app.indexOf(from);
  const b = app.indexOf(to, a + from.length);
  assert.ok(a >= 0 && b > a, `slice ${from} .. ${to}`);
  return app.slice(a, b);
}

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.listeners = {}; this._text = ''; this.hidden = false; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
  click() { if (this.listeners.click) this.listeners.click(); }
}

function harness(replies) {
  const elements = {};
  const get = (id) => (elements[id] ||= new Element('div'));
  const requests = [];
  const delays = [];
  const context = vm.createContext({
    $: get, document: { createElement: (tag) => new Element(tag) }, encodeURIComponent,
    setPlusMenu() {}, loadUsage() {},
    setTimeout: (callback, ms) => { delays.push(ms); callback(); return 0; },
    api: async (url, options) => {
      requests.push({ url, options, shown: get('attachments').children[0] ? get('attachments').children[0].textContent : '' });
      const reply = replies.shift();
      if (reply instanceof Error) throw reply;
      return typeof reply === 'function' ? reply() : reply;
    },
  });
  vm.runInContext(between('// DOCUMENTS WITH A MESSAGE', '// F-C-02. THE MIC'), context);
  return { context, requests, get, delays };
}

const summary = (changes = {}) => ({
  document_ref: 'doc_aaaaaaaaaaaaaaaaaaaaaaaa-' + 'b'.repeat(64), name: 'memo.pdf', format: 'pdf',
  state: 'read', check: { state: 'clear', reason: 'no threat found by ClamAV', checker: 'clamav' },
  pages_total: 2, pages_read: 2, pages_read_by_ai: 0, pages_partly_legible: 0, waiting_for_ai: 0,
  unread: [], failure: null, ...changes,
});
const file = (name = 'memo.pdf', size = 1000) => ({ name, size });
const chip = (get, index = 0) => get('attachments').children[index];
// A reading is a background job: its replies say where it stands (plan AN.25, P4).
const done = (document, pages = 1) => ({ state: 'done', done: pages, total: pages, document });
const reading = (finished, total) => ({ state: 'reading', done: finished, total });

// A scanned page waits for the AI after upload, then the chip reports what was read.
{
  const scanned = summary({ state: 'partly_read', pages_read: 1, waiting_for_ai: 1,
    unread: [{ number: 2, reason: 'a scanned page with no text layer' }] });
  const { context, requests, get } = harness([scanned, done(summary({ pages_read_by_ai: 1, pages_partly_legible: 1 }))]);
  const pending = context.attachFile(file());
  assert.match(chip(get).textContent, /Checking for malware and reading/);
  assert.equal(context.attachmentsBlockSend(), 'Wait until the attached documents have been read.');
  await pending;
  assert.equal(requests[0].url, '/api/documents');
  assert.equal(requests[0].options.headers['X-NM-Document-Name'], 'memo.pdf');
  assert.equal(requests[1].url, `/api/documents/${encodeURIComponent(scanned.document_ref)}/reading`);
  assert.equal(requests[1].options.method, 'POST');
  assert.match(chip(get).textContent, /Read · 2 pages \(1 by AI\) · 1 page partly legible/);
  assert.equal(context.attachmentsBlockSend(), null);
}

// Without AI data sharing the scanned pages stay unread and the chip says why.
{
  const refused = Object.assign(new Error('Read the current AI data-sharing notice'), { status: 403 });
  const { context, get } = harness([summary({ state: 'not_read', pages_read: 0, waiting_for_ai: 1 }), refused]);
  await context.attachFile(file('scan.png'));
  assert.match(chip(get).textContent, /No page could be read\. Scanned pages were not read: accept AI data sharing/);
  assert.equal(context.attachmentsBlockSend(), null);
}

// The AI could not read the scan just now (17 Oct 2026): the chip says why and offers to
// read it again; reading again asks the same reader, and the button goes once all is read.
{
  const waiting = [1, 2].map((number) => ({ number, reason: 'the AI could not read this page just now; it can be read again' }));
  const { context, requests, get } = harness([
    summary({ state: 'not_read', pages_read: 0, waiting_for_ai: 2 }),
    done(summary({ state: 'not_read', pages_read: 0, waiting_for_ai: 2, unread: waiting }), 2),
    done(summary({ pages_read_by_ai: 2 }), 2)]);
  await context.attachFile(file('fir-scan.pdf'));
  assert.equal(chip(get).textContent,
    'fir-scan.pdfNo page could be read: the AI could not read this page just now; it can be read againRead again×');
  assert.equal(context.attachmentsBlockSend(), null);
  const again = chip(get).children[2];
  assert.equal(again.attributes['aria-label'], 'Ask the AI to read the unread pages of fir-scan.pdf again');
  const pending = again.listeners.click();
  assert.match(chip(get).textContent, /Reading scanned pages with AI/);
  assert.equal(context.attachmentsBlockSend(), 'Wait until the attached documents have been read.');
  await pending;
  assert.equal(requests.length, 3);
  assert.equal(requests[2].url, requests[1].url);
  assert.equal(chip(get).textContent, 'fir-scan.pdfRead · 2 pages (2 by AI)×');
}

// A recording waiting to be transcribed offers to transcribe it again.
{
  const { context, get } = harness([summary({ recording: true, state: 'not_read', pages_read: 0, waiting_for_ai: 1 }),
    done(summary({ recording: true, state: 'not_read', pages_read: 0, waiting_for_ai: 1,
      unread: [{ number: 1, reason: 'the recording could not be transcribed just now; it can be tried again' }] }))]);
  await context.attachFile(file('call.mp3'));
  assert.match(chip(get).textContent, /Not transcribed: the recording could not be transcribed just now/);
  assert.equal(chip(get).children[2].textContent, 'Transcribe again');
}

// Reading scans is a background job (plan AN.25, P4): started once, asked after until it ends, the chip saying how many pages are read,
// and no request held for the whole of a long scan. A job that failed says why; one lost when the server restarted says it was
// interrupted; both leave the chip offering to read again. Removing the chip stops the asking.
{
  const scanned = summary({ state: 'partly_read', pages_read: 1, pages_total: 4, waiting_for_ai: 3,
    unread: [2, 3, 4].map((number) => ({ number, reason: 'a scanned page with no text layer' })) });
  const address = `/api/documents/${encodeURIComponent(scanned.document_ref)}/reading`;
  const { context, requests, get, delays } = harness([scanned, reading(0, 3), reading(2, 3),
    done(summary({ pages_total: 4, pages_read: 4, pages_read_by_ai: 3 }), 3)]);
  await context.attachFile(file('long-scan.pdf'));
  assert.deepEqual(requests.map((request) => [request.url, request.options && request.options.method || 'GET']),
    [['/api/documents', 'POST'], [address, 'POST'], [address, 'GET'], [address, 'GET']]);
  assert.deepEqual(delays, [1000, 1000], 'the page waits a second before each time it asks');
  assert.match(requests[2].shown, /Reading scanned pages with AI… 0 of 3 pages read/);
  assert.match(requests[3].shown, /Reading scanned pages with AI… 2 of 3 pages read/);
  assert.match(chip(get).textContent, /Read · 4 pages \(3 by AI\)/);
  assert.equal(context.attachmentsBlockSend(), null);
  const one = harness([scanned, reading(0, 1), done(summary({ pages_read_by_ai: 1 }), 1)]);
  await one.context.attachFile(file('one.pdf'));
  assert.match(one.requests[2].shown, /0 of 1 page read/);
}
{
  const scanned = summary({ state: 'partly_read', pages_read: 1, waiting_for_ai: 1,
    unread: [{ number: 2, reason: 'a scanned page with no text layer' }] });
  const failed = { state: 'failed', done: 1, total: 3, error: { status: 402, why: 'You have used all your AI usage.', code: 'usage_limit' } };
  const one = harness([scanned, reading(1, 3), failed]);
  await one.context.attachFile(file('scan.pdf'));
  assert.match(chip(one.get).textContent, /Scanned pages were not read: You have used all your AI usage\./);
  assert.equal(chip(one.get).children[2].textContent, 'Read again');
  const lost = harness([scanned, reading(1, 3), Object.assign(new Error('No reading of this document is running.'), { status: 404 })]);
  await lost.context.attachFile(file('scan.pdf'));
  assert.match(chip(lost.get).textContent, /Scanned pages were not read: the reading was interrupted; read it again\./);
  assert.equal(chip(lost.get).children[2].textContent, 'Read again');
  // Taking the chip away stops the asking: no request after the one that was in flight.
  const away = harness([scanned, reading(0, 3), () => {
    vm.runInContext('attachments.length = 0', away.context);
    return reading(1, 3);
  }, reading(2, 3)]);
  await away.context.attachFile(file('scan.pdf'));
  assert.equal(away.requests.length, 3, 'it did not go on asking after the chip was removed');
}

// A held or failed document blocks sending until it is removed; an oversized one is
// refused without any request.
{
  const held = summary({ state: 'held', pages_read: 0, pages_total: null,
    check: { state: 'held', reason: 'ClamAV reported a threat in this file', checker: 'clamav' } });
  const { context, requests, get } = harness([held, new Error('Only PDF, Word (.docx), plain text (.txt), PNG or JPEG files can be read.')]);
  await context.attachFile(file('bad.pdf'));
  await context.attachFile(file('tool.exe'));
  await context.attachFile(file('huge.pdf', 17 * 1024 * 1024));
  assert.equal(requests.length, 2);
  assert.match(chip(get, 0).textContent, /Held, not read: ClamAV reported a threat/);
  assert.match(chip(get, 1).textContent, /Not attached: Only PDF/);
  assert.match(chip(get, 2).textContent, /Not attached: a document can be at most 16 MB/);
  assert.equal(context.attachmentsBlockSend(), 'Remove the documents that could not be used before sending.');
  for (let i = 0; i < 3; i += 1) chip(get).children[2].click();
  assert.equal(get('attachments').hidden, true);
  assert.equal(context.attachmentsBlockSend(), null);
}

// A message carries at most ten documents (the server's limit; owner decision, 26 Oct 2026, plan AN.26): what comes after the first
// ten is not kept - no request is made for it and no chip is left to block sending - and the advocate is told plainly. Held and
// failed documents are not carried, so they do not use up a place.
{
  const told = "You can't upload more than 10 documents at a time, so only the first 10 were kept.";
  const held = summary({ state: 'held', pages_read: 0, pages_total: null,
    check: { state: 'held', reason: 'ClamAV reported a threat in this file', checker: 'clamav' } });
  const { context, requests, get } = harness([held, ...Array.from({ length: 10 }, () => summary())]);
  await context.attachFile(file('bad.pdf'));
  for (let n = 1; n <= 10; n += 1) await context.attachFile(file(`doc${n}.pdf`));
  assert.equal(requests.length, 11, 'a held document does not use up a place: all ten good ones were attached');
  assert.equal(get('attachments-status').textContent, '', 'nothing is said while there is room');
  await context.attachFile(file('eleventh.pdf'));
  await context.attachFile(file('twelfth.pdf'));
  assert.equal(requests.length, 11, 'nothing after the first ten is sent to the server');
  assert.equal(get('attachments').children.length, 11, 'and no chip is left for it (the ten and the held one)');
  assert.equal(get('attachments-status').textContent, told);
  // A recording that would need converting is not even started.
  get('attachments-status').textContent = '';
  await context.attachFile(file('call.opus'));
  assert.equal(get('attachments').children.length, 11);
  assert.equal(get('attachments-status').textContent, told);
  chip(get, 0).children[2].click();  // the held one goes
  assert.equal(context.attachmentsBlockSend(), null, 'nothing is left to block sending');
  // The send gate holds the same line if more than ten ever get past the door.
  vm.runInContext("attachments.push({ name: 'extra.pdf', status: 'ready', summary: null, note: '' })", context);
  assert.equal(context.attachmentsBlockSend(), 'A message can carry at most 10 documents; remove 1 before sending.');
}

// Twelve chosen at once, as the file picker delivers them: the first ten are kept, in order, and the advocate is told.
{
  const { requests, get } = harness(Array.from({ length: 10 }, (_, n) => summary({ name: `d${n + 1}.pdf` })));
  get('attach-files').files = Array.from({ length: 12 }, (_, n) => file(`d${n + 1}.pdf`));
  get('attach-files').listeners.change();
  for (let wait = 0; wait < 20; wait += 1) await Promise.resolve();
  assert.deepEqual(requests.map((request) => request.options.headers['X-NM-Document-Name']),
    Array.from({ length: 10 }, (_, n) => `d${n + 1}.pdf`));
  assert.equal(get('attachments').children.length, 10);
  assert.equal(get('attachments-status').textContent,
    "You can't upload more than 10 documents at a time, so only the first 10 were kept.");
  assert.equal(get('attach-files').value, '');
}

// The matter's files (owner decision 4, 17 Oct 2026): a plain list. Each name opens the
// file as sent, a note appears only when something needs attention, and "Read here" opens
// what NM read as one document (decision 5), each page marked where it begins.
{
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag) },
    stateBlock: (_kind, text) => Object.assign(new Element('p'), { textContent: text }),
  });
  vm.runInContext(between("// THE MATTER'S FILES", 'const CERTAINTY = '), context);
  // The page has one fileSize (18 Oct 2026: a second, shadowed copy had been tested instead).
  vm.runInContext(between('function fileSize(bytes) {', "/* F-B-04, later the same day."), context);
  const [empty] = context.renderChatDocuments({ sent: [] }, () => {});
  assert.match(empty.textContent, /No files have been sent/);
  const received = '2026-10-17T04:20:00+00:00';
  const turn = { turn_id: 't1', message: 'Please look at the memo.',
    documents: [{ document_ref: 'doc_x', name: 'memo.pdf',
      file: { format: 'pdf', size: 12877, received_at: received, pages_total: 3, cleared: true },
      pages: [{ number: 1, text: 'Return memo.', read_by: 'local' },
              { number: 2, text: 'Notice [illegible]', read_by: 'ai', model: 'gpt-6-luna', legible: 'part',
                note: 'lower edge cut off' }],
      unread: [{ number: 3, reason: 'the AI could not make out this page' }] },
    { document_ref: 'doc_y', name: 'Police complaint.docx',
      file: { format: 'docx', size: 3347, received_at: received, pages_total: 1, cleared: true },
      pages: [{ number: 1, text: 'Complaint.', read_by: 'local' }], unread: [] }] };
  const opened = [];
  const [list] = context.renderChatDocuments({ sent: [turn] }, (doc, sent, opener) => opened.push([doc, sent, opener]));
  const [memo, word] = list.children;
  const [tile, body] = memo.children;
  assert.equal(tile.textContent, 'PDF');
  const [name, meta, attention, read] = body.children;
  assert.equal(name.textContent, 'memo.pdf');
  assert.equal(name.href, '/api/documents/doc_x/original');
  assert.equal(name.target, '_blank');
  assert.equal(meta.textContent, 'PDF · 12.6 KB · sent 17 Oct 2026 · read by AI');
  assert.equal(attention.textContent, '1 page could not be read · 1 page partly legible');
  assert.equal(memo.title, 'Sent with: “Please look at the memo.”');
  const wordBody = word.children[1];
  assert.equal(wordBody.children[0].attributes['aria-label'], 'Police complaint.docx, opens in Word');
  assert.equal(wordBody.children[1].textContent, 'Word · 3.3 KB · sent 17 Oct 2026 · opens in Word');
  assert.equal(wordBody.children.length, 3, 'no note when nothing needs attention');
  read.click();
  assert.equal(opened.length, 1);
  assert.equal(opened[0][0].name, 'memo.pdf');
  assert.equal(opened[0][2], read);
  const shown = context.renderDocumentPages(opened[0][0], opened[0][1]);
  // As the design shows it (18 Oct 2026): how many pages and that this is as NM read them.
  assert.equal(shown[0].textContent, '3 pages · as NM read it');
  assert.equal(shown[1].textContent, 'Open the file as sent');
  assert.equal(shown[1].href, '/api/documents/doc_x/original');
  assert.equal(shown[2].textContent, 'Sent with: “Please look at the memo.”');
  assert.equal(shown[3].className, 'document-flow whole');
  assert.deepEqual(shown[3].children.map((node) => node.textContent), [
    'Page 1', 'Return memo.', 'Page 2 · read by AI, partly legible', 'lower edge cut off', 'Notice [illegible]',
    'Page 3', 'Not read: the AI could not make out this page']);
  // A file whose own record could not be read still lists what the conversation saved.
  const [bare] = context.renderChatDocuments({ sent: [{ ...turn, documents: [{ ...turn.documents[1], file: null }] }] },
    () => {}).map((node) => node.children[0]);
  assert.equal(bare.children[1].children[1].textContent, 'File');
}

console.log('attachments: ok');
