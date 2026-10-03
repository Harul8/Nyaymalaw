import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('async function deliver(entry) {');
const end = app.indexOf('/* ------------------------------------------------------------------ wire --- */', start);
assert.ok(start >= 0 && end > start, 'The shipped delivery function must be available');

async function refused(code, expectedState, expectedReloads) {
  const nodes = new Map();
  const node = (id) => {
    if (!nodes.has(id)) nodes.set(id, {
      parentElement: {insertBefore() {}}, scrollHeight: 0,
      addEventListener() {}, remove() {},
    });
    return nodes.get(id);
  };
  const detail = {committed: 'not_committed', retryable: true};
  if (code !== undefined) detail.code = code;
  const friendly = 'The saved conversation could not be verified. No new message was saved.';
  let reloads = 0;
  const context = vm.createContext({
    AbortController, activeDelivery: null,
    state: {sessionGeneration: 1, matterId: 'synthetic-matter'},
    ownsIntent: () => true, $: node,
    document: {createElement: () => node('cancel')},
    repaint() {}, updateWorkspace() {},
    saveProtectedDraft: async () => true,
    api: async () => { throw Object.assign(new Error(friendly), {status: 409, detail}); },
    showThreadBoard: async () => { reloads += 1; },
  });
  vm.runInContext(app.slice(start, end), context);
  const entry = {context: {}, envelope: '{}', request: {matter_id: 'synthetic-matter'}};
  await context.deliver(entry);
  assert.equal(entry.state, expectedState);
  assert.equal(reloads, expectedReloads);
  assert.equal(entry.error, friendly);
  assert.equal(entry.refusal, detail);
  assert.equal(context.activeDelivery, null);
  assert.equal(node('send').disabled, false);
}

await refused('brain_refused', 'not_committed', 0);
await refused('stale_version', 'stale', 1);
await refused(undefined, 'not_committed', 0);
