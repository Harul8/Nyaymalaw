/** Exercise bounded account preferences, explicit approval and session-safe UI state. */
'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {create, checkedMemory} = require('../nm/legal_brain/understand/advocate-preferences.js');

class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.listeners = {}; this.attributes = {};
    this.value = ''; this.checked = false; this.disabled = false; this.open = false; this._text = '';
  }
  set textContent(text) { this._text = String(text); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(' '); }
  set innerHTML(_value) { throw new Error('Preference content must render as text.'); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this.children = nodes; this._text = ''; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  addEventListener(kind, handler) { (this.listeners[kind] ||= []).push(handler); }
  async fire(kind) { for (const handler of this.listeners[kind] || []) await handler({target: this}); }
  showModal() { this.open = true; }
  close() { this.open = false; for (const handler of this.listeners.close || []) handler({target: this}); }
}
const supported = {
  advice_length: ['short', 'standard', 'detailed'], authorities_position: ['inline', 'end'],
  advice_form: ['prose', 'bullets'], draft_date_format: ['iso', 'day_month_year'],
  court_ids: ['supreme_court', 'hc_telangana', 'hc_andhra_pradesh'],
  standing_instructions: ['explain_abbreviations', 'show_action_owners', 'include_short_summary'],
};
function snapshot(settings = {}, version = 0) {
  return {version, state: Object.keys(settings).length ? 'saved' : 'empty', settings,
    supported: structuredClone(supported), courts: {supreme_court: 'Supreme Court of India',
      hc_telangana: 'High Court for the State of Telangana', hc_andhra_pradesh: 'High Court of Andhra Pradesh'},
    limits: 'Only listed settings are supported. No client facts, free text or unlisted courts.',
    approved_at: version ? '2026-09-27T00:00:00+00:00' : null};
}
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; }
function descendants(node) { return node.children.flatMap(child => [child, ...descendants(child)]); }
function fixture(initial = snapshot()) {
  const elements = {};
  for (const id of ['dialog', 'fields', 'saved', 'status', 'approve', 'save', 'delete', 'limits', 'reload', 'close']) {
    elements['advocate-preferences-' + id] = new Element();
  }
  elements['advocate-preferences'] = new Element('button');
  const document = {getElementById: id => elements[id], createElement: tag => new Element(tag)};
  const scope = {account: 'adv_a', generation: 1};
  const records = new Map([['adv_a', initial], ['adv_b', snapshot({advice_length: 'detailed'}, 4)]]);
  const calls = [];
  let override = null;
  async function standard(path, options) {
    const old = records.get(scope.account);
    if (options.method === 'GET') return structuredClone(old);
    const body = JSON.parse(options.body);
    assert.equal(body.approved, true);
    if (body.expected_version !== old.version) throw Object.assign(new Error('stale'), {status: 409});
    const settings = options.method === 'PUT' ? body.settings : {...old.settings};
    if (options.method === 'DELETE') {
      const key = path.split('/')[4];
      if (key) delete settings[key]; else for (const key of Object.keys(settings)) delete settings[key];
    }
    const current = snapshot(settings, old.version + 1); records.set(scope.account, current);
    return structuredClone(current);
  }
  const controller = create({document, session: () => ({...scope}), api: async (path, options) => {
    calls.push({path, options, account: scope.account});
    return override ? override(path, options, standard) : standard(path, options);
  }});
  const e = suffix => elements['advocate-preferences-' + suffix];
  const select = title => descendants(e('fields')).find(node => node.tag === 'select' && node.attributes['aria-label'] === title);
  const approve = async () => { e('approve').checked = true; await e('approve').fire('change'); };
  return {controller, scope, records, calls, e, select, approve, override: callback => {override = callback;},
          text: () => Object.values(elements).map(node => node.textContent).join(' ')};
}

test('unset defaults have no preselection, free text, automatic learning or implicit save', async () => {
  const f = fixture(); await f.controller.open();
  assert.equal(f.select('Advice length').value, '');
  assert.ok(descendants(f.e('fields')).filter(node => node.tag === 'input').every(node => node.type === 'checkbox' && !node.checked));
  assert.equal(f.e('approve').checked, false); assert.equal(f.e('save').disabled, true);
  await f.controller.save(); await f.controller.deleteAll();
  assert.equal(f.calls.length, 1);
  assert.match(f.text(), /No preferences are saved/);
});

test('explicit approval saves only selected bounded settings and the exact observed version', async () => {
  const f = fixture(); await f.controller.open();
  f.select('Advice length').value = 'short'; await f.select('Advice length').fire('change');
  f.select('Where authorities appear').value = 'end';
  await f.approve(); await f.controller.save();
  const sent = f.calls.at(-1);
  assert.equal(sent.options.method, 'PUT');
  assert.equal(sent.options.cache, 'no-store'); assert.equal(sent.options.credentials, 'same-origin');
  assert.deepEqual(JSON.parse(sent.options.body), {approved: true, expected_version: 0,
    settings: {advice_length: 'short', authorities_position: 'end'}});
  assert.equal(f.e('approve').checked, false);
  assert.match(f.e('status').textContent, /saved for new conversations/);
  await f.approve(); f.select('Advice length').value = 'detailed'; await f.select('Advice length').fire('change');
  assert.equal(f.e('approve').checked, false); assert.equal(f.e('save').disabled, true);
});

test('owner can delete one saved preference and all preferences only after approval', async () => {
  const f = fixture(snapshot({advice_length: 'short', authorities_position: 'end'}, 2));
  await f.controller.open(); await f.controller.deleteEntry('advice_length'); assert.equal(f.calls.length, 1);
  await f.approve(); await f.controller.deleteEntry('advice_length');
  assert.equal(f.calls.at(-1).path, '/api/account/advocate-memory/advice_length');
  assert.deepEqual(f.records.get('adv_a').settings, {authorities_position: 'end'});
  assert.match(f.e('status').textContent, /deletion confirmed/);
  await f.approve(); await f.controller.deleteAll();
  assert.deepEqual(f.records.get('adv_a').settings, {});
  assert.equal(f.records.get('adv_a').version, 4);
  assert.match(f.text(), /No preferences are saved/);
});

test('invalid response values fail as a whole instead of becoming account defaults or case text', () => {
  const changes = [value => { value.version = true; }, value => { value.version = -1; },
    value => { value.settings.client_name = 'PRIVATE CLIENT CANARY'; },
    value => { value.settings.court_ids = ['unlisted']; },
    value => { value.settings.advice_form = false; }, value => { value.supported.advice_form = ['new_unlisted']; },
    value => { value.supported.advice_length = ['supreme_court']; },
    value => { value.supported.court_ids = ['end']; },
    value => { value.settings.standing_instructions = ['the claimant wins']; },
    value => { value.supported.court_ids = ['hc_telangana', 'hc_telangana']; }];
  for (const change of changes) { const value = snapshot(); change(value); assert.throws(() => checkedMemory(value)); }
});

test('a malformed or unreadable response never renders planted case material', async () => {
  const f = fixture(); f.override(async () => ({...snapshot(), settings: {client_name: '<img src=x> PRIVATE CLIENT CANARY'}}));
  await f.controller.open();
  assert.ok(!f.text().includes('PRIVATE CLIENT CANARY')); assert.equal(f.e('fields').children.length, 0);
  assert.match(f.e('status').textContent, /Could not read/); assert.equal(f.e('save').disabled, true);
});

test('stale, lost or unexpected-version write acknowledgement makes no saved/deleted claim', async () => {
  for (const mode of ['stale', 'lost', 'wrong_version']) {
    const f = fixture(snapshot({advice_length: 'short'}, 1)); await f.controller.open(); await f.approve();
    f.override(async (path, options, standard) => {
      if (mode === 'wrong_version') return snapshot({advice_length: 'short'}, 99);
      if (mode === 'lost') await standard(path, options);
      throw Object.assign(new Error(mode), {status: mode === 'stale' ? 409 : undefined});
    });
    await f.controller.save();
    assert.match(f.e('status').textContent, /not confirmed/);
    assert.equal(f.e('save').disabled, true); assert.equal(f.e('approve').checked, false);
    const count = f.calls.length; await f.controller.save(); assert.equal(f.calls.length, count);
  }
});

test('clear removes every preference immediately and fences a delayed old-account read', async () => {
  const f = fixture(snapshot({advice_length: 'short'}, 1)); const held = deferred();
  f.override(async () => held.promise); const old = f.controller.open();
  const signal = f.calls.at(-1).options.signal;
  f.controller.clear(); assert.equal(signal.aborted, true); assert.equal(f.e('dialog').open, false);
  f.scope.account = 'adv_b'; f.scope.generation += 1; f.override(null); await f.controller.open();
  held.resolve(snapshot({advice_length: 'short'}, 1)); await old;
  assert.equal(f.select('Advice length').value, 'detailed');
  assert.equal(f.e('approve').checked, false);
  assert.ok(!f.e('saved').textContent.includes('Short'));
});

test('a delayed save cannot repaint or lend approval to another signed-in account', async () => {
  const f = fixture(snapshot({advice_length: 'short'}, 1)); await f.controller.open(); await f.approve();
  const held = deferred(); f.override(async () => held.promise); const old = f.controller.save();
  const signal = f.calls.at(-1).options.signal;
  f.controller.clear(); f.scope.account = 'adv_b'; f.scope.generation += 1;
  f.override(null); await f.controller.open(); held.resolve(snapshot({advice_length: 'short'}, 2)); await old;
  assert.equal(signal.aborted, true); assert.equal(f.select('Advice length').value, 'detailed');
  assert.equal(f.e('approve').checked, false); assert.ok(!f.e('status').textContent.includes('Preferences saved'));
});

test('reopening or reloading fences an earlier same-account read and closing blocks late writes', async () => {
  const f = fixture(); const held = deferred(); f.override(async () => held.promise);
  const old = f.controller.open(); f.override(null); await f.controller.open();
  held.resolve(snapshot({advice_length: 'short'}, 1)); await old;
  assert.equal(f.select('Advice length').value, '');
  await f.approve(); f.e('dialog').close(); const count = f.calls.length;
  await f.controller.save(); assert.equal(f.calls.length, count); assert.equal(f.e('saved').children.length, 0);
});

test('real application loads this module and clears it at every session/account boundary', () => {
  const html = fs.readFileSync('nm/app/index.html', 'utf8');
  const app = fs.readFileSync('nm/app/app.js', 'utf8');
  const moduleSource = fs.readFileSync('nm/legal_brain/understand/advocate-preferences.js', 'utf8');
  assert.ok(html.indexOf('/static/advocate-preferences.js') < html.indexOf('/static/app.js'));
  assert.match(app, /function clearPrivileged\(\) \{\s+advocatePreferences\?\.clear\(\)/);
  assert.match(app, /function showApplication\([^)]*\) \{\s+advocatePreferences\?\.clear\(\)/);
  assert.match(app, /NMAdvocatePreferences\.create\(\{document, api/);
  assert.match(app, /generation: state\.sessionGeneration/);
  assert.ok(!/localStorage|sessionStorage|\bfetch\s*\(/.test(moduleSource));
});
