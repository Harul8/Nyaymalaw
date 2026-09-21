/* Same-device drafts. Ciphertext persists; the authenticated key never does.
 * One slot per tab preserves conflicting edits. A shared epoch prevents late
 * asynchronous saves and old tabs from resurrecting deliberately discarded work.
 */
'use strict';
class NMDraftVault {
  constructor(storage, cryptography, now = () => Date.now()) {
    this.storage = storage;
    this.crypto = cryptography;
    this.now = now;
    this.tab = cryptography.randomUUID();
    this.key = null;
    this.generation = 0;
    this.writes = Promise.resolve();
    this.last = new Map();
  }
  async unlock(protection) {
    this.lock();
    const generation = this.generation;
    if (!/^[a-f0-9]{64}$/.test(protection.namespace) || protection.lifetime_hours !== 72) {
      throw new Error('Draft protection could not be verified.');
    }
    const bytes = Uint8Array.from(atob(protection.key), c => c.charCodeAt(0));
    const key = await this.crypto.subtle.importKey('raw', bytes, 'AES-GCM', false,
      ['encrypt', 'decrypt']);
    bytes.fill(0);
    if (generation !== this.generation) return;
    this.prefix = 'nm.draft.v1.' + protection.namespace + '.';
    this.epochKey = this.prefix + 'epoch';
    this.epoch = this.storage.getItem(this.epochKey) || 'initial';
    this.lifetime = protection.lifetime_hours * 60 * 60 * 1000;
    this.key = key;
  }
  lock() {
    this.generation += 1;
    this.key = null;
    this.prefix = null;
    this.epochKey = null;
    this.last.clear();
  }
  current(generation) {
    return this.key && generation === this.generation
      && (this.storage.getItem(this.epochKey) || 'initial') === this.epoch;
  }
  async slotFor(key) {
    const digest = Array.from(new Uint8Array(await this.crypto.subtle.digest(
      'SHA-256', new TextEncoder().encode(key))))
      .map(b => b.toString(16).padStart(2, '0')).join('');
    return this.prefix + digest + '.' + this.tab;
  }
  save(intent) {
    // Snapshot before awaiting: later edits must not be labelled as this save.
    const text = JSON.stringify(intent);
    const generation = this.generation;
    const job = this.writes.catch(() => {}).then(async () => {
      if (!this.current(generation)) throw new Error('Draft access ended.');
      const slot = await this.slotFor(intent.key);
      if (this.last.get(slot)?.text === text) return this.last.get(slot).savedAt;
      const savedAt = Number.isFinite(intent.editedAt) ? intent.editedAt : this.now();
      if (savedAt > this.now() || savedAt + this.lifetime <= this.now()) {
        throw new Error('This draft has expired or its save time is invalid.');
      }
      const expiresAt = savedAt + this.lifetime;
      const iv = this.crypto.getRandomValues(new Uint8Array(12));
      const header = JSON.stringify({slot, epoch: this.epoch, savedAt, expiresAt});
      const encrypted = await this.crypto.subtle.encrypt({name: 'AES-GCM', iv,
        additionalData: new TextEncoder().encode(header)}, this.key,
      new TextEncoder().encode(text));
      if (!this.current(generation)) throw new Error('Draft access ended.');
      const encode = bytes => btoa(Array.from(bytes, b => String.fromCharCode(b)).join(''));
      this.storage.setItem(slot, JSON.stringify({header, iv: encode(iv),
        sealed: encode(new Uint8Array(encrypted))}));
      this.last.set(slot, {text, savedAt});
      return savedAt;
    });
    this.writes = job;
    return job;
  }
  async list() {
    const generation = this.generation;
    if (!this.current(generation)) throw new Error('Sign in to recover drafts.');
    const result = [];
    const slots = [];
    for (let i=0; i<this.storage.length; i++) {
      const slot=this.storage.key(i);
      if (slot.startsWith(this.prefix) && slot !== this.epochKey) slots.push(slot);
    }
    for (const slot of slots) {
      const raw = this.storage.getItem(slot);
      if (raw === null) continue;
      const record=JSON.parse(raw);
      const header=JSON.parse(record.header);
      if (header.slot !== slot || header.epoch !== this.epoch) continue;
      if (!Number.isFinite(header.expiresAt) || header.expiresAt <= this.now()) {
        this.storage.removeItem(slot); continue;
      }
      const decode = value => Uint8Array.from(atob(value), c=>c.charCodeAt(0));
      const plain=await this.crypto.subtle.decrypt({name:'AES-GCM', iv:decode(record.iv),
        additionalData:new TextEncoder().encode(record.header)}, this.key, decode(record.sealed));
      if (!this.current(generation)) throw new Error('Draft access ended.');
      result.push({slot, raw, savedAt:header.savedAt, expiresAt:header.expiresAt,
        intent:JSON.parse(new TextDecoder().decode(plain))});
    }
    return result.sort((a,b)=>b.savedAt-a.savedAt);
  }
  async adopt(saved) {
    await this.save({...saved.intent, editedAt:saved.savedAt});
    if (this.storage.getItem(saved.slot) === saved.raw) this.storage.removeItem(saved.slot);
  }
  async removeOwn(key) {
    const generation = this.generation;
    await this.writes.catch(() => {});
    if (!this.current(generation)) throw new Error('Draft access ended.');
    const slot = await this.slotFor(key);
    if (!this.current(generation)) throw new Error('Draft access ended.');
    this.storage.removeItem(slot);
    this.last.delete(slot);
  }
  discard() {
    if (!this.prefix) return;
    // Tombstone first: even an in-flight encryption must observe the discard.
    this.storage.setItem(this.epochKey, this.crypto.randomUUID());
    const slots=[];
    for(let i=0;i<this.storage.length;i++) {
      const slot=this.storage.key(i);
      if(slot.startsWith(this.prefix) && slot!==this.epochKey) slots.push(slot);
    }
    for(const slot of slots)this.storage.removeItem(slot);
    this.lock();
  }
}
if (typeof module !== 'undefined') module.exports = {NMDraftVault};
