// THE INITIALS ON THE PERSON BUTTON (plan AN.20): the first letters of the first and last words of the name
// the account holds, after any title; the first letter of an email's name when the account holds no name;
// put on at sign-in and taken off with the session. Offline; not browser QA.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../../nm/app/app.js', import.meta.url), 'utf8');
const start = app.indexOf('const NAME_TITLES =');
const end = app.indexOf('function showApplication(advocate, workspace, professionalApproval) {', start);
assert.ok(start >= 0 && end > start, 'the initials function must be shipped');
const context = vm.createContext({ Array, String });
vm.runInContext(app.slice(start, end), context);
const initials = (name) => context.initialsOf(name);

// The design's own example, a name with a title, and the ordinary shapes.
assert.equal(initials('Adv. Meera Rao'), 'MR');
assert.equal(initials('Meera Rao'), 'MR');
assert.equal(initials('Rahul Lambade'), 'RL');
assert.equal(initials('Meera'), 'M');
assert.equal(initials('  Meera   Kumari   Rao '), 'MR', 'the first and last words, however many between');
assert.equal(initials('Dr. A P J Abdul Kalam'), 'AK');
assert.equal(initials('A. B. Sharma'), 'AS');
assert.equal(initials('Justice Hon Meera Rao'), 'MR', 'titles are skipped one after another');

// A title is never the whole of it.
assert.equal(initials('Adv'), 'A');
assert.equal(initials('Dr.'), 'D');

// An account that holds no name shows its email, or its id: one letter, from before the @.
assert.equal(initials('p14lrahul@iima.ac.in'), 'P');
assert.equal(initials('Advocate@Chambers.in'), 'A');
assert.equal(initials('adv_demo'), 'A');

// Other scripts: the first letter of each word, in the case that script has.
assert.equal(initials('మీరా రావు'), 'మర');
assert.equal(initials('ÉLISE Ångström'), 'ÉÅ');

// Nothing to show is shown as nothing, never as a made-up letter.
assert.equal(initials(''), '');
assert.equal(initials('   '), '');
assert.equal(initials(null), '');
assert.equal(initials(undefined), '');
assert.equal(initials('— · —'), '');

// It is put on at sign-in from the name shown, and taken off with the session.
const show = app.slice(app.indexOf('function showApplication('), app.indexOf('// IS THE SERVER RUNNING THE CODE THAT IS ON DISK?'));
assert.ok(show.indexOf("$('who-name').textContent = shownName;") < show.indexOf("$('account-initials').textContent = initialsOf(shownName);"));
assert.ok(show.includes("const shownName = advocate.name || advocate.email || advocate.id;"));
const cleared = app.slice(app.indexOf('function clearPrivileged() {'), app.indexOf('/* ------------------------------------------------------- idle sign-out --- */'));
assert.ok(/'who-name', 'account-initials', 'profile-name'/.test(cleared), 'the initials leave with the session');
console.log('person initials: ok');
