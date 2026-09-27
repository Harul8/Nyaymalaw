'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {createHash, webcrypto} = require('node:crypto');

const shipped = fs.readFileSync('nm/legal_brain/communicate/matter-workspace.js', 'utf8');
function walk(node) { return [node, ...node.children.flatMap(walk)]; }
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.listeners = {}; this.attributes = {}; this.open = false; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(' '); }
  set innerHTML(_value) { throw new Error('An original must never become HTML.'); }
  append(...nodes) { nodes.forEach(node => { node.parentElement = this; this.children.push(node); }); }
  prepend(...nodes) { nodes.reverse().forEach(node => { node.parentElement = this; this.children.unshift(node); }); }
  replaceChildren(...nodes) { this.text = ''; this.children = []; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(kind, handler) { (this.listeners[kind] ||= []).push(handler); }
  async fire(kind) { for (const handler of this.listeners[kind] || []) await handler({preventDefault() {}}); }
  querySelectorAll(tag) { return walk(this).filter(node => node.tagName === tag); }
  showModal() { this.open = true; }
  close() { this.open = false; for (const handler of this.listeners.close || []) handler(); }
  get classList() { return {add: () => {}}; }
}
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes; }); return {promise, resolve}; }
function record(bytes = Buffer.from('<script>PRIVATE ORIGINAL</script>'), format = 'text') {
  const hash = createHash('sha256').update(bytes).digest('hex');
  const original = {original_id: 'upload_one', matter_version: 7, asset_version: 1,
    source_sha256: hash, byte_length: bytes.length, page: 3, span: 'Recorded paragraph'};
  const casefile = {state: 'ok', matter_id: 'matter_one', version: 7, repetition_upgrades: [], split_disputes: [],
    entries: [{fact_id: 'fact_one', version: 1, statement: 'An asserted statement', certainty: 'asserted',
      confirmed: 'not_asked', superseded_by: '', conflicts_with: [], attribution: {document: 'upload_one',
        page: 3, span: 'Recorded paragraph', read_quality: 'clear', said: 'upload_one page 3', original}}]};
  const acknowledgement = {state: 'original_opened', matter_id: 'matter_one', matter_version: 7,
    original_id: 'upload_one', asset_version: 1, source_sha256: hash, byte_length: bytes.length,
    content_base64: bytes.toString('base64'), filename: 'private.txt', format, facts_established: false,
    representation: 'original_bytes', purpose: 'human_original_inspection'};
  return {casefile, acknowledgement};
}
function fixture(value = record()) {
  const body = new Element('body');
  for (const id of ['workspace-menu', 'save-status']) { const node = new Element('div'); node.id = id; body.append(node); }
  const events = {}, calls = [], urls = [], revoked = [], downloads = [];
  const state = {matterId: 'matter_one', advocate: 'adv_one', ended: false, matterReady: true,
    sessionGeneration: 1, railGeneration: 1};
  let reply = url => structuredClone(url.endsWith('/casefile') ? value.casefile : value.acknowledgement);
  const document = {body, getElementById: id => walk(body).find(node => node.id === id),
    createElement: tag => { const node = new Element(tag); node.click = () => downloads.push({href: node.href, download: node.download}); return node; }};
  const sandbox = {document, state, crypto: webcrypto, URLSearchParams, AbortController, Uint8Array,
    TextDecoder, Blob, atob, URL: {createObjectURL: blob => { const url = `blob:checked-${urls.length}`; urls.push({url, blob}); return url; },
      revokeObjectURL: url => revoked.push(url)},
    window: {addEventListener: (kind, handler) => (events[kind] ||= []).push(handler)},
    api: async (url, options) => { calls.push({url, options}); return reply(url, options); }};
  vm.runInNewContext(shipped, sandbox);
  const find = predicate => walk(body).find(predicate);
  const button = text => { const node = find(node => node.tagName === 'button' && node.textContent === text); assert.ok(node, text); return node; };
  return {body, state, calls, urls, revoked, downloads, find, button, value,
    reply: handler => { reply = handler; }, dispatch: kind => (events[kind] || []).forEach(handler => handler()),
    openFile: () => button('Attributed file').fire('click'), openOriginal: () => button('Open original at recorded location').fire('click')};
}

test('exact source opens original text through the existing scoped API helper without confirming a fact', async () => {
  const f = fixture(); await f.openFile(); await f.openOriginal();
  const call = f.calls.at(-1), query = new URL('http://local' + call.url);
  assert.equal(query.pathname, '/api/matters/matter_one/uploads/upload_one/content');
  assert.deepEqual(Object.fromEntries(query.searchParams), {view: 'original', version: '7', asset_version: '1',
    source_sha256: f.value.acknowledgement.source_sha256, purpose: 'human_original_inspection'});
  assert.equal(call.options.method, 'GET'); assert.equal(call.options.cache, 'no-store');
  assert.equal(call.options.credentials, 'same-origin'); assert.ok(call.options.signal);
  assert.ok(f.find(node => node.tagName === 'pre').textContent.includes('<script>PRIVATE ORIGINAL</script>'));
  assert.equal(f.find(node => node.tagName === 'script'), undefined);
  assert.match(f.body.textContent, /not a verified text-page mapping/);
  assert.match(f.body.textContent, /No case fact was confirmed or changed/);
  assert.equal(f.downloads.length, 0); assert.equal(f.urls.length, 0);
});

test('legacy filename locators remain unavailable and cannot initiate an original read', async () => {
  const value = record(); const source = value.casefile.entries[0].attribution;
  source.document = 'private.txt'; delete source.original;
  const f = fixture(value); await f.openFile();
  assert.match(f.body.textContent, /Opening the original is not available/);
  assert.equal(f.find(node => node.textContent === 'Open original at recorded location'), undefined);
  assert.equal(f.calls.length, 1);
});

test('changed, ill-typed or unbound locators cannot select a filename, URL or another original', async () => {
  for (const mutation of [value => {value.original_id = 'https://foreign.test/client';},
    value => {value.asset_version = true;}, value => {value.page = true;},
    value => {value.source_sha256 = 'wrong';}, value => {value.matter_version = 8;},
    value => {value.original_id = 'other_upload';}, value => {value.byte_length = 8 * 1024 * 1024 + 1;}]) {
    const value = record(); mutation(value.casefile.entries[0].attribution.original);
    const f = fixture(value); await f.openFile();
    assert.match(f.body.textContent, /identity could not be established/); assert.equal(f.calls.length, 1);
    assert.equal(f.find(node => node.tagName === 'iframe'), undefined);
  }
});

test('PDF frame has no active-content permissions, no referrer, and uses the recorded page', async () => {
  const f = fixture(record(Buffer.from('%PDF-1.7\ncontrolled fixture'), 'pdf'));
  await f.openFile(); await f.openOriginal();
  const frame = f.find(node => node.tagName === 'iframe'); assert.ok(frame);
  assert.equal(frame.attributes.sandbox, ''); assert.equal(frame.attributes.referrerpolicy, 'no-referrer');
  assert.equal(frame.attributes.allow, undefined); assert.equal(frame.src, 'blob:checked-0#page=3');
  assert.equal(f.urls[0].blob.type, 'application/pdf'); assert.equal(f.downloads.length, 0);
  await f.button('Close').fire('click'); assert.deepEqual(f.revoked, ['blob:checked-0']);
  assert.ok(!f.body.textContent.includes('PRIVATE ORIGINAL'));
});

test('unsupported inline formats require a separate deliberate download with a security note', async () => {
  const f = fixture(record(Buffer.from('controlled docx bytes'), 'docx'));
  await f.openFile(); await f.openOriginal();
  assert.equal(f.find(node => node.tagName === 'iframe'), undefined);
  assert.match(f.body.textContent, /no inline original viewer/); assert.match(f.body.textContent, /active content disabled/);
  assert.equal(f.urls.length, 0); assert.equal(f.downloads.length, 0);
  await f.button('Download this original').fire('click');
  assert.deepEqual(f.downloads, [{href: 'blob:checked-0', download: 'upload_one.docx'}]);
  assert.equal(f.urls[0].blob.type, 'application/octet-stream');
  assert.match(f.body.textContent, /not erased when NM closes or signs out/);
  f.state.matterId = 'another_matter'; f.dispatch('nm:matter-changed');
  assert.deepEqual(f.revoked, ['blob:checked-0']);
});

test('changed acknowledgement identity, permission or actual bytes never produces a replacement preview', async () => {
  for (const mutation of [value => {value.matter_id = 'foreign';}, value => {value.matter_version = 8;},
    value => {value.asset_version = true;}, value => {value.source_sha256 = 'a'.repeat(64);},
    value => {value.facts_established = true;}, value => {value.purpose = 'automatic_analysis';},
    value => {value.format = 'html';}, value => {value.content_base64 = Buffer.from('WRONG ORIGINAL OF SAME LENGTH!!').toString('base64');},
    value => {value.content_base64 = '*'.repeat(value.content_base64.length);}]) {
    const value = record(); mutation(value.acknowledgement);
    const f = fixture(value); await f.openFile(); await f.openOriginal();
    assert.match(f.body.textContent, /could not be opened under its current permission/);
    assert.ok(!f.body.textContent.includes('PRIVATE ORIGINAL')); assert.equal(f.urls.length, 0);
    assert.equal(f.find(node => node.tagName === 'pre'), undefined);
  }
});

test('a tampered same-length base64 original fails its actual SHA instead of trusting the response label', async () => {
  const value = record(); const bytes = Buffer.from(value.acknowledgement.content_base64, 'base64');
  bytes[0] ^= 1; value.acknowledgement.content_base64 = bytes.toString('base64');
  const f = fixture(value); await f.openFile(); await f.openOriginal();
  assert.match(f.body.textContent, /could not be opened/); assert.equal(f.urls.length, 0);
});

test('lost or withdrawn permission clears the original instead of rendering raw server error content', async () => {
  const f = fixture(); await f.openFile(); f.reply(async () => {throw new Error('PRIVATE ERROR CANARY');});
  await f.openOriginal(); assert.ok(!f.body.textContent.includes('PRIVATE ERROR CANARY'));
  assert.match(f.body.textContent, /No replacement document was substituted/); assert.equal(f.urls.length, 0);
});

for (const boundary of ['matter', 'session', 'close']) {
  test(`delayed original response cannot repaint after ${boundary} boundary`, async () => {
    const f = fixture(); await f.openFile(); const held = deferred(); f.reply(async () => held.promise);
    const pending = f.openOriginal(); const signal = f.calls.at(-1).options.signal;
    if (boundary === 'matter') {f.state.matterId = 'foreign'; f.state.railGeneration += 1; f.dispatch('nm:matter-changed');}
    else if (boundary === 'session') {f.state.advocate = null; f.state.sessionGeneration += 1; f.dispatch('nm:session-ended');}
    else await f.button('Close').fire('click');
    held.resolve(f.value.acknowledgement); await pending;
    assert.equal(signal.aborted, true); assert.ok(!f.body.textContent.includes('PRIVATE ORIGINAL'));
    assert.equal(f.urls.length, 0); assert.equal(f.find(node => node.tagName === 'pre'), undefined);
  });
}

test('returning to the case file revokes an opened blob and never bypasses shared transport or persists bytes', async () => {
  const f = fixture(record(Buffer.from('%PDF-1.7\ncontrolled fixture'), 'pdf'));
  await f.openFile(); await f.openOriginal(); await f.button('Back to attributed file').fire('click');
  assert.deepEqual(f.revoked, ['blob:checked-0']); assert.equal(f.find(node => node.tagName === 'iframe'), undefined);
  assert.ok(!/\bfetch\s*\(|localStorage|sessionStorage/.test(shipped));
});
