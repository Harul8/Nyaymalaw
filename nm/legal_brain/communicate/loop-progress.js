/* Closed-by-default recorded stages. No model text or private deliberation. */
'use strict';

(() => {
  const streams = new Set();
  function stopAll() {
    streams.forEach((stream) => stream.close());
    streams.clear();
  }
  window.addEventListener('nm:session-ended', stopAll);
  window.addEventListener('nm:matter-changed', stopAll);

  function attach(container, matterId, { read, isCurrent, turnId = null, unlinkedOnly = false }) {
    const panel = document.createElement('details');
    panel.className = 'audit recorded-work-progress';
    const summary = document.createElement('summary');
    summary.textContent = turnId ? 'Recorded work for this response' : 'Other recorded work progress';
    panel.appendChild(summary);
    container.appendChild(panel);
    let requestGeneration = 0;
    const localStreams = new Set();
    function stopLocal() {
      localStreams.forEach((stream) => { stream.close(); streams.delete(stream); });
      localStreams.clear();
    }
    function current(generation) {
      return generation === requestGeneration && panel.isConnected && panel.open && isCurrent();
    }
    panel.addEventListener('toggle', async () => {
      stopLocal();
      const generation = ++requestGeneration;
      if (!panel.open || !isCurrent()) return;
      [...panel.children].slice(1).forEach((element) => element.remove());
      const note = document.createElement('p');
      note.textContent = 'These are saved working stages, not released advice or private deliberation.';
      panel.appendChild(note);
      try {
        const root = `/api/matters/${encodeURIComponent(matterId)}/loops`;
        const population = turnId
          ? { loops: [await read(`${root}/${encodeURIComponent(turnId)}`)] }
          : await read(root);
        if (!current(generation)) return;
        if (!Array.isArray(population.loops)) throw new Error('The work list could not be verified.');
        const loops = population.loops.filter((loop) => turnId
          ? loop.linked_released_turn === true : !unlinkedOnly || loop.linked_released_turn !== true);
        if (!loops.length) {
          const empty = document.createElement('p');
          empty.textContent = turnId ? 'Work cannot currently be linked to this released response.'
            : 'No other autonomous work is recorded on this matter.';
          panel.appendChild(empty);
        }
        loops.forEach((loop, index) => {
          const detail = document.createElement('details');
          const heading = document.createElement('summary');
          heading.textContent = turnId ? 'Saved working stages'
            : `Work ${index + 1}${loop.terminal ? ' — ended' : ' — completion not confirmed'}`;
          detail.appendChild(heading);
          panel.appendChild(detail);
          let stream = null;
          let detailGeneration = 0;
          detail.addEventListener('toggle', async () => {
            if (stream) { stream.close(); streams.delete(stream); localStreams.delete(stream); }
            const thisDetail = ++detailGeneration;
            if (!detail.open || !current(generation)) return;
            [...detail.children].slice(1).forEach((element) => element.remove());
            const list = document.createElement('ol');
            list.className = 'progress-stages';
            list.setAttribute('aria-label', 'Saved working stages');
            const status = document.createElement('p');
            status.setAttribute('role', 'status');
            status.setAttribute('aria-live', 'polite');
            detail.append(list, status);
            const seen = new Set();
            let recordedScope = null;
            const active = () => thisDetail === detailGeneration && detail.open && current(generation);
            function add(row) {
              if (!active() || !row || typeof row.label !== 'string'
                  || row.working_not_advice !== true || typeof row.cursor !== 'string'
                  || !/^[0-9]{1,9}\.[a-f0-9]{64}$/.test(row.cursor)) return;
              if (row.dispute_index !== undefined &&
                  (!Number.isSafeInteger(row.dispute_index) || row.dispute_index < 1 ||
                   recordedScope?.state !== 'recorded' ||
                   !Array.isArray(recordedScope.disputes) || row.dispute_index > 1000)) return;
              if (seen.has(row.cursor)) return;
              seen.add(row.cursor);
              const item = document.createElement('li');
              item.textContent = row.dispute_index === undefined
                ? row.label : `Dispute ${row.dispute_index}: ${row.label}`;
              list.appendChild(item);
              status.textContent = item.textContent;
              if (row.state !== 'working' && stream) {
                stream.close(); streams.delete(stream); localStreams.delete(stream);
              }
            }
            const base = `/api/matters/${encodeURIComponent(matterId)}/loops/${encodeURIComponent(loop.turn_id)}`;
            try {
              const record = await read(base);
              if (!active()) return;
              if (!Array.isArray(record.events)) throw new Error('The saved stages could not be verified.');
              recordedScope = record.scope;
              if (turnId && record.linked_released_turn !== true) {
                throw new Error('The released response link could not be verified.');
              }
              const scope = document.createElement('section');
              scope.className = 'progress-scope';
              scope.setAttribute('aria-label', 'Recorded working scope');
              const scopeNote = document.createElement('p');
              scope.appendChild(scopeNote);
              if (record.scope?.state === 'recorded' && Array.isArray(record.scope.disputes)) {
                scopeNote.textContent = record.scope.disputes.length
                  ? 'Disputes in the recorded working scope:' : 'The recorded scope was the opening matter file.';
                const disputes = document.createElement('ul');
                record.scope.disputes.forEach((dispute) => {
                  if (typeof dispute.label !== 'string') return;
                  const name = document.createElement('li');
                  name.textContent = dispute.label;
                  disputes.appendChild(name);
                });
                scope.appendChild(disputes);
              } else {
                scopeNote.textContent = 'Dispute-specific working scope was not established in this record.';
              }
              const shared = document.createElement('p');
              shared.textContent = 'Only source-linked information-needs and single-dispute opposition receipts are marked by dispute here. Authority and provision reads remain shared; no working stage establishes legal assessment.';
              scope.appendChild(shared);
              detail.insertBefore(scope, list);
              record.events.forEach(add);
              if (!record.terminal) {
                stream = new EventSource(`${base}/progress?after=${encodeURIComponent(record.cursor)}`,
                                         { withCredentials: true });
                streams.add(stream); localStreams.add(stream);
                stream.addEventListener('progress', (event) => {
                  if (!active()) { stream.close(); return; }
                  try { add(JSON.parse(event.data)); }
                  catch { stream.close(); status.textContent = 'A progress update could not be verified.'; }
                });
                stream.onerror = async () => {
                  stream.close(); streams.delete(stream); localStreams.delete(stream);
                  if (!active()) return;
                  // Reuse the central authenticated reader: 401 ends the
                  // session and clears privileged content, rather than leaving
                  // this fold alive behind an expired EventSource connection.
                  try {
                    const latest = await read(base);
                    if (!active()) return;
                    latest.events.forEach(add);
                    if (!latest.terminal) status.textContent = 'Live updates paused. Reopen to refresh the saved stages.';
                  } catch (error) {
                    if (active() && !error.obsolete) status.textContent = 'The current work status could not be read.';
                  }
                };
              }
            } catch (error) {
              if (active() && !error.obsolete) status.textContent = 'The saved stages could not be read. Reopen to try again.';
            }
          });
          if (turnId) detail.open = true;
        });
      } catch (error) {
        if (current(generation) && !error.obsolete) note.textContent = 'The recorded work could not be read. Reopen to try again.';
      }
    });
    return panel;
  }
  async function attachTurn(container, matterId, turnId, { read, isCurrent }) {
    // Presence in the private journal is not release. The actual strict
    // receipt, applied-turn ledger and original offer must agree on the server.
    try {
      const record = await read(`/api/matters/${encodeURIComponent(matterId)}/loops/${encodeURIComponent(turnId)}`);
      if (!container.isConnected || !isCurrent() || record.linked_released_turn !== true) return null;
      return attach(container, matterId, { read, isCurrent, turnId });
    } catch { return null; } // Legacy turns without journals do not gain an empty work panel.
  }
  window.NMLoopProgress = Object.freeze({ attach, attachTurn, stopAll });
})();
