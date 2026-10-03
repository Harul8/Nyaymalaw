import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Node {
  constructor() { this.children = []; this.handlers = new Map(); this.open = false; }
  addEventListener(name, callback) { this.handlers.set(name, callback); }
  replaceChildren(...children) { this.children = children; this.textContent = ''; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() { this.focused = true; }
}
const nodes = new Map(['brain-source-reader', 'brain-source-title', 'brain-source-close',
  'brain-source-status', 'brain-source-body'].map(id => [id, new Node()]));
const events = new Map();
const window = {addEventListener:(name, callback) => events.set(name, callback)};
const document = {getElementById:id => nodes.get(id), createElement:() => new Node()};
vm.runInNewContext(fs.readFileSync('nm/app/brain-sources.js', 'utf8'), {window, document});
const reader = window.NmBrainSources;
const reads = [];
let session = 1;
reader.configure({scope:() => ({session}), request:url => new Promise((resolve, reject) => {
  reads.push({url, resolve, reject});
})});
const source = {brain:true, id:'saved-1', digest:'digest-1', text:'Exact saved words',
  label:'Saved passage', locator:'source-turn'};
const element = {source, sources:[source]};
const answer = {chat_id:'pending-chat', matter_id:null, turn_id:'source-turn'};
const saved = {...source, qualification:'Reported account, not proof'};
const opener = new Node(); opener.isConnected = true;

const opened = reader.open(answer, element, 2, 0, opener);
assert.equal(reads[0].url, '/api/chats/pending-chat/turns/source-turn/brain-sources/2/0');
reads[0].resolve(saved); await opened;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, source.text);
assert.equal(nodes.get('brain-source-reader').open, true);
reader.close();
assert.equal(opener.focused, true);
assert.equal(nodes.get('brain-source-body').children.length, 0);

const stale = reader.open(answer, element, 0, 0, opener);
const current = reader.open({...answer, matter_id:'saved-matter'}, element, 1, 0, opener);
nodes.get('brain-source-reader').handlers.get('close')();
assert.equal(nodes.get('brain-source-reader').open, true);
assert.equal(reads[2].url, '/api/matters/saved-matter/turns/source-turn/brain-sources/1/0');
reads[2].resolve(saved); await current;
reads[1].resolve({...saved, text:'Old selection'}); await stale;
assert.equal(nodes.get('brain-source-body').children.at(-1).textContent, source.text);

const mismatch = reader.open(answer, element, 0, 0, opener);
reads[3].resolve({...saved, digest:'different'}); await mismatch;
assert.equal(nodes.get('brain-source-body').children.length, 0);
assert.match(nodes.get('brain-source-status').textContent, /could not be matched/);

const ended = reader.open(answer, element, 0, 0, opener);
session += 1; reader.close(false);
reads[4].resolve(saved); await ended;
assert.equal(nodes.get('brain-source-reader').open, false);
assert.equal(nodes.get('brain-source-body').children.length, 0);

const changed = reader.open(answer, element, 0, 0, opener);
events.get('nm:matter-changed')();
reads[5].reject(new Error('late failure')); await changed;
assert.equal(nodes.get('brain-source-status').textContent, '');
assert.equal(nodes.get('brain-source-reader').open, false);
console.log('PASS saved brain source reader ownership');
