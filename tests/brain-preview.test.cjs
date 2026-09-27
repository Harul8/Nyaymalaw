/* The shipped controller, an explicit small DOM, and no provider/server calls. */
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {create, checkedPreview, checkedInstruction, parentLoops} = require('../nm/legal_brain/evaluate/brain-preview.js');
const {createHash, webcrypto} = require('node:crypto');
const MARKER = 'Private fictional-matter evaluation—not client advice or release.';
function workingStatus() {
  return {state: 'work_outstanding', total: 7, checked: 1, inapplicable: 4, not_assessed: 2,
    closes_matter: false, establishes_facts_or_law: false,
    operations: [{label: 'Only part of the requested material was available.', state: 'returned'}]};
}
function workingExplanation() {
  return {version: 'working-explanation-v1', state: 'checked_private_rationale',
    client_ready: false, normal_cutover: false, inventory_identity: 'a'.repeat(64),
    checks: {expected: 24, present: 24, checked: 24, not_assessed: 0, failed: 0},
    entries: [{id: 'entry-one', thread_id: 'thread-one', area: 'act_passages',
      package_identity: 'b'.repeat(64), text: 'Exact checked concise rationale.'}]};
}

test('working explanations require all actual channel checks and reject scratch fields', () => {
  const base = {...preview(), working_explanation: workingExplanation()};
  assert.equal(checkedPreview(base, 'matter_a', 'pv_turn_one').working_explanation.entries.length, 1);
  for (const mutation of [row => row.client_ready = true, row => row.normal_cutover = true,
    row => row.checks.checked = 23, row => row.checks.expected = 0,
    row => row.checks.failed = 1, row => row.state = 'unavailable',
    row => row.raw_reasoning = 'PRIVATE CANARY', row => row.entries[0].checker_reason = 'PRIVATE CANARY',
    row => row.entries[0].area = 'made_up', row => row.entries[0].package_identity = '',
    row => row.entries.push({...row.entries[0]})]) {
    const changed = structuredClone(base); mutation(changed.working_explanation);
    assert.throws(() => checkedPreview(changed, 'matter_a', 'pv_turn_one'), /working explanation/);
  }
});

test('unavailable working explanation is explicit and has no candidate or fallback words', () => {
  const row = workingExplanation(); row.state = 'unavailable'; row.entries = [];
  row.checks = {expected: 24, present: 0, checked: 0, not_assessed: 0, failed: 0};
  assert.equal(checkedPreview({...preview(), working_explanation: row},
    'matter_a', 'pv_turn_one').working_explanation.state, 'unavailable');
});

test('checked rationale renders as text in a collapsed secondary panel without replacing the response', async () => {
  const f = fixture(); await f.api.start();
  f.reply((path, options, standard) => {
    const result = standard(path, options);
    return path.includes('/brain/reviewed-preview/') && !path.endsWith('/seen')
      ? {...result, working_explanation: workingExplanation()} : result;
  });
  f.elements.message.value = 'Review the available material.'; await f.api.send();
  const panel = descendants(f.elements.messages).find(row => row.tagName === 'details'
    && row.children[0]?.textContent === 'Reasons supporting this work');
  assert.ok(panel); assert.notEqual(panel.open, true);
  assert.match(panel.textContent, /Exact checked concise rationale/);
  assert.match(f.elements.messages.textContent, /Exact checked words/);
});
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.handlers = {};
    this.style = {}; this.value = ''; this.scrollHeight = 46; this.hidden = false;
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(row => row.textContent).join(' '); }
  set innerHTML(_) { throw new Error('Untrusted HTML rendering is forbidden'); }
  append(...rows) { this.children.push(...rows); }
  appendChild(row) { this.children.push(row); return row; }
  replaceChildren(...rows) { this.text = ''; this.children = [...rows]; }
  addEventListener(type, handler) { (this.handlers[type] ||= []).push(handler); }
  async fire(type, fields = {}) {
    for (const handler of this.handlers[type] || []) await handler({preventDefault() {}, ...fields});
    await new Promise(resolve => setImmediate(resolve));
  }
}
function preview(turn = 'pv_turn_one', paragraphs = [{text: 'Exact checked words.', references: ['source:1']}]) {
  return {matter_id: 'matter_a', turn_id: turn, matter_version: 2,
    evaluation_only: true, released: false, client_ready: false, marker: MARKER,
    result_state: 'reviewed_private_candidate', paragraphs};
}

test('working status has an exact nonempty population and cannot assert matter closure', () => {
  const base = {...preview(), working_status: workingStatus()};
  assert.equal(checkedPreview(base, 'matter_a', 'pv_turn_one').working_status.total, 7);
  for (const mutation of [row => row.total = 0, row => row.closes_matter = true,
    row => row.establishes_facts_or_law = true, row => row.raw_thought = 'PRIVATE CANARY',
    row => row.checked = 99, row => row.state = 'complete_requested_work',
    row => row.operations[0].raw_result = 'PRIVATE CANARY']) {
    const changed = structuredClone(base); mutation(changed.working_status);
    assert.throws(() => checkedPreview(changed, 'matter_a', 'pv_turn_one'), /working-status/);
  }
});

test('work record stays collapsed and does not replace natural response paragraphs', async () => {
  const f = fixture(); await f.api.start(); await f.api.openMatter('matter_a');
  f.reply((path, options, standard) => {
    const result = standard(path, options);
    return path.includes('/brain/reviewed-preview/') && !path.endsWith('/seen')
      ? {...result, working_status: workingStatus()} : result;
  });
  f.elements.message.value = 'Review the available material.';
  await f.api.send();
  const article = f.elements.messages.children.find(row => row.children.some(item => item.tagName === 'details'));
  assert.ok(article);
  const panel = article.children.find(row => row.tagName === 'details');
  assert.notEqual(panel.open, true);
  assert.equal(panel.children[0].textContent, 'Work recorded');
  assert.match(panel.textContent, /remains outstanding/);
  assert.match(article.textContent, /Exact checked words/);
  assert.doesNotMatch(article.textContent, /PRIVATE CANARY/);
});
function fixture({sourceReader = null} = {}) {
  const ids = ['status', 'message', 'send', 'refresh', 'open-matter', 'stop-waiting', 'retry',
    'messages', 'history', 'matter-board', 'account-name', 'workspace', 'signin',
    'signin-message', 'matter-title', 'matter-id', 'matter-form', 'composer', 'check-session'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const doc = {cookie: 'nm_csrf=csrf%2Dtoken', getElementById: id => elements[id],
    createElement: tag => new Element(tag)};
  const timers = new Map(), events = {}, calls = [];
  let clock = 1000, counter = 0, handler = null;
  const win = {setTimeout: fn => { timers.set(++counter, fn); return counter; },
    clearTimeout: id => timers.delete(id), addEventListener: (type, fn) => { events[type] = fn; }};
  if (sourceReader) win.NmSourceReader = sourceReader;
  const server = {loops: [], version: 2, checked: null, failPost: false, post: null};
  const standard = (path, options) => {
    if (path === '/api/session') return {advocate: {id: 'advocate_a', name: 'Advocate'},
      access_window: {remaining_seconds: 1800}};
    if (path.endsWith('/brain/preview')) {
      const body = JSON.parse(options.body); server.post = body;
      if (server.failPost) throw new Error('Network unavailable');
      server.loops = [{turn_id: body.turn_id, terminal: true}];
      server.checked ||= preview(body.turn_id);
      return {turn_id: body.turn_id, matter_version: server.version, result_state: 'not_released',
        client_ready: false, raw_candidate: 'PRIVATE CANARY DO NOT DISPLAY'};
    }
    if (path.endsWith('/seen')) return {matter_id: 'matter_a', turn_id: server.checked.turn_id,
      receipt_id: 'display-receipt', display_identity: 'checked-display-identity',
      matter_version: server.version, result_state: 'private_preview_display_recorded',
      evaluation_only: true, released: false, client_ready: false};
    if (path.includes('/brain/reviewed-preview/')) return server.checked;
    if (path.endsWith('/loops')) return {loops: server.loops};
    if (path.endsWith('/cover')) return {matter_id: 'matter_a', version: server.version,
      title: 'Recorded title', client: 'Recorded client'};
    if (path === '/api/matters/matter_a') return {matter_id: 'matter_a', version: server.version,
      threads: [], agenda: {disputes: []}};
    throw new Error(`Unexpected fixture path ${path}`);
  };
  const api = create({document: doc, window: win, now: () => clock, search: '?matter_id=matter_a',
    crypto: {randomUUID: () => 'turn-one', subtle: webcrypto.subtle}, fetch: async (path, options) => {
      calls.push({path, options});
      const answer = handler ? await handler(path, options, standard) : standard(path, options);
      if (answer?.httpStatus) return {status: answer.httpStatus, ok: false, json: async () => ({})};
      return {status: 200, ok: true, json: async () => answer};
    }});
  return {api, doc, elements, server, calls, timers, events,
    now: value => {clock = value;}, reply: fn => {handler = fn;},
    text: () => Object.values(elements).map(row => row.textContent).join(' ')};
}
async function opened() { const f = fixture(); await f.api.start(); assert.equal(f.api.state.version, 2); return f; }
async function retry(f) { await f.elements.retry.fire('click'); while (f.api.state.active) await new Promise(resolve => setImmediate(resolve)); }

function descendants(node) { return [node, ...node.children.flatMap(descendants)]; }
test('checked private references open the shared reader through exact authenticated source bindings', async () => {
  const openedSources = [];
  const reader = {configure() {}, close() {}, open: (...args) => openedSources.push(args)};
  const f = fixture({sourceReader: reader}); await f.api.start();
  f.reply((path, options, standard) => path.includes('/sources/')
    ? {coverage: 'saved_passage', digest: 'a'.repeat(64), label: 'Captured provision', locator: 'source:1'}
    : standard(path, options));
  f.elements.message.value = 'Read the source.'; await f.api.send();
  const button = descendants(f.elements.messages).find(node => node.tagName === 'button'
    && node.textContent === 'Read retrieved passage 1');
  assert.ok(button); await button.fire('click');
  assert.equal(openedSources.length, 1);
  assert.deepEqual(openedSources[0][4], {privatePreview: true});
  assert.equal(openedSources[0][1].source.digest, 'a'.repeat(64));
  const call = f.calls.find(row => row.path.includes('/sources/'));
  assert.ok(call.path.endsWith('/sources/0?reference=source%3A1'));
  assert.equal(call.options.credentials, 'same-origin');
  assert.equal(call.options.cache, 'no-store');
  const before = f.calls.length; await f.api.openMatter('matter_b');
  const after = f.calls.length; await button.fire('click');
  assert.equal(f.calls.length, after); assert.ok(after > before);
});

test('a malformed source identity cannot open the reader even with checked words', async () => {
  const openedSources = [];
  const f = fixture({sourceReader: {configure() {}, close() {}, open: value => openedSources.push(value)}});
  await f.api.start();
  f.reply((path, options, standard) => path.includes('/sources/')
    ? {coverage: 'stored_document', digest: 'unknown', label: 'Unbound source'}
    : standard(path, options));
  f.elements.message.value = 'Read the source.'; await f.api.send();
  const button = descendants(f.elements.messages).find(node => node.tagName === 'button'
    && node.textContent === 'Read retrieved passage 1');
  await button.fire('click'); assert.equal(openedSources.length, 0);
  assert.ok(f.elements.status.textContent.includes('identity could not be verified'));
});

test('checked wording requires every exact private boundary, never a metadata author claim', () => {
  assert.equal(checkedPreview(preview(), 'matter_a', 'pv_turn_one').paragraphs.length, 1);
  const mutations = [data => {data.matter_id = 'other';}, data => {data.turn_id = 'other';},
    data => {data.matter_version = 0;}, data => {data.released = true;},
    data => {data.client_ready = true;}, data => {data.evaluation_only = false;},
    data => {data.marker = '';}, data => {data.result_state = 'not_released';},
    data => {data.paragraphs[0].text = ' ';}, data => {data.paragraphs[0].references = null;},
    data => {data.paragraphs[0].references = [42];}, data => {data.paragraphs = null;}];
  for (const mutate of mutations) {
    const data = structuredClone(preview()); mutate(data);
    assert.throws(() => checkedPreview(data, 'matter_a', 'pv_turn_one'));
  }
  assert.equal(checkedPreview({...preview(), result_state: 'checked_private_interaction'},
    'matter_a', 'pv_turn_one').paragraphs.length, 1);
});
test('history excludes derived child journals and requires distinct original completion identities', () => {
  const original = {turn_id: 'one', terminal: true};
  assert.deepEqual(parentLoops({loops: [original, {turn_id: 'one:checks'}, {turn_id: '../bad'}]}), [original]);
  assert.throws(() => parentLoops({loops: [original, original]}));
  assert.throws(() => parentLoops({loops: [{turn_id: 'one'}]}));
  assert.throws(() => parentLoops({}));
});
test('real controller clears and shrinks sent input; only checked GET words render as text', async () => {
  const f = await opened();
  f.elements.message.value = '<script>user text</script>';
  f.elements.message.style.height = '180px';
  f.server.checked = preview('pv_turn_one', [{text: '<img src=x onerror=alert(1)>', references: ['opaque:source']}]);
  await f.api.send();
  assert.equal(f.elements.message.value, ''); assert.equal(f.elements.message.style.height, '46px');
  assert.ok(f.text().includes('<img src=x onerror=alert(1)>'));
  assert.ok(!f.text().includes('PRIVATE CANARY'));
  assert.ok(f.text().includes('opaque:source'));
  assert.equal(f.api.state.pending, null);
  const post = f.calls.find(row => row.options.method === 'POST');
  assert.equal(post.options.headers['X-NM-CSRF'], 'csrf-token');
  assert.equal(post.options.credentials, 'same-origin'); assert.equal(post.options.redirect, 'error');
  assert.equal(post.options.cache, 'no-store');
  assert.deepEqual(f.server.post, {version: 2, turn_id: 'pv_turn_one',
    message: '<script>user text</script>', selected_issue_ids: []});
  const seen = f.calls.find(row => row.path.endsWith('/seen'));
  assert.equal(seen.options.body, '{}'); assert.equal(seen.options.headers['X-NM-CSRF'], 'csrf-token');
  assert.ok(f.calls.findIndex(row => row.path.endsWith('/seen'))
    > f.calls.findIndex(row => row.path.endsWith('/brain/reviewed-preview/pv_turn_one')));
});
test('raw candidate or unreviewed wording never leaks when the GET release contract is false', async () => {
  const f = await opened(); f.elements.message.value = 'Original user instruction';
  f.server.checked = {...preview(), result_state: 'not_released',
    paragraphs: [{text: 'UNREVIEWED PRIVATE CANARY', references: []}]};
  await f.api.send();
  assert.ok(!f.text().includes('UNREVIEWED PRIVATE CANARY'));
  assert.ok(!f.text().includes('PRIVATE CANARY DO NOT DISPLAY'));
  assert.ok(f.api.state.pending); assert.equal(f.elements.retry.hidden, false);
  assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
});
test('an empty checked result is explicitly unfinished, not falsely called checked wording', async () => {
  const f = await opened(); f.elements.message.value = 'Original instruction';
  f.server.checked = {...preview(), result_state: 'wording_review_pending', paragraphs: []};
  await f.api.send();
  assert.match(f.elements.status.textContent, /not fully checked/);
  assert.equal(f.api.state.pending, null);
  assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
});
test('missing CSRF permits no POST and releases its request controller without losing retry identity', async () => {
  const f = await opened(); f.doc.cookie = ''; f.elements.message.value = 'Instruction';
  await f.api.send();
  assert.equal(f.calls.filter(row => row.options.method === 'POST').length, 0);
  assert.equal(f.api.state.controllers.size, 0); assert.ok(f.api.state.pending);
  assert.match(f.elements.status.textContent, /session protection/);
});
test('transport retry reconciles history first and reuses the identical frozen request', async () => {
  const f = await opened(); f.server.failPost = true; f.elements.message.value = 'Instruction';
  await f.api.send(); const work = f.api.state.pending;
  assert.ok(Object.isFrozen(work)); assert.ok(Object.isFrozen(work.body.selected_issue_ids));
  f.server.failPost = false; await retry(f);
  const posts = f.calls.filter(row => row.path.endsWith('/brain/preview'));
  assert.equal(posts.length, 2); assert.equal(posts[0].options.body, posts[1].options.body);
  assert.equal(f.api.state.pending, null);
});
test('an existing in-progress turn is not resubmitted or silently declared resolved', async () => {
  const f = await opened(); f.server.failPost = true; f.elements.message.value = 'Instruction';
  await f.api.send(); f.server.loops = [{turn_id: 'pv_turn_one', terminal: false}];
  await retry(f);
  assert.equal(f.calls.filter(row => row.path.endsWith('/brain/preview')).length, 1);
  assert.ok(f.api.state.pending); assert.match(f.elements.status.textContent, /still in progress/);
  f.server.loops[0].terminal = true; f.server.checked = preview(); await retry(f);
  assert.equal(f.calls.filter(row => row.path.endsWith('/brain/preview')).length, 1);
  assert.equal(f.api.state.pending, null);
});
test('unresolved transport work cannot be discarded by refresh, navigation or a second instruction', async () => {
  const f = await opened(); f.server.failPost = true; f.elements.message.value = 'First';
  await f.api.send(); const pending = f.api.state.pending, count = f.calls.length;
  await f.api.openMatter('matter_b'); await f.api.openMatter('matter_a');
  f.elements.message.value = 'Second'; await f.api.send();
  assert.equal(f.api.state.pending, pending); assert.equal(f.api.state.matter, 'matter_a');
  assert.equal(f.calls.length, count); assert.equal(f.elements.refresh.disabled, true);
});
test('detached history buttons cannot issue cross-generation file reads', async () => {
  const f = await opened(); f.server.loops = [{turn_id: 'old', terminal: true}];
  await f.api.openMatter('matter_a'); const button = f.elements.history.children[0];
  await f.api.openMatter('matter_a'); const count = f.calls.length;
  await button.fire('click'); assert.equal(f.calls.length, count);
});
test('expired sessions cannot dispatch, and an actual 401 clears privileged DOM and draft text', async () => {
  const f = await opened(); f.now(f.api.state.expires + 1); const count = f.calls.length;
  f.elements.message.value = 'Unsent'; await f.api.send(); assert.equal(f.calls.length, count);
  f.timers.values().next().value();
  assert.equal(f.elements.message.value, ''); assert.equal(f.elements.workspace.hidden, true);
  const again = await opened(); again.elements.message.value = 'Instruction';
  again.reply((path, options, standard) => options.method === 'POST' ? {httpStatus: 401} : standard(path, options));
  await again.api.send();
  assert.equal(again.api.state.actor, null); assert.equal(again.elements.messages.children.length, 0);
  assert.equal(again.elements['account-name'].textContent, '');
});
test('a response that finishes after navigation cannot enter the current file', async () => {
  const f = await opened(); let resolve, began;
  const entered = new Promise(done => {began = done;});
  f.reply(async (path, options, standard) => {
    if (options.method === 'POST') {began(); return new Promise(done => {resolve = done;});}
    return standard(path, options);
  });
  f.elements.message.value = 'Instruction'; const sending = f.api.send(); await entered;
  f.api.endSession('Closed'); resolve({turn_id: 'pv_turn_one', matter_version: 2,
    result_state: 'not_released', client_ready: false}); await sending;
  assert.equal(f.elements.messages.children.length, 0); assert.equal(f.api.state.pending, null);
});
test('inconsistent board and cover versions do not establish a dispatchable matter', async () => {
  const f = fixture(); f.reply((path, options, standard) => {
    const result = standard(path, options); return path.endsWith('/cover') ? {...result, version: 3} : result;
  });
  await f.api.start(); assert.equal(f.api.state.version, null); assert.equal(f.elements.send.disabled, true);
});
test('a refused display acknowledgement stays visibly missing, with no author resubmission', async () => {
  const f = await opened(); f.elements.message.value = 'Instruction';
  f.reply((path, options, standard) => path.endsWith('/seen') ? {httpStatus: 409} : standard(path, options));
  await f.api.send();
  assert.ok(f.text().includes('Exact checked words.'));
  assert.match(f.elements.status.textContent, /display history was not recorded/);
  assert.ok(f.text().includes('Later work may not know'));
  assert.equal(f.calls.filter(row => row.path.endsWith('/brain/preview')).length, 1);
});
test('a forged display receipt cannot assert client release or successful display history', async () => {
  const f = await opened(); f.elements.message.value = 'Instruction';
  f.reply((path, options, standard) => {
    const result = standard(path, options); return path.endsWith('/seen') ? {...result, released: true} : result;
  });
  await f.api.send();
  assert.match(f.elements.status.textContent, /display history was not recorded/);
});
test('a stopped-work GET explains the interruption as text without implying a finished answer', async () => {
  const f = await opened(); f.elements.message.value = 'Instruction';
  const message = 'The provider connection was interrupted. <unsafe markup> No legal answer was produced.';
  f.server.checked = {...preview(), result_state: 'work_stopped', paragraphs: [], message,
    proposal: {text: 'PRIVATE STOPPED DRAFT CANARY'}};
  await f.api.send();
  assert.equal(f.elements.status.textContent, message);
  assert.ok(f.elements.messages.textContent.includes(message));
  assert.ok(!f.text().includes('PRIVATE STOPPED DRAFT CANARY'));
  assert.ok(!f.text().includes('PRIVATE CANARY DO NOT DISPLAY'));
  assert.ok(!f.elements.status.textContent.includes('instruction finished'));
  assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
  assert.equal(f.api.state.pending, null);
});
test('a stopped-work label cannot expose proposed paragraphs or omit its public explanation', () => {
  for (const message of [null, '', ' ', 42, 'x'.repeat(2001)]) {
    assert.throws(() => checkedPreview({...preview(), result_state: 'work_stopped',
      paragraphs: [], message}, 'matter_a', 'pv_turn_one'));
  }
  assert.throws(() => checkedPreview({...preview(), result_state: 'work_stopped',
    message: 'Public interruption'}, 'matter_a', 'pv_turn_one'));
});
test('reopening a saved stopped turn gives its public reason without another author request', async () => {
  const f = await opened(); f.server.failPost = true; f.elements.message.value = 'Instruction';
  await f.api.send(); f.server.loops = [{turn_id: 'pv_turn_one', terminal: true}];
  const message = 'The approved work budget was exhausted. No legal answer was produced.';
  f.server.checked = {...preview(), result_state: 'work_stopped', paragraphs: [], message};
  await retry(f);
  assert.equal(f.elements.status.textContent, message);
  assert.equal(f.calls.filter(row => row.path.endsWith('/brain/preview')).length, 1);
  assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
  assert.equal(f.api.state.pending, null);
});
function instruction(text, provenance = 'sealed_turn_admission') {
  return {state: 'recorded', text,
    text_identity: createHash('sha256').update(JSON.stringify(text), 'utf8').digest('hex'),
    provenance, material_kind: 'advocate_original_instruction',
    trust: 'user_instruction_not_established_fact_or_legal_authority'};
}
function userBubbles(f) { return f.elements.messages.children.filter(row => row.className === 'message user'); }
test('saved input requires the closed original-instruction contract, never model or tool words', () => {
  assert.equal(checkedInstruction(instruction('Supplied original words')).text, 'Supplied original words');
  const changes = [row => {row.state = 'model_response';}, row => {row.provenance = 'tool_result';},
    row => {row.material_kind = 'system_prompt';}, row => {row.trust = 'established_fact';},
    row => {row.text = ' ';}, row => {row.text_identity = 'not a digest';},
    row => {row.raw_prompt = 'raw fallback';}];
  for (const change of changes) {
    const row = instruction('Supplied words'); change(row); assert.throws(() => checkedInstruction(row));
  }
  assert.equal(checkedInstruction(undefined), null);
  assert.equal(checkedInstruction({state: 'not_recorded', text: '', text_identity: '',
    provenance: 'not_recorded', material_kind: 'advocate_original_instruction',
    trust: 'user_instruction_not_established_fact_or_legal_authority'}), null);
});
test('freshly returned saved original words do not duplicate the current escaped user bubble', async () => {
  const f = await opened(); const text = '<script>Original advocate words</script>';
  f.elements.message.value = text;
  f.server.checked = {...preview(), original_instruction: instruction(text)};
  await f.api.send();
  assert.equal(userBubbles(f).length, 1); assert.equal(userBubbles(f)[0].textContent, text);
  assert.equal(f.api.state.pending, null);
});
test('refresh and saved-history read reopen original input from GET with no paid author call', async () => {
  const f = await opened(); const text = 'Earlier original input, not a factual finding.';
  f.server.checked = {...preview('saved_turn'), result_state: 'work_stopped', paragraphs: [],
    message: 'The provider request stopped.', original_instruction: instruction(text, 'sealed_first_dispatch')};
  f.server.loops = [{turn_id: 'saved_turn', terminal: true}];
  await f.api.openMatter('matter_a'); await f.elements.history.children[0].fire('click');
  assert.equal(userBubbles(f).length, 1); assert.equal(userBubbles(f)[0].textContent, text);
  assert.equal(f.calls.filter(row => row.options.method === 'POST').length, 0);
  await f.api.openMatter('matter_a'); await f.elements.history.children[0].fire('click');
  assert.equal(userBubbles(f).length, 1); assert.equal(userBubbles(f)[0].textContent, text);
});
test('historical missing input stays unavailable and raw prompt or tool fields are never a fallback', async () => {
  const f = await opened(); f.server.loops = [{turn_id: 'saved_turn', terminal: true}];
  f.server.checked = {...preview('saved_turn'), paragraphs: [], result_state: 'wording_review_pending',
    raw_prompt: 'PRIVATE RAW PROMPT CANARY', tool_result: 'PRIVATE TOOL CANARY',
    original_instruction: {state: 'not_recorded', text: '', text_identity: '',
      provenance: 'not_recorded', material_kind: 'advocate_original_instruction',
      trust: 'user_instruction_not_established_fact_or_legal_authority'}};
  await f.api.openMatter('matter_a'); await f.elements.history.children[0].fire('click');
  assert.equal(userBubbles(f).length, 0); assert.ok(f.text().includes('original instruction is unavailable'));
  assert.ok(!f.text().includes('PRIVATE RAW PROMPT CANARY')); assert.ok(!f.text().includes('PRIVATE TOOL CANARY'));
});
test('an altered original text digest cannot display reconstructed user words', async () => {
  const f = await opened(); f.server.loops = [{turn_id: 'saved_turn', terminal: true}];
  f.server.checked = {...preview('saved_turn'), original_instruction:
    {...instruction('Original exact words'), text: 'ALTERED ORIGINAL CANARY'}};
  await f.api.openMatter('matter_a'); await f.elements.history.children[0].fire('click');
  assert.equal(userBubbles(f).length, 0); assert.ok(!f.text().includes('ALTERED ORIGINAL CANARY'));
  assert.match(f.elements.status.textContent, /input identity changed/);
});
test('a failed wording review exposes only its public reason while preserving exact original input', async () => {
  const f = await opened(); const words = 'Exact advocate input'; f.elements.message.value = words;
  const message = 'The wording check could not verify the entire response. No unchecked wording was shown.';
  f.server.checked = {...preview(), result_state: 'wording_review_failed', paragraphs: [], message,
    original_instruction: instruction(words), proposed_text: 'PRIVATE FAILED WORDING CANARY'};
  await f.api.send();
  assert.equal(f.elements.status.textContent, message);
  assert.equal(userBubbles(f).length, 1); assert.equal(userBubbles(f)[0].textContent, words);
  assert.ok(!f.text().includes('PRIVATE FAILED WORDING CANARY'));
  assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
  assert.equal(f.api.state.pending, null); assert.equal(f.elements.send.disabled, false);
});
test('a failed wording-review label cannot display private paragraphs or an invalid public message', () => {
  for (const message of [null, '', ' ', 5, 'x'.repeat(2001)]) {
    assert.throws(() => checkedPreview({...preview(), result_state: 'wording_review_failed',
      paragraphs: [], message}, 'matter_a', 'pv_turn_one'));
  }
  assert.throws(() => checkedPreview({...preview(), result_state: 'wording_review_failed',
    message: 'Public reason'}, 'matter_a', 'pv_turn_one'));
});
test('saved terminal review failure resolves transport retry and restores input without author resubmission', async () => {
  const f = await opened(); f.server.failPost = true; const words = 'Original failed request';
  f.elements.message.value = words; await f.api.send();
  f.server.loops = [{turn_id: 'pv_turn_one', terminal: true}];
  const message = 'The saved response did not pass its complete wording check.';
  f.server.checked = {...preview(), result_state: 'wording_review_failed', paragraphs: [], message,
    original_instruction: instruction(words)};
  await retry(f);
  assert.equal(f.elements.status.textContent, message);
  assert.equal(f.calls.filter(row => row.path.endsWith('/brain/preview')).length, 1);
  assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
  assert.equal(f.api.state.pending, null); assert.equal(f.elements.send.disabled, false);
  assert.equal(userBubbles(f).length, 1);
  await f.api.openMatter('matter_a'); await f.elements.history.children[0].fire('click');
  assert.equal(userBubbles(f).length, 1); assert.equal(userBubbles(f)[0].textContent, words);
  assert.ok(f.elements.messages.textContent.includes(message));
});

test('every declared public failure keeps its reason on reopen without displaying unchecked words', async () => {
  for (const result_state of ['work_stopped', 'wording_review_failed', 'proposal_binding_failed']) {
    const f = await opened();
    const words = 'Original instruction to assess the recorded file';
    const message = 'The saved response could not be checked; the instruction is preserved.';
    f.server.loops = [{turn_id: 'saved_turn', terminal: true}];
    f.server.checked = {...preview('saved_turn'), result_state, paragraphs: [], message,
      original_instruction: instruction(words), proposed_text: 'UNREVIEWED CANARY'};
    await f.api.openMatter('matter_a'); await f.elements.history.children[0].fire('click');
    assert.ok(f.elements.messages.textContent.includes(message), result_state);
    assert.equal(userBubbles(f)[0].textContent, words);
    assert.ok(!f.text().includes('UNREVIEWED CANARY'));
    assert.equal(f.calls.filter(row => row.path.endsWith('/brain/preview')).length, 0);
    assert.equal(f.calls.filter(row => row.path.endsWith('/seen')).length, 0);
  }
});

test('no public-failure state admits unchecked paragraphs or an empty unbounded reason', () => {
  for (const result_state of ['work_stopped', 'wording_review_failed', 'proposal_binding_failed']) {
    for (const message of [undefined, null, '', ' ', 7, 'x'.repeat(2001)]) {
      assert.throws(() => checkedPreview({...preview(), result_state, paragraphs: [], message},
        'matter_a', 'pv_turn_one'), result_state);
    }
    assert.throws(() => checkedPreview({...preview(), result_state, message: 'Public reason'},
      'matter_a', 'pv_turn_one'), result_state);
  }
});
