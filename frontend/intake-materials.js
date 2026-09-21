/* Original receipt is not permission to read, and never establishes a fact. */
(() => {
  'use strict';
  let limits = null;
  const MAX_RECORDING_MS = 5 * 60 * 1000;
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const dialog = node('dialog', undefined, 'account-dialog materials-dialog');
  dialog.id = 'materials-dialog';
  dialog.setAttribute('aria-labelledby', 'materials-title');
  // Constant markup only. File names, user statements and receipts use textContent.
  dialog.innerHTML = `
    <div class="dialog-heading"><div><p class="eyebrow">BRING THE ORIGINAL MATERIAL</p>
      <h2 id="materials-title">Files and voice notes</h2></div>
      <button id="materials-close" type="button" class="ghost">Close</button></div>
    <p id="materials-target" class="materials-muted"></p>
    <p class="materials-limit">Files are retained in restricted quarantine. They are not scanned,
      admitted, transcribed or read; no fact is established. Original preview and download remain held.</p>
    <form id="materials-form">
      <label for="materials-matter-title">Matter title <span class="materials-muted">— optional; otherwise your first file name</span></label>
      <input id="materials-matter-title" maxlength="200" autocomplete="off">
      <label for="materials-files">Choose original files — documents, images, audio or video</label>
      <input id="materials-files" type="file" multiple aria-describedby="materials-bounds">
      <p id="materials-bounds" class="materials-muted">Reading this installation's upload limits. No transfer until they are confirmed. An upload does not replace the legal admission checks.</p>
      <section class="materials-recorder" aria-labelledby="materials-record-title">
        <h3 id="materials-record-title">Record a voice note</h3>
        <p class="materials-muted">Microphone access starts only when you choose Record. Capture and playback stay in this tab until you choose Upload. Five-minute limit, including pauses.</p>
        <div class="materials-actions">
          <button id="materials-record" type="button" class="secondary">Record voice note</button>
          <button id="materials-record-pause" type="button" class="ghost" disabled>Pause recording</button>
          <button id="materials-record-stop" type="button" class="ghost" disabled>Stop recording</button>
        </div>
        <p id="materials-record-state" role="status" aria-live="polite">Microphone off.</p>
        <audio id="materials-playback" controls hidden aria-label="Local voice-note playback"></audio>
      </section>
      <ul id="materials-selected" class="materials-selected" aria-label="Selected original files"></ul>
      <label for="materials-purpose">Purpose for holding this material</label>
      <textarea id="materials-purpose" rows="2" maxlength="2000" required></textarea>
      <label for="materials-authority">Your authority to provide and retain it</label>
      <textarea id="materials-authority" rows="2" maxlength="2000" required></textarea>
      <p class="materials-muted">These are your supplied statements, not an independent verification of consent, rights or legal authority.</p>
      <label for="materials-retention">Retention instruction</label>
      <select id="materials-retention" required>
        <option value="">Choose explicitly…</option>
        <option value="matter_life">For the life of this matter</option>
        <option value="fixed_period">Until a specified date</option>
        <option value="delete_after_derivation">Delete after authorised derivation</option>
      </select>
      <div id="materials-until-wrap" hidden><label for="materials-until">Retain until</label>
        <input id="materials-until" type="date"></div>
      <p class="materials-limit">The instruction is recorded. Automated retention/deletion is not implemented here; this selection is not a promise that deletion has occurred or will run automatically.</p>
      <div class="materials-actions">
        <button id="materials-upload" type="submit" class="primary">Upload selected originals</button>
        <button id="materials-pause" type="button" class="ghost" disabled>Pause upload</button>
      </div>
    </form>
    <p id="materials-status" role="status" aria-live="polite"></p>
    <div class="materials-receipt-heading"><h3>Saved receipts</h3>
      <button id="materials-refresh" type="button" class="ghost">Refresh receipts</button></div>
    <p class="materials-muted">To resume after reopening, choose the same original file. Its full digest and size must match the saved receipt. Closing this window stops local sending, not storage of bytes already accepted.</p>
    <div id="materials-receipts"></div>
    <input id="materials-resume-file" type="file" hidden aria-label="Reselect the original file to resume">
  `;
  document.body.append(dialog);
  const el = id => dialog.querySelector(`#materials-${id}`);
  // F-C-01. OPENED FROM THE PLUS MENU UNDER THE BRIEF; there is no files bar
  // above the chat. Documents and media each open the file chooser for their
  // kind, and a voice note to keep goes to the recorder below.
  const KINDS = {
    documents: '.pdf,.doc,.docx,.odt,.rtf,.txt,.xls,.xlsx,.csv,.eml,.msg',
    media: 'image/*,audio/*,video/*',
  };
  function openFor(kind) {
    setPlusMenu(false);
    el('files').accept = KINDS[kind] || '';
    const opening = open();
    if (dialog.open && kind in KINDS) el('files').click();
    if (dialog.open && kind === 'voice') el('record').focus();
    return opening;
  }
  $('plus-documents').addEventListener('click', () => openFor('documents'));
  $('plus-media').addEventListener('click', () => openFor('media'));
  $('plus-voice').addEventListener('click', () => openFor('voice'));

  let generation = 0, receiptReadGeneration = 0, token = null, busy = false, active = null;
  let files = [], receipts = [], resumeId = null, adopting = null;
  let recorder = null, stream = null, timer = null, capture = null;
  let preview = null;
  const attempts = new Map();
  let opening = null;
  const key = () => crypto.randomUUID().replaceAll('-', '');
  const valid = held => dialog.open && !!state.advocate && !state.ended && held
    && held.generation === generation && held.session === state.sessionGeneration
    && held.rail === state.railGeneration && held.matter === state.matterId;
  const context = () => ({generation, session: state.sessionGeneration,
    rail: state.railGeneration, matter: state.matterId});
  const say = text => { el('status').textContent = text; };
  const bytes = count => `${(count / 1024).toLocaleString(undefined, {maximumFractionDigits: 1})} KiB`;
  const route = (held, suffix = '') => `/api/matters/${encodeURIComponent(held.matter)}/uploads${suffix}`;
  function requireCurrent(held) {
    if (!valid(held)) { const error = new Error('The active context changed.'); error.obsolete = true; throw error; }
  }
  function controls() {
    el('upload').disabled = busy || !!capture || !!recorder || !limits;
    el('pause').disabled = !busy;
    el('files').disabled = busy || !!capture || !!recorder;
    el('refresh').disabled = busy;
    el('record').disabled = busy || !!recorder || !!capture || !limits;
    el('record-pause').disabled = !recorder;
    el('record-stop').disabled = !recorder;
  }
  function selected() {
    el('selected').replaceChildren(...files.map(file => node('li', `${file.name} · ${bytes(file.size)} · local selection`)));
  }
  function clearPreview() {
    const player = el('playback');
    player.pause(); player.removeAttribute('src'); player.load(); player.hidden = true;
    if (preview) URL.revokeObjectURL(preview);
    preview = null;
  }
  function stopCapture(discard = false) {
    if (capture && discard) capture.discard = true;
    if (timer) clearTimeout(timer);
    timer = null;
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach(track => track.stop());
    stream = null;
  }
  function dismiss() {
    const returnToComposer = valid(token) && !$('composer').hidden;
    generation += 1;
    receiptReadGeneration += 1;
    if (active) active.abort();
    active = null; busy = false;
    stopCapture(true); recorder = null; capture = null;
    clearPreview();
    files = []; receipts = []; resumeId = null; token = null; limits = null;
    el('form').reset(); el('resume-file').value = '';
    el('until-wrap').hidden = true; el('until').required = false;
    el('selected').replaceChildren(); el('receipts').replaceChildren();
    el('target').textContent = ''; el('status').textContent = '';
    el('record-state').textContent = 'Microphone off.';
    el('record-pause').textContent = 'Pause recording';
    if (dialog.open) dialog.close();
    controls();
    // The menu entry that opened us is now hidden. Restore a visible trigger,
    // but never move focus into an obsolete matter or a signed-out workspace.
    if (returnToComposer) $('plus-toggle').focus();
  }
  window.addEventListener('nm:session-ended', () => {
    attempts.clear(); opening = null; adopting = null; dismiss();
  });
  window.addEventListener('nm:matter-changed', () => {
    if (dialog.open && !(adopting && state.matterId === adopting)) dismiss();
  });
  el('close').addEventListener('click', dismiss);
  dialog.addEventListener('cancel', event => { event.preventDefault(); dismiss(); });
  dialog.addEventListener('close', () => { if (!dialog.open && token) dismiss(); });

  async function open() {
    if (!state.advocate || state.ended) return;
    if (!state.matterId) {
      showIntake(true);
      $('intake-state').textContent = 'Record the opening brief before adding material. Unknown answers are allowed.';
      return;
    }
    if (activeDelivery) { return; }
    if (dialog.open) return;
    generation += 1; dialog.showModal(); token = context();
    el('target').textContent = token.matter ? `For ${$('matter-heading').textContent}`
      : 'No case narrative is required. Your supplied title or first file name opens a matter; its legal screens remain unassessed.';
    el('matter-title').disabled = !!token.matter;
    controls();
    if (token.matter) await refresh(token);
    else el('receipts').textContent = 'No matter has been opened by this window yet.';
  }
  function checked(row, held, assetId = null) {
    requireCurrent(held);
    const r = row && row.receipt;
    if (!r || row.matter_id !== held.matter || r.matter_id !== held.matter
        || row.asset_id !== r.upload_id || (assetId && row.asset_id !== assetId)
        || !Number.isInteger(r.declared_size)
        || r.declared_size < 1 || !limits || r.declared_size > limits.original_bytes
        || !Number.isInteger(r.observed_size) || r.observed_size < 0
        || r.observed_size > r.declared_size || !Number.isInteger(row.version) || row.version < 0
        || !['not_started', 'receiving', 'received', 'failed_integrity', 'cancelled'].includes(r.state)
        || row.quarantine !== 'not_assessed' || row.establishes_a_fact !== false
        || row.may_reach_reasoning !== false) {
      throw new Error('The receipt identity or admission state could not be verified. No further bytes will be sent.');
    }
    state.matterVersion = Math.max(state.matterVersion || 0, row.version);
    return row;
  }
  function putReceipt(row, held, assetId = null) {
    checked(row, held, assetId);
    receipts = [...receipts.filter(item => item.asset_id !== row.asset_id), row];
    renderReceipts();
  }
  function renderReceipts() {
    el('receipts').replaceChildren();
    if (!receipts.length) { el('receipts').textContent = 'No saved original receipts on this matter.'; return; }
    for (const row of receipts) {
      const card = node('article', undefined, 'materials-receipt');
      card.dataset.assetId = row.asset_id;
      card.append(node('h4', row.filename));
      const r = row.receipt;
      const stateText = r.state === 'received' ? 'Received — not admitted or read'
        : r.state === 'receiving' ? 'Incomplete — may be resumed'
        : r.state === 'cancelled' ? 'Cancelled — accepted sealed bytes retained'
        : 'Integrity not established — do not rely on this material';
      card.append(node('p', `${stateText}. ${bytes(r.observed_size)} of ${bytes(r.declared_size)}.`, 'materials-receipt-state'));
      card.append(node('p', `Quarantine: not assessed. ${row.reason || 'Reading and reasoning are withheld.'}`, 'materials-limit'));
      const details = node('details');
      details.append(node('summary', 'Receipt and supplied instructions'));
      for (const [label, value] of [['Purpose', row.purpose], ['Supplied authority (not verified)', row.authority],
        ['Retention instruction', row.retention], ['Retain until', row.retain_until || 'No fixed date supplied'],
        ['Automatic deletion', 'Not implemented; accepted bytes are retained'],
        ['Original locator', row.asset_id], ['Observed SHA-256', r.observed_hash || 'Not complete'],
        ['Reading', 'No OCR, transcription, scanner or page/time assessment has run']]) {
        details.append(node('p', `${label}: ${value}`));
      }
      card.append(details);
      if (r.state === 'receiving') {
        const resume = node('button', 'Reselect original and resume', 'ghost');
        resume.type = 'button'; resume.disabled = busy;
        resume.addEventListener('click', () => { resumeId = row.asset_id; el('resume-file').click(); });
        const cancel = node('button', 'Cancel this upload', 'ghost');
        cancel.type = 'button'; cancel.disabled = busy;
        cancel.addEventListener('click', () => cancelReceipt(row.asset_id));
        card.append(resume, cancel);
      }
      el('receipts').append(card);
    }
  }
  async function refresh(held = token) {
    if (busy || !held || !held.matter) return;
    const requestGeneration = ++receiptReadGeneration;
    try {
      const reply = await api(route(held));
      requireCurrent(held);
      if (requestGeneration !== receiptReadGeneration) return;
      if (reply.matter_id !== held.matter || !Array.isArray(reply.uploads)) throw new Error('The receipt list could not be verified.');
      const reported = reply.limits;
      if (!reported || !['original_bytes', 'chunk_bytes', 'receipts_per_matter'].every(
        name => Number.isSafeInteger(reported[name]) && reported[name] > 0)) {
        throw new Error('The server upload limits could not be established.');
      }
      limits = reported;
      el('bounds').textContent = `Up to ${bytes(limits.original_bytes)} per file, sent in chunks of up to ${bytes(limits.chunk_bytes)}. `
        + `${limits.receipts_per_matter} receipts per matter, including incomplete receipts. Receipt is not admission or understanding.`;
      receipts = reply.uploads.map(row => checked(row, held));
      renderReceipts();
      controls();
    } catch (error) {
      if (valid(held) && requestGeneration === receiptReadGeneration) el('receipts').textContent = 'The receipt list could not be read. This does not mean that no material is held. Refresh before relying on it.';
    }
  }
  el('refresh').addEventListener('click', () => refresh());
  el('retention').addEventListener('change', () => {
    const fixed = el('retention').value === 'fixed_period';
    el('until-wrap').hidden = !fixed; el('until').required = fixed;
    if (!fixed) el('until').value = '';
  });
  el('files').addEventListener('change', () => {
    const incoming = Array.from(el('files').files);
    if (!limits || incoming.some(file => !file.size || file.size > limits.original_bytes)
        || incoming.length > limits.receipts_per_matter) {
      say('Choose nonempty files within the confirmed server limits. If limits are unavailable, refresh receipts first. Nothing was uploaded.');
      files = []; selected(); el('files').value = ''; return;
    }
    files = incoming; selected(); say('Selected locally. Supply the purpose, authority and retention instruction before uploading.');
  });
  async function digest(file, held) {
    if (!limits || !file.size || file.size > limits.original_bytes) {
      throw new Error('The original must fit the confirmed server limits.');
    }
    if (!crypto.subtle) throw new Error('This browser cannot verify the original digest. Upload is held.');
    const buffer = await file.arrayBuffer(); requireCurrent(held);
    const value = await crypto.subtle.digest('SHA-256', buffer); requireCurrent(held);
    return Array.from(new Uint8Array(value), byte => byte.toString(16).padStart(2, '0')).join('');
  }
  async function transfer(file, row, held, hash) {
    checked(row, held);
    const assetId = row.asset_id;
    if (row.filename !== file.name || row.receipt.declared_size !== file.size
        || !row.receipt.declared_hash || row.receipt.declared_hash !== hash) {
      throw new Error('The reselected file does not match the saved name, size and full SHA-256 digest. Nothing further was sent.');
    }
    while (row.receipt.state === 'receiving' && row.receipt.observed_size < file.size) {
      requireCurrent(held);
      if (active.signal.aborted) throw new DOMException('Paused', 'AbortError');
      const offset = row.receipt.observed_size;
      const data = await file.slice(offset, offset + limits.chunk_bytes).arrayBuffer();
      requireCurrent(held);
      row = await api(route(held, `/${encodeURIComponent(assetId)}/chunks/${offset}`), {
        method: 'PUT', headers: {'content-type': 'application/octet-stream'}, body: data, signal: active.signal,
      });
      putReceipt(row, held, assetId);
      say(`Sending ${file.name}: ${bytes(row.receipt.observed_size)} of ${bytes(file.size)} acknowledged.`);
      if (row.receipt.observed_size <= offset) throw new Error('The server receipt did not advance. Resume only after inspecting it.');
    }
    if (row.receipt.state === 'receiving') {
      row = await api(route(held, `/${encodeURIComponent(assetId)}/complete`), {method: 'POST', signal: active.signal});
      putReceipt(row, held, assetId);
    }
    if (row.receipt.state !== 'received' || row.receipt.observed_hash !== hash) {
      throw new Error('This original is not integrity-confirmed as received. It remains withheld.');
    }
    say('Original received in restricted quarantine. It has not been scanned, admitted or read.');
  }
  async function run(work) {
    if (busy || !valid(token) || activeDelivery) return;
    // A pre-mutation list response must not restore an earlier receipt after
    // cancellation, resumption or receipt of more bytes.
    receiptReadGeneration += 1;
    busy = true; active = new AbortController(); const started = token;
    controls(); renderReceipts();
    try { await work(); }
    catch (error) {
      if (started.generation === generation && valid(token) && started.session === state.sessionGeneration) {
        say(error.name === 'AbortError'
          ? 'Local sending paused. Accepted bytes may already be saved; refresh the receipt and reselect the same original to resume. Pausing does not delete bytes.'
          : `${error.message || 'The request was not confirmed.'} Accepted bytes may already be saved. Refresh receipts before retrying; never assume that a lost response means nothing arrived.`);
      }
    } finally {
      if (started.generation === generation) { busy = false; active = null; controls(); renderReceipts(); }
    }
  }
  async function ensureMatter(first) {
    const held = token;
    if (held.matter) return held;
    const title = el('matter-title').value.trim() || first.name.slice(0, 200);
    if (!opening || opening.title !== title || opening.session !== held.session) {
      opening = {title, request_key: key(), session: held.session};
    }
    const result = await api('/api/matters/intake', {method: 'POST',
      headers: {'content-type': 'application/json'}, signal: active.signal,
      body: JSON.stringify({title, request_key: opening.request_key})});
    requireCurrent(held);
    if (!result.matter_id || result.state !== 'intake_opened' || result.facts_established !== false) {
      throw new Error('The matter opening could not be confirmed. No original bytes were sent.');
    }
    adopting = result.matter_id;
    try { await showThreadBoard(result.matter_id, { adoptOpening: true }); }
    finally { adopting = null; }
    if (!dialog.open || state.sessionGeneration !== held.session || state.matterId !== result.matter_id) {
      const error = new Error('The selected matter changed.'); error.obsolete = true; throw error;
    }
    token = context(); opening = null;
    el('target').textContent = `For ${result.title}. Legal screens remain unassessed.`;
    el('matter-title').disabled = true;
    return token;
  }
  el('form').addEventListener('submit', event => {
    event.preventDefault();
    if (!files.length) { say('Choose an original file or explicitly record a voice note first.'); return; }
    const purpose = el('purpose').value.trim(), authority = el('authority').value.trim();
    if (!purpose || !authority || !el('retention').value) { say('Supply a nonblank purpose, authority statement and explicit retention instruction.'); return; }
    const batch = [...files];
    const instruction = {purpose, authority, retention: el('retention').value};
    if (instruction.retention === 'fixed_period') instruction.retain_until = el('until').value;
    run(async () => {
      const held = await ensureMatter(batch[0]);
      for (const file of batch) {
        requireCurrent(held); say(`Verifying the full original: ${file.name}…`);
        const hash = await digest(file, held);
        const identity = JSON.stringify([held.session, held.matter, file.name, file.size, hash, instruction]);
        if (!attempts.has(identity)) attempts.set(identity, key());
        let row = await api(route(held), {method: 'POST', signal: active.signal,
          headers: {'content-type': 'application/json'}, body: JSON.stringify({
            ...instruction, request_key: attempts.get(identity), filename: file.name,
            declared_size: file.size, declared_type: file.type || '', declared_hash: hash,
          })});
        putReceipt(row, held);
        // Re-read acknowledged state even on a replayed begin response.
        const assetId = row.asset_id;
        row = checked(await api(route(held, `/${encodeURIComponent(assetId)}`), {signal: active.signal}), held, assetId);
        await transfer(file, row, held, hash);
      }
      files = []; el('files').value = ''; selected();
    });
  });
  el('pause').addEventListener('click', () => { if (active) active.abort(); });
  el('resume-file').addEventListener('change', () => {
    const file = el('resume-file').files[0], assetId = resumeId;
    el('resume-file').value = ''; resumeId = null;
    if (!file || !assetId) return;
    run(async () => {
      const held = token;
      const row = checked(await api(route(held, `/${encodeURIComponent(assetId)}`), {signal: active.signal}), held, assetId);
      const hash = await digest(file, held);
      await transfer(file, row, held, hash);
    });
  });
  function cancelReceipt(assetId) {
    run(async () => {
      const held = token;
      const row = await api(route(held, `/${encodeURIComponent(assetId)}/cancel`), {method: 'POST', signal: active.signal});
      putReceipt(row, held, assetId);
      say(row.receipt.state === 'cancelled'
        ? 'Cancellation confirmed. Bytes already accepted remain sealed; they were not deleted.'
        : 'The receipt is already complete. Cancellation did not undo receipt or delete the original.');
    });
  }

  el('record').addEventListener('click', async () => {
    if (busy || capture || !valid(token)) return;
    if (files.length >= 64) { say('Upload or clear the current selection before adding another original.'); return; }
    const held = token;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      el('record-state').textContent = 'Recording is unavailable in this browser. You can choose an existing audio or video file.'; return;
    }
    const local = {discard: false, chunks: [], size: 0, held};
    capture = local; controls();
    el('record-state').textContent = 'Waiting for your microphone permission…';
    try {
      const obtained = await navigator.mediaDevices.getUserMedia({audio: true});
      if (!valid(held) || capture !== local) { obtained.getTracks().forEach(track => track.stop()); return; }
      stream = obtained; clearPreview();
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      const recording = new MediaRecorder(stream, mime ? {mimeType: mime} : {});
      recorder = recording;
      recording.addEventListener('dataavailable', event => {
        if (capture !== local || recorder !== recording || local.discard || !valid(held) || !event.data.size) return;
        local.size += event.data.size;
        if (!limits || local.size > limits.original_bytes) {
          local.discard = true; local.chunks = []; stopCapture(true);
          el('record-state').textContent = 'Recording exceeded the confirmed file limit and was discarded locally. Nothing was uploaded.';
        } else local.chunks.push(event.data);
      });
      recording.addEventListener('stop', () => {
        if (recorder === recording) { if (timer) clearTimeout(timer); timer = null; }
        if (stream === obtained) { obtained.getTracks().forEach(track => track.stop()); stream = null; }
        if (recorder === recording) recorder = null;
        if (capture === local) capture = null;
        if (!local.discard && valid(held) && limits && local.size
            && local.size <= limits.original_bytes) {
          const blob = new Blob(local.chunks, {type: recording.mimeType || 'audio/webm'});
          const extension = blob.type.includes('mp4') ? 'm4a' : 'webm';
          const file = new File([blob], `Voice note ${new Date().toISOString().replaceAll(':', '-')}.${extension}`, {type: blob.type});
          files.push(file); selected(); preview = URL.createObjectURL(blob);
          el('playback').src = preview; el('playback').hidden = false;
          el('record-state').textContent = 'Microphone off. Local voice note ready for playback; it has not been uploaded or transcribed.';
        } else if (!local.discard && valid(held)) el('record-state').textContent = 'Microphone off. No audio bytes were captured.';
        local.chunks = [];
        if (valid(held)) controls();
      });
      recording.addEventListener('error', () => {
        if (recorder !== recording || capture !== local) return;
        stopCapture(true);
        if (valid(held)) el('record-state').textContent = 'Recording failed locally. Nothing was uploaded; choose an existing recording or try again.';
      });
      recording.start(1000);
      el('record-pause').textContent = 'Pause recording';
      timer = setTimeout(() => {
        if (recorder === recording) { stopCapture(); el('record-state').textContent = 'Five-minute capture limit reached; stopping the microphone.'; }
      }, MAX_RECORDING_MS);
      el('record-state').textContent = 'Recording locally. Nothing is being sent. Stop within five minutes.';
      controls();
    } catch (error) {
      if (capture !== local) return;
      stopCapture(true); recorder = null;
      if (capture === local) capture = null;
      if (valid(held)) { el('record-state').textContent = 'Microphone unavailable or permission declined. Nothing was recorded or uploaded. You can choose an existing file.'; controls(); }
    }
  });
  el('record-pause').addEventListener('click', () => {
    if (!recorder) return;
    if (recorder.state === 'recording') {
      recorder.pause(); el('record-pause').textContent = 'Resume recording';
      el('record-state').textContent = 'Recording paused locally. Stop to release the microphone.';
    } else if (recorder.state === 'paused') {
      recorder.resume(); el('record-pause').textContent = 'Pause recording';
      el('record-state').textContent = 'Recording resumed locally. Nothing is being sent.';
    }
  });
  el('record-stop').addEventListener('click', () => stopCapture());
})();
