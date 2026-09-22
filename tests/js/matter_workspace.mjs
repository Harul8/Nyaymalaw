/* Runs the shipped browser controller; small DOM, no network, no npm. */
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import vm from 'node:vm';

const original = fs.readFileSync('frontend/matter-workspace.js', 'utf8');
const mode = process.argv[2];
function walk(el) { return [el, ...el.children.flatMap(walk)]; }
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.listeners = {}; this.value = ''; this.disabled = false; this.open = false; this.attributes = {}; this.className = ''; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(el => el.textContent).join(' '); }
  append(...els) { for (const el of els) { el.parentElement = this; this.children.push(el); } }
  prepend(...els) { for (const el of [...els].reverse()) { el.parentElement = this; this.children.unshift(el); } }
  after(el) { this.parentElement.append(el); }
  replaceChildren(...els) { this.text = ''; this.children = []; this.append(...els); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  async fire(type) { for (const fn of this.listeners[type] || []) await fn({ preventDefault() {} }); }
  querySelectorAll(tag) { return walk(this).filter(el => el.tagName === tag); }
  showModal() { this.open = true; }
  close() { this.open = false; for (const fn of this.listeners.close || []) fn(); }
  get classList() { return { add: name => { this.className += ` ${name}`; } }; }
  get elements() { return { namedItem: name => walk(this).find(el => el.name === name) }; }
  reportValidity() { return walk(this).every(el => !el.required || el.disabled || String(el.value).trim()); }
}
function fixture(source = original) {
  const body = new Element('body');
  for (const id of ['workspace-focus', 'workspace-menu', 'save-status']) { const el = new Element('div'); el.id = id; body.append(el); }
  const events = {};
  const state = { matterId: 'matter_a', advocate: 'adv_a', ended: false, matterReady: true, sessionGeneration: 1, railGeneration: 1 };
  const calls = [], sends = [], boards = [];
  let respond = () => { throw Error('Unexpected API request'); };
  const window = { addEventListener: (name, handler) => { (events[name] ||= []).push(handler); } };
  const dispatch = name => (events[name] || []).forEach(fn => fn());
  const sandbox = { document: { body, createElement: tag => new Element(tag), getElementById: id => walk(body).find(el => el.id === id) }, window, crypto: { randomUUID },
    state, activeDelivery: null, api: async (url, options) => { calls.push({ url, options }); return respond(url, options); },
    send: async (message, options) => { sends.push({ message, options }); },
    showThreadBoard: async (id, options) => { assert.equal(options.restore, true, 'Successful record changes must restore the historical conversation, not retain unqualified live advice'); boards.push({ id, options }); state.railGeneration += 1; dispatch('nm:matter-changed'); } };
  vm.runInNewContext(source, sandbox);
  const find = predicate => walk(body).find(predicate);
  return { body, state, calls, sends, boards, dispatch, sandbox,
    reply: fn => { respond = fn; }, find,
    button: text => { const found = find(el => el.tagName === 'button' && el.textContent === text); assert.ok(found, text); return found; },
    input: name => { const found = find(el => el.name === name); assert.ok(found, name); return found; },
    get dialog() { return find(el => el.tagName === 'dialog'); } };
}
const cover = () => ({ state: 'ok', matter_id: 'matter_a', title: 'Example file', version: 2,
  client_state: 'not_recorded', posture_state: 'not_established', stage: 'opening', deadline_assessment: 'not_assessed',
  deadline_said: 'Not established — service date unknown', commission: null });
const commission = () => ({ state: 'ok', matter_id: 'matter_a', version: 2, commission: null, history: [], refusals: [] });
const declared = () => ({ actor_id: 'adv_a', basis: 'Immediate protective referral requested', declared_at: '2026-09-12T10:00:00Z',
  expires_at: '2026-09-12T11:00:00Z', outstanding: ['capacity not established'], permitted_scope: 'protective or referral guidance only', revoked_at: null, revoked_by: '' });
const emergency = live => ({ state: 'ok', matter_id: 'matter_a', version: 2, governing_ref: live ? 'a'.repeat(64) : null, governing: live ? declared() : null,
  said: live ? 'Emergency exception live until 11:00Z' : 'No emergency exception is live', history: [], permits_substance: false });
function replyCover(f) { f.reply(url => url.endsWith('/commission') ? commission() : cover()); }
async function edit(f) { replyCover(f); await f.button('Matter cover & instructions').fire('click'); await f.button('Record the instructions').fire('click'); }
function fill(f) {
  for (const [name, value] of Object.entries({ objective: 'Protect the recorded interest', scope: 'Review the supplied agreement', work_product: 'advice',
    instructing_id: 'solicitor_1', instructing_description: 'Instructing solicitor', instructing_capacity: 'instructing',
    deciding_id: 'client_1', deciding_description: 'The client', deciding_capacity: 'deciding',
    deadline_reason: 'Service date unknown', because: 'Initial instruction', exclusions: 'No filing\nNo settlement' })) f.input(name).value = value;
}
if (mode === 'cover') {
  const f = fixture(); replyCover(f);
  await f.button('Matter cover & instructions').fire('click');
  for (const text of ['Not recorded', 'Not established', 'service date unknown', 'No commission is recorded', 'does not grant authority', 'No earlier versions recorded']) assert.ok(f.dialog.textContent.includes(text), text);
  assert.equal(f.calls.length, 2);
  assert.equal(f.sends.length, 0);
  const live = fixture();
  live.reply(url => url.endsWith('/commission') ? commission() : { ...cover(),
    client_state: 'recorded', client: 'Synthetic CedarClient', last_activity: '2026-09-12',
    posture_state: 'mixed', posture: 'mixed',
    case_deadlines: { deadline_assessment: 'incomplete', next_deadline: '2026-10-01',
      deadline_entries: [{ status: 'passed', on: '2026-01-01', action: 'Review the expired window', owner: 'Advocate', source: 'Saved order', consequence: 'Window lost', thread: 'thread_a' },
        { status: 'not_computed', on: null, action: 'Confirm service date', owner: 'Advocate', source: 'Supplied notice', consequence: 'Window uncertain', thread: 'thread_b' }],
      deadline_unreadable: [{ reason: 'saved deadline row unreadable' }], deadline_unassessed: ['thread_b'] } });
  await live.button('Matter cover & instructions').fire('click');
  for (const text of ['Synthetic CedarClient', '2026-09-12', 'Different roles across disputes', 'Case deadlines',
    'Instruction deadline', 'service date unknown', '2026-10-01', 'passed', '2026-01-01', 'Date not established',
    'not fully assessed', 'saved deadline row unreadable', 'thread_b']) assert.ok(live.dialog.textContent.includes(text), text);
  assert.ok(!live.dialog.textContent.includes('The assessed case register contains no deadlines'));
} else if (mode === 'commission') {
  const f = fixture(); await edit(f); fill(f);
  f.state.matterVersion = 99; // The live state is not what this form reviewed.
  f.reply((url, options) => {
    assert.ok(url.endsWith('/commission')); assert.equal(options.method, 'POST');
    const p = JSON.parse(options.body);
    assert.equal(p.expected_version, 2);
    assert.equal(p.instructing.party_id, 'solicitor_1'); assert.equal(p.deciding.party_id, 'client_1');
    assert.equal(p.deciding.capacity, 'deciding'); assert.equal(p.instructing.capacity, 'instructing');
    assert.deepEqual(p.exclusions, ['No filing', 'No settlement']);
    assert.deepEqual(p.deadline, { kind: 'unknown', reason: 'Service date unknown' });
    assert.equal(p.because, 'Initial instruction'); assert.equal('acting_as' in p, false);
    return { matter_id: 'matter_a', state: 'commission_recorded', reopened: true };
  });
  await f.input('objective').parentElement.parentElement.fire('submit');
  assert.equal(f.boards.length, 1); assert.equal(f.sends.length, 0); assert.equal(f.dialog.open, false);
  assert.ok(f.body.textContent.includes('reopened scope assessment'));
} else if (mode === 'casefile') {
  const f = fixture();
  f.reply(() => ({ state: 'ok', matter_id: 'matter_a', repetition_upgrades: ['fact_2 needs a source'], split_disputes: [],
    entries: [{ fact_id: 'fact_1', version: 1, statement: '<script>not executable</script>', certainty: 'asserted', confirmed: 'not_asked',
      attribution: { said: 'agreement page 3', document: 'agreement', page: 3, read_quality: 'clear', inspectable: true }, conflicts_with: ['fact_2'], superseded_by: 'fact_3' }] }));
  await f.button('Attributed file').fire('click');
  for (const text of ['Recorded statement 1 · revision 1', 'Record reference', 'fact_1']) assert.ok(f.dialog.textContent.includes(text), text);
  for (const text of ['asserted', 'not asked', 'clear', 'fact_2', 'fact_3', 'agreement page 3', 'Opening the original is not available', '<script>not executable</script>']) assert.ok(f.dialog.textContent.includes(text), text);
  assert.equal(walk(f.dialog).filter(el => ['a', 'script'].includes(el.tagName)).length, 0);
} else if (mode === 'declaration') {
  const f = fixture(); f.reply(() => emergency(false));
  await f.button('Protective handoff').fire('click');
  f.input('basis').value = 'The limitation date requires immediate review'; f.input('hours').value = '2';
  f.reply((url, options) => { const payload = JSON.parse(options.body); assert.match(payload.request_key, /^[a-f0-9-]{36}$/); assert.deepEqual(payload, { request_key: payload.request_key, basis: 'The limitation date requires immediate review', hours: 2 }); return { matter_id: 'matter_a', state: 'emergency_declared', request_key: payload.request_key, replayed: false }; });
  await f.input('basis').parentElement.parentElement.fire('submit');
  assert.equal(f.sends.length, 0); assert.equal(f.boards.length, 1);
  assert.ok(f.body.textContent.includes('no handoff was requested'));
} else if (mode === 'protective') {
  for (const live of [false, true]) {
    const f = fixture(); f.reply(() => emergency(true));
    await f.button('Protective handoff').fire('click');
    f.input('protective_request').value = 'Identify the appropriate urgent referral';
    f.reply(() => emergency(live));
    await f.input('protective_request').parentElement.parentElement.fire('submit');
    assert.equal(f.sends.length, live ? 1 : 0);
    if (live) { assert.equal(f.sends[0].options.workProduct, 'protective_triage'); assert.equal(f.sends[0].message, 'Identify the appropriate urgent referral'); }
    else assert.ok(f.dialog.textContent.includes('No live exception remains'));
    assert.equal(f.calls.filter(call => call.options?.method === 'POST').length, 0);
  }
} else if (mode === 'revoke') {
  const f = fixture(); f.reply(() => emergency(true));
  await f.button('Protective handoff').fire('click');
  f.state.matterVersion = 99; // Later mutable state must not change this reviewed command.
  f.reply((url, options) => { assert.deepEqual(JSON.parse(options.body), { revoke: true, expected_version: 2, governing_ref: 'a'.repeat(64) }); return { matter_id: 'matter_a', state: 'emergency_revoked', version: 3, governing_ref: 'a'.repeat(64) }; });
  await f.button('End the protective exception').fire('click');
  assert.ok(f.body.textContent.includes('Protective exception ended')); assert.equal(f.sends.length, 0);
} else if (mode.startsWith('confirmation_')) {
  const operation = mode.slice('confirmation_'.length);
  const states = { commission: 'commission_recorded', declaration: 'emergency_declared', revoke: 'emergency_revoked' };
  async function probe(kind, response, source = original) {
    const f = fixture(source);
    let submit;
    if (kind === 'commission') {
      await edit(f); fill(f);
      submit = () => f.input('objective').parentElement.parentElement.fire('submit');
    } else {
      f.reply(() => emergency(kind === 'revoke'));
      await f.button('Protective handoff').fire('click');
      if (kind === 'declaration') {
        f.input('basis').value = 'A synthetic urgent referral';
        submit = () => f.input('basis').parentElement.parentElement.fire('submit');
      } else submit = () => f.button('End the protective exception').fire('click');
    }
    f.reply((url, options) => response && kind === 'declaration'
      ? { request_key: JSON.parse(options.body).request_key, replayed: false, ...response } : response);
    await submit();
    assert.equal(f.boards.length, 0, 'An unconfirmed write refreshed as success');
    assert.equal(f.dialog.open, true, 'An unconfirmed write closed the record');
    assert.equal(f.find(el => el.id === 'save-status').textContent, '');
    assert.ok(f.dialog.textContent.includes('not confirmed') || f.dialog.textContent.includes('could not be confirmed'));
    assert.equal(f.sends.length, 0);
  }
  if (operation === 'mutation') {
    const guard = 'result.state !== expectedState';
    assert.ok(original.includes(guard));
    const mutated = original.replace(guard, 'false');
    assert.notEqual(mutated, original);
    await assert.rejects(() => probe('declaration', { matter_id: 'matter_a', state: 'unknown' }, mutated), assert.AssertionError);
  } else {
    assert.ok(states[operation]);
    for (const state of [undefined, null, true, [], {}, 'unknown', 'ok']) {
      await probe(operation, { matter_id: 'matter_a', state, reopened: false });
    }
    await probe(operation, null);
    if (operation === 'commission') await probe(operation, { matter_id: 'matter_a', state: states[operation], reopened: 'false' });
  }
} else if (mode === 'declaration_retry') {
  const f = fixture();
  const offered = [];
  async function openDeclaration() {
    f.reply(() => emergency(false)); await f.button('Protective handoff').fire('click');
    f.input('basis').value = 'The same unresolved danger'; f.input('hours').value = '1';
  }
  await openDeclaration();
  f.reply((url, options) => { offered.push(JSON.parse(options.body)); throw Error('synthetic lost response'); });
  await f.input('basis').parentElement.parentElement.fire('submit');
  assert.equal(f.dialog.open, true); assert.equal(f.boards.length, 0);
  await f.button('Close').fire('click');
  await openDeclaration();
  f.reply((url, options) => { const payload = JSON.parse(options.body); offered.push(payload);
    return { matter_id: 'matter_a', state: 'emergency_declared', request_key: payload.request_key, replayed: true }; });
  await f.input('basis').parentElement.parentElement.fire('submit');
  assert.equal(offered.length, 2); assert.deepEqual(offered[1], offered[0]);
  assert.ok(f.body.textContent.includes('original expiry was not renewed'));
  await openDeclaration();
  f.reply((url, options) => { const payload = JSON.parse(options.body); offered.push(payload);
    return { matter_id: 'matter_a', state: 'emergency_declared', request_key: payload.request_key, replayed: false }; });
  await f.input('basis').parentElement.parentElement.fire('submit');
  assert.equal(offered.length, 3); assert.notEqual(offered[2].request_key, offered[0].request_key);
  assert.equal(f.sends.length, 0);
} else if (mode === 'urgency' || mode === 'urgency_retry') {
  const f = fixture(); const offered = [];
  const view = version => ({ ...emergency(false), version, urgency_register: { state: 'ok', entries: [],
    classes: [{ class: 'personal_safety', label: 'Personal safety', assessment: 'not_assessed' }],
    taxonomy_basis: 'Supplied fixture choice; automatic assessment remains unavailable' } });
  async function openUrgency(version) {
    f.reply(() => view(version)); await f.button('Protective handoff').fire('click');
    assert.ok(f.dialog.textContent.includes('not an all-clear'));
    await f.button('Record a danger manually').fire('click');
    f.input('urgency-class').value = 'personal_safety'; f.input('urgency-basis').value = 'Supplied danger';
    f.input('urgency-action').value = 'Contact responsible advocate';
    f.input('urgency-owner').value = 'Instructing advocate';
  }
  await openUrgency(2);
  const form = () => f.input('urgency-basis').parentElement.parentElement;
  const before = f.calls.length;
  await form().fire('submit');
  assert.equal(f.calls.length, before); assert.ok(f.dialog.textContent.includes('explain why it is unknown'));
  f.input('urgency-due-unknown').value = 'Order not yet supplied';
  f.reply((url, options) => {
    const payload = JSON.parse(options.body); offered.push(payload);
    if (mode === 'urgency_retry') throw Error('synthetic lost response after commit');
    return { matter_id: 'matter_a', state: 'urgency_recorded', request_key: payload.request_key,
      urgency_id: 'urgency_a', version: 3, replayed: false };
  });
  await form().fire('submit');
  assert.equal(offered[0].expected_version, 2); assert.equal(offered[0].urgency.due, null);
  assert.equal(offered[0].urgency.unknowns.due, 'Order not yet supplied');
  if (mode === 'urgency_retry') {
    assert.equal(f.boards.length, 0); await f.button('Close').fire('click');
    await openUrgency(3); f.input('urgency-due-unknown').value = 'Order not yet supplied';
    f.reply((url, options) => {
      const payload = JSON.parse(options.body); offered.push(payload);
      return { matter_id: 'matter_a', state: 'urgency_recorded', request_key: payload.request_key,
        urgency_id: 'urgency_a', version: 3, replayed: true };
    });
    await form().fire('submit'); assert.deepEqual(offered[1], offered[0]);
    assert.ok(f.body.textContent.includes('Earlier urgency change recovered'));
  }
  assert.equal(f.boards.length, 1); assert.equal(f.sends.length, 0);
  const saved = view(3);
  saved.urgency_register.entries = [{ urgency_id: 'urgency_a', class: 'personal_safety', state: 'live',
    basis: 'Supplied danger', action: 'Contact responsible advocate', owner: 'Instructing advocate',
    due: null, unknowns: { due: 'Order not yet supplied' }, raised_by: 'adv_a', raised_at: '2026-09-12T10:00:00Z' }];
  f.reply(() => saved); await f.button('Protective handoff').fire('click');
  assert.ok(f.dialog.textContent.includes('Unknown — Order not yet supplied'));
  await f.button('Record explicit resolution').fire('click');
  f.input('urgency-resolution').value = 'Responsible advocate confirmed the danger was addressed';
  f.reply((url, options) => {
    const payload = JSON.parse(options.body); assert.equal(payload.urgency_command, 'resolve');
    assert.equal(payload.urgency_id, 'urgency_a'); assert.equal(payload.expected_version, 3);
    assert.ok(payload.request_key); assert.ok(payload.resolution_basis);
    return { matter_id: 'matter_a', state: 'urgency_resolved', urgency_id: 'urgency_a',
      request_key: payload.request_key, version: 4, replayed: false };
  });
  await f.input('urgency-resolution').parentElement.parentElement.fire('submit');
  assert.equal(f.boards.length, 2); assert.equal(f.sends.length, 0);
} else if (mode === 'cover_changed') {
  for (const version of [undefined, -1, 3]) {
    const f = fixture();
    f.reply(url => url.endsWith('/commission') ? { ...commission(), version } : cover());
    await f.button('Matter cover & instructions').fire('click');
    assert.ok(f.dialog.textContent.includes('changed while this view loaded'));
    assert.equal(f.find(el => el.tagName === 'button' && el.textContent === 'Record the instructions'), undefined);
  }
} else if (mode === 'stale_read' || mode === 'mutation') {
  let source = original;
  if (mode === 'mutation') {
    const anchor = 'return dialog.open && !state.ended && !!state.advocate';
    assert.ok(source.includes(anchor));
    source = source.replace(anchor, 'return true; /*');
    const end = '&& token.matter === state.matterId && token.view === generation;';
    assert.ok(source.includes(end)); source = source.replace(end, end + ' */');
  }
  async function probe(axis) {
    const f = fixture(source); let resolve;
    f.reply(() => new Promise(done => { resolve = done; }));
    const pending = f.button('Attributed file').fire('click');
    if (axis === 'session') f.state.sessionGeneration += 1;
    if (axis === 'rail') f.state.railGeneration += 1;
    if (axis === 'matter') f.state.matterId = 'matter_b';
    if (axis === 'dialog') await f.button('Close').fire('click');
    resolve({ state: 'ok', matter_id: 'matter_a', repetition_upgrades: [], split_disputes: [], entries: [{ fact_id: 'STALE_SECRET', version: 1, statement: 'Late private material', certainty: 'asserted', confirmed: 'not_asked', attribution: {}, conflicts_with: [] }] });
    await pending;
    assert.ok(!f.body.textContent.includes('STALE_SECRET'));
  }
  if (mode === 'mutation') await assert.rejects(() => probe('session'), assert.AssertionError);
  else for (const axis of ['session', 'rail', 'matter', 'dialog']) await probe(axis);
} else if (mode === 'stale_write') {
  const f = fixture(); await edit(f); fill(f); let resolve;
  f.reply(() => new Promise(done => { resolve = done; }));
  const pending = f.input('objective').parentElement.parentElement.fire('submit');
  f.state.matterId = 'matter_b'; f.state.railGeneration += 1; f.dispatch('nm:matter-changed');
  resolve({ matter_id: 'matter_a', state: 'commission_recorded' }); await pending;
  assert.equal(f.boards.length, 0); assert.equal(f.dialog.textContent.includes('Protect the recorded interest'), false);
} else if (mode === 'wipe') {
  const f = fixture(); await edit(f); fill(f);
  f.state.ended = true; f.state.advocate = null; f.state.matterId = null; f.state.sessionGeneration += 1;
  f.dispatch('nm:session-ended');
  assert.equal(f.dialog.open, false); assert.equal(walk(f.dialog).filter(el => el.name).length, 0);
  assert.equal(f.find(el => el.id === 'matter-tools').hidden, true);
} else throw Error(`Unknown witness: ${mode}`);
console.log(`PASS matter workspace ${mode}`);
