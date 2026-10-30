// Voice notes in the browser (owner decisions, 15 Oct 2026): recordings the service
// takes go as they are, others are converted here to WAV parts of at most ten minutes,
// video is refused, and the chips report what the server heard.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const app = readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const from = app.indexOf('// DOCUMENTS WITH A MESSAGE');
const to = app.indexOf('// F-C-02. THE MIC', from);
assert.ok(from >= 0 && to > from);

class Element {
  constructor() { this.children = []; this.listeners = {}; this._text = ''; this.hidden = false; this.attributes = {}; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(event, handler) { this.listeners[event] = handler; }
}

function harness(replies, { seconds = 2 } = {}) {
  const elements = {};
  const requests = [];
  const rendered = [];
  class Playing {
    async decodeAudioData() { return { duration: seconds }; }
    close() {}
  }
  class Mixing {
    constructor(channels, length, rate) { this.length = length; this.rate = rate; rendered.push({ channels, length, rate }); }
    createBufferSource() { return { connect() {}, start() {} }; }
    async startRendering() { const samples = new Float32Array(this.length); return { getChannelData: () => samples }; }
  }
  const context = vm.createContext({
    $: (id) => (elements[id] ||= new Element()), document: { createElement: () => new Element() },
    encodeURIComponent, Blob, File, setPlusMenu() {}, loadUsage() {},
    window: { AudioContext: Playing }, OfflineAudioContext: Mixing,
    setTimeout: (callback) => { callback(); return 0; },
    api: async (url, options) => {
      requests.push({ url, name: options?.headers?.['X-NM-Document-Name'], size: options?.body?.size,
        type: options?.body?.type });
      const reply = replies.shift();
      if (reply instanceof Error) throw reply;
      return reply;
    },
  });
  vm.runInContext(app.slice(from, to), context);
  const chips = () => elements.attachments.children.map((chip) => chip.textContent);
  return { context, requests, rendered, chips };
}

const recording = (changes = {}) => ({
  document_ref: 'doc_aaaaaaaaaaaaaaaaaaaaaaaa-' + 'b'.repeat(64), name: 'note.m4a', format: 'm4a', recording: true,
  state: 'not_read', check: { state: 'clear', reason: 'no threat found by ClamAV', checker: 'clamav' },
  pages_total: 1, pages_read: 0, pages_read_by_ai: 0, pages_partly_legible: 0, waiting_for_ai: 1,
  unread: [{ number: 1, reason: 'a recording, waiting to be transcribed' }], failure: null, ...changes,
});
const heard = recording({ state: 'read', pages_read: 1, pages_read_by_ai: 1, waiting_for_ai: 0, unread: [] });
// A reading is a background job (plan AN.25, P4): its reply says it is done, with the document.
const done = (document) => ({ state: 'done', done: 1, total: 1, document });

// A recording the service takes goes as it is, and is transcribed after upload.
{
  const { context, requests, chips } = harness([recording(), done(heard)]);
  await context.attachFile(new File([new Uint8Array(100)], 'note.m4a', { type: 'audio/mp4' }));
  assert.deepEqual(requests.map((r) => r.url), ['/api/documents',
    `/api/documents/${encodeURIComponent(heard.document_ref)}/reading`]);
  assert.equal(requests[0].name, 'note.m4a');
  assert.match(chips()[0], /note\.m4aTranscribed by AI×/);
  assert.equal(context.attachmentsBlockSend(), null);
}

// A WhatsApp voice note is converted here to 16 kHz mono WAV before it leaves.
{
  const { context, requests, rendered, chips } = harness([recording({ name: 'PTT-01.opus.wav', format: 'wav' }),
    done(recording({ name: 'PTT-01.opus.wav', format: 'wav', state: 'read', pages_read: 1, waiting_for_ai: 0, unread: [] }))]);
  await context.attachFile(new File([new Uint8Array(50)], 'PTT-01.opus', { type: 'audio/ogg' }));
  assert.deepEqual(rendered, [{ channels: 1, length: 32000, rate: 16000 }]);
  assert.equal(requests[0].name, 'PTT-01.opus.wav');
  assert.equal(requests[0].type, 'audio/wav');
  assert.equal(requests[0].size, 44 + 32000 * 2);
  assert.match(chips()[0], /Transcribed by AI/);
}

// A long recording is converted into parts of at most ten minutes, each its own chip.
{
  // The two parts are uploaded together, then read together: both uploads answer first, then both readings.
  const replies = [recording(), recording(), done(heard), done(heard)];
  const { context, requests } = harness(replies, { seconds: 650 });
  await context.attachFile(new File([new Uint8Array(50)], 'call.aac', { type: 'audio/aac' }));
  const names = requests.filter((r) => r.url === '/api/documents').map((r) => decodeURIComponent(r.name)).sort();
  assert.deepEqual(names, ['call.aac (part 1 of 2).wav', 'call.aac (part 2 of 2).wav']);
}

// Video is refused before anything leaves; a recording that cannot be heard says why.
{
  const { context, requests, chips } = harness([recording(),
    done(recording({ unread: [{ number: 1, reason: 'no speech was heard in this recording' }], waiting_for_ai: 0 }))]);
  await context.attachFile(new File([new Uint8Array(10)], 'clip.mp4', { type: 'video/mp4' }));
  assert.equal(requests.length, 0);
  assert.match(chips()[0], /Not attached: video is not read/);
  await context.attachFile(new File([new Uint8Array(10)], 'silence.wav', { type: 'audio/wav' }));
  assert.match(chips()[1], /Not transcribed: no speech was heard in this recording/);
  assert.equal(context.attachmentsBlockSend(), 'Remove the documents that could not be used before sending.');
}

// Without AI permission the recording stays untranscribed and the chip says how to allow it.
{
  const refused = Object.assign(new Error('Read the current AI data-sharing notice'), { status: 403 });
  const { context, chips } = harness([recording(), refused]);
  await context.attachFile(new File([new Uint8Array(10)], 'note.webm', { type: 'audio/webm' }));
  assert.match(chips()[0], /The recording was not transcribed: accept AI data sharing in your profile/);
}

console.log('voice notes: ok');
