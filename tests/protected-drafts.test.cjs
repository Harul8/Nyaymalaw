const {test} = require('node:test');
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const {NMDraftVault} = require('../frontend/draft-vault.js');
class Storage {
  constructor(){this.data=new Map();}
  get length(){return this.data.size;}
  key(i){return [...this.data.keys()][i];}
  getItem(k){return this.data.get(k)??null;}
  setItem(k,v){this.data.set(k,String(v));}
  removeItem(k){this.data.delete(k);}
}
const protection={namespace:'a'.repeat(64),key:Buffer.alloc(32,7).toString('base64'),lifetime_hours:72};
const intent={key:'opaque-context',advocate:'synthetic',workspace:'private',matterId:null,
  text:'Synthetic confidential draft canary',fields:{},pending:[]};
async function setup(storage=new Storage(),now=()=>Date.now()){
  const vault=new NMDraftVault(storage,webcrypto,now);await vault.unlock(protection);
  return {vault,storage};
}
test('ciphertext survives reopening; plaintext and key are never persisted',async()=>{
  const {vault,storage}=await setup();await vault.save(intent);
  assert.ok(!JSON.stringify([...storage.data]).includes(intent.text));
  assert.ok(!JSON.stringify([...storage.data]).includes(protection.key));
  vault.lock();await assert.rejects(vault.list());
  const reopened=await setup(storage);assert.deepEqual((await reopened.vault.list())[0].intent,intent);
});
test('a different key cannot recover the same stored ciphertext',async()=>{
  const {vault,storage}=await setup();await vault.save(intent);
  const other=new NMDraftVault(storage,webcrypto);
  await other.unlock({...protection,key:Buffer.alloc(32,9).toString('base64')});
  await assert.rejects(other.list());
});
test('expiry is absolute from the actual edit, not from reopening',async()=>{
  let clock=1000000;const {vault,storage}=await setup(new Storage(),()=>clock);
  await vault.save({...intent,editedAt:clock});clock+=71*3600000;
  const opened=await setup(storage,()=>clock);const held=(await opened.vault.list())[0];
  await opened.vault.adopt(held);clock+=3600000;
  assert.deepEqual(await opened.vault.list(),[]);
});
test('tampering with expiry fails authenticated decryption',async()=>{
  const {vault,storage}=await setup();await vault.save(intent);
  const slot=storage.key(0),record=JSON.parse(storage.getItem(slot));
  const header=JSON.parse(record.header);header.expiresAt+=3600000;
  record.header=JSON.stringify(header);storage.setItem(slot,JSON.stringify(record));
  await assert.rejects(vault.list());
});
test('two tabs keep different recoverable versions',async()=>{
  const {vault,storage}=await setup();const other=(await setup(storage)).vault;
  await Promise.all([vault.save(intent),other.save({...intent,text:'A different edit'})]);
  assert.equal((await vault.list()).length,2);
});
test('discard prevents old tabs and queued writes from resurrecting work',async()=>{
  const {vault,storage}=await setup();const other=(await setup(storage)).vault;
  await vault.save(intent);const pending=other.save({...intent,text:'Late edit'});
  vault.discard();await assert.rejects(pending);await assert.rejects(other.save(intent));
  const reopened=(await setup(storage)).vault;assert.deepEqual(await reopened.list(),[]);
});
test('quota failure cannot report a save or write plaintext fallback',async()=>{
  const {vault,storage}=await setup();storage.setItem=()=>{throw new Error('quota');};
  await assert.rejects(vault.save(intent),/quota/);assert.equal(storage.length,0);
});
test('submission checkpoint replaces only the writer version, keeping a newer tab edit',async()=>{
  const {vault,storage}=await setup();const other=(await setup(storage)).vault;
  await vault.save(intent);await other.save({...intent,text:'Newer unsubmitted edit'});
  await vault.save({...intent,text:'',fields:{},pending:[]});
  const texts=(await vault.list()).map(r=>r.intent.text);
  assert.ok(!texts.includes(intent.text));assert.ok(texts.includes('Newer unsubmitted edit'));
});

test('retiring an opening checkpoint preserves another tab and the saved matter checkpoint',async()=>{
  const {vault,storage}=await setup();const other=(await setup(storage)).vault;
  await vault.save({...intent,opening:{key:'stable-request',offer:'parties'}});
  await other.save({...intent,text:'Another tab opening'});
  await vault.save({...intent,key:'saved-matter',matterId:'matter-1'});
  await vault.removeOwn(intent.key);
  const saved=await vault.list();
  assert.equal(saved.length,2);
  assert.ok(saved.some(row=>row.intent.key==='saved-matter'));
  assert.ok(saved.some(row=>row.intent.text==='Another tab opening'));
});

test('a recovery preview cannot delete an edit made while it was decrypting',async()=>{
  const {vault,storage}=await setup();await vault.save(intent);
  let changed=false;
  const crypto={randomUUID:()=>webcrypto.randomUUID(),
    getRandomValues:array=>webcrypto.getRandomValues(array),
    subtle:{importKey:(...args)=>webcrypto.subtle.importKey(...args),
      digest:(...args)=>webcrypto.subtle.digest(...args),
      encrypt:(...args)=>webcrypto.subtle.encrypt(...args),
      decrypt:async(...args)=>{
        const result=await webcrypto.subtle.decrypt(...args);
        if(!changed){changed=true;await vault.save({...intent,text:'Changed during preview'});}
        return result;
      }}};
  const reading=new NMDraftVault(storage,crypto);await reading.unlock(protection);
  const snapshot=(await reading.list())[0];
  assert.equal(snapshot.intent.text,intent.text);
  await reading.adopt(snapshot);
  const texts=(await reading.list()).map(row=>row.intent.text);
  assert.ok(texts.includes('Changed during preview'));
  assert.ok(texts.includes(intent.text));
});
