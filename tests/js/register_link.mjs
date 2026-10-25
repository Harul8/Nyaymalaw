// The homepage's "Create your account" opens the app with #register (plan AN.16, now that the app is
// at /app and nyaymalaw.in opens the public homepage): read once, removed from the address, and the
// register card shown only to someone not signed in. Offline substitutes; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('function takeRegisterLink() {');
const end = app.indexOf("window.addEventListener('hashchange'", start);
assert.ok(start >= 0 && end > start, 'the register link reader must be shipped');

function run(hash) {
  const replaced = [];
  const context = vm.createContext({
    window: { location: { hash, pathname: '/app', search: '' } },
    history: { replaceState: (...args) => { replaced.push(args); } },
  });
  vm.runInContext(app.slice(start, end), context);
  return { taken: context.takeRegisterLink(), replaced };
}

{
  const { taken, replaced } = run('#register');
  assert.equal(taken, true);
  assert.deepEqual(replaced, [[null, '', '/app']], 'the link is removed from the address once read');
}
for (const hash of ['', '#reset=abc', '#registered', '#register-me']) {
  const { taken, replaced } = run(hash);
  assert.equal(taken, false, hash);
  assert.equal(replaced.length, 0, hash);
}

// Boot reads it before asking for the session, and shows the register card only to someone not
// signed in; a signed-in advocate simply opens their workspace.
const boot = app.slice(app.indexOf('async function boot() {'), app.indexOf("$('login').addEventListener('submit'"));
assert.ok(boot.indexOf('const wantsRegister = takeRegisterLink();') >= 0, 'boot no longer reads the link');
assert.ok(boot.indexOf('const wantsRegister = takeRegisterLink();') < boot.indexOf("await api('/api/session')"));
assert.ok(boot.includes("if (err.status === 401 && wantsRegister) showForm('register');"));
console.log('register link: ok');
