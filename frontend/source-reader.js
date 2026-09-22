/* Read a released saved passage; never resolve a label or start legal research. */
'use strict';
let sourceRead = null;
let sourceReadGeneration = 0;
const sourceNode = id => document.getElementById(id);

function closeSourceReader(restore = true) {
  const previous = sourceRead;
  sourceRead = null; sourceReadGeneration += 1;
  const dialog = sourceNode('source-reader');
  if (dialog.open) dialog.close();
  for (const id of ['source-text', 'source-meta', 'source-qualification',
    'source-status', 'source-search-result']) sourceNode(id).replaceChildren();
  sourceNode('source-title').textContent = 'Source passage';
  sourceNode('source-search').value = '';
  if (restore && previous) {
    const target = previous.opener?.isConnected ? previous.opener : sourceNode('message');
    if (target && !target.closest('[hidden]')) target.focus({ preventScroll: true });
  }
}

function ownsSourceRead(read) {
  return sourceRead === read && read.generation === sourceReadGeneration
    && read.session === state.sessionGeneration && read.advocate === state.advocate
    && read.pageMatter === state.matterId && sourceNode('source-reader').open;
}

async function readSourcePage(read, offset) {
  const page = await api(read.url + `?offset=${offset}&view=${read.view}`
    + (read.documentIdentity ? `&document_identity=${encodeURIComponent(read.documentIdentity)}` : ''));
  if (!ownsSourceRead(read)) return null;
  // The coverage the server states must be the coverage this view asked for.
  // A document page accepted into the passage view would put the current text
  // under a heading that says "exact saved retrieved passage".
  const wanted = read.view === 'document' ? 'stored_document' : 'saved_passage';
  if (page.digest !== read.digest || page.offset !== offset
      || page.coverage !== wanted || typeof page.text !== 'string') {
    throw new Error('The saved source identity changed.');
  }
  if (read.view === 'document') {
    if (typeof page.document_identity !== 'string' || !page.document_identity
        || (read.documentIdentity && read.documentIdentity !== page.document_identity)) {
      throw new Error('The current document changed while reading.');
    }
    read.documentIdentity = page.document_identity;
  }
  return page;
}

function sourceReadError(read) {
  if (!ownsSourceRead(read)) return;
  read.text = ''; read.pages = []; read.next = null;
  for (const id of ['source-text', 'source-qualification', 'source-meta']) {
    sourceNode(id).replaceChildren();
  }
  sourceNode('source-status').textContent = (read.view === 'document'
    ? 'The current document could not be opened consistently. Return to the saved passage, or reopen the citation. '
    : 'The saved passage could not be opened. ')
    + 'No replacement source has been substituted. Check your access and retry.';
  sourceNode('source-passage').hidden = read.view !== 'document';
  sourceNode('source-retry').hidden = false;
  sourceNode('source-more').hidden = true;
  sourceNode('source-copy').disabled = true;
}

function paintSourceText() {
  if (!sourceRead) return;
  const text = sourceRead.text, query = sourceNode('source-search').value;
  const host = sourceNode('source-text');
  host.replaceChildren();
  if (!query && sourceRead.view === 'document' && sourceRead.anchor !== null
      && sourceRead.anchor !== undefined) {
    // THE CITED SPAN, marked as itself and not as a search hit. Only when it
    // was located by its own text: a span the current document does not carry
    // is reported, never approximated to the nearest paragraph.
    const start = sourceRead.anchor - sourceRead.pages[0];
    const stop = start + sourceRead.anchorLength;
    if (start >= 0 && stop <= text.length) {
      host.appendChild(document.createTextNode(text.slice(0, start)));
      const cited = document.createElement('mark');
      cited.className = 'cited-span';
      cited.id = 'source-cited-span';
      cited.textContent = text.slice(start, stop);
      host.appendChild(cited);
      host.appendChild(document.createTextNode(text.slice(stop)));
      sourceNode('source-search-result').textContent =
        'The passage this answer relied on is marked in the current text.';
      return;
    }
  }
  let cursor = 0, count = 0, position;
  // Literal case-sensitive matching preserves Unicode offsets. Never parse HTML.
  while (query && (position = text.indexOf(query, cursor)) !== -1) {
    host.appendChild(document.createTextNode(text.slice(cursor, position)));
    const mark = document.createElement('mark');
    mark.textContent = text.slice(position, position + query.length);
    host.appendChild(mark); cursor = position + query.length; count += 1;
    if (count >= 500) break;
  }
  host.appendChild(document.createTextNode(text.slice(cursor)));
  const scope = sourceRead.view === 'document'
    ? 'the loaded part of the current document' : 'the loaded text';
  sourceNode('source-search-result').textContent = query
    ? `${count === 500 ? 'At least ' : ''}${count} match${count === 1 ? '' : 'es'} in ${scope} only (case-sensitive). `
      + 'No match here does not mean the word is absent from the rest.'
    : `Search covers ${scope} only.`;
}

async function loadSourcePage(read, offset = 0) {
  if (!ownsSourceRead(read) || read.loading) return;
  read.loading = true;
  sourceNode('source-more').disabled = true;
  sourceNode('source-copy').disabled = true;
  sourceNode('source-retry').hidden = true;
  sourceNode('source-status').textContent = 'Opening the saved passage…';
  try {
    let page = await readSourcePage(read, offset);
    if (!page) return;
    if (offset === 0) { read.text = ''; read.pages = []; }
    if (offset === 0 && read.view === 'document' && read.atCitation !== false
        && page.anchor_offset !== null && page.anchor_offset >= page.text.length) {
      page = await readSourcePage(read, Math.floor(page.anchor_offset / 6000) * 6000);
      if (!page) return;
    }
    read.text += page.text; read.pages.push(page.offset); read.next = page.next_offset;
    // A cited passage may cross a page boundary. Load its remaining pages before
    // claiming to have opened at it, retaining the same document identity.
    if (offset === 0 && read.view === 'document' && read.atCitation !== false
        && page.anchor_offset !== null) {
      const end = page.anchor_offset + page.anchor_length;
      while (read.next !== null && read.next < end) {
        page = await readSourcePage(read, read.next);
        if (!page) return;
        read.text += page.text; read.pages.push(page.offset); read.next = page.next_offset;
      }
    }
    read.qualification = page.qualification; read.label = page.label;
    read.locator = page.locator;
    sourceNode('source-title').textContent = page.label;
    sourceNode('source-meta').textContent = `Saved with the response on ${page.recorded_at}. `
      + `Content identity ${page.digest.slice(0, 12)}. `
      + (page.valid_from ? `Recorded effective from ${page.valid_from}. ` : '')
      + (page.valid_to ? `Recorded effective to ${page.valid_to}. ` : '')
      + 'This is not a new check of legal currency or applicability.';
    sourceNode('source-qualification').textContent = page.qualification;
    if (read.view === 'document') {
      read.anchor = page.anchor_offset; read.anchorLength = page.anchor_length || 0;
      sourceNode('source-coverage').textContent =
        `The source as this corpus holds it now${page.snapshot_id ? ` (generation ${page.snapshot_id})` : ''}`
        + ' · extracted text, not an original facsimile.';
      // A CHANGED SOURCE IS A FINDING, not a silent substitution: the owner
      // asked for the latest text, so the reader shows it and says plainly
      // when it is no longer the text the answer rested on.
      sourceNode('source-anchor-note').textContent = page.anchor_note || '';
      sourceNode('source-anchor-note').hidden = !page.anchor_note;
      sourceNode('source-meta').textContent = `Current document ${page.document_identity.slice(0, 12)}. `
        + `The answer relied on saved passage ${page.digest.slice(0, 12)} from ${page.recorded_at}. `
        + 'Opening the current text does not reassess the saved answer.';
      sourceNode('source-status').textContent = read.pages[0] === 0 && page.next_offset === null
        ? `All ${page.total_characters} characters of the stored document are loaded.`
        : `Showing characters ${read.pages[0] + 1}–${page.offset + page.text.length} `
          + `of ${page.total_characters}. Earlier text is available from Beginning of document.`;
    } else {
      sourceNode('source-anchor-note').hidden = true;
      sourceNode('source-full').hidden = !page.full_document_available;
      read.fullWhyNot = page.full_document_unavailable_because || '';
      sourceNode('source-status').textContent = page.next_offset === null
        ? 'All of this saved passage is loaded.'
          + (page.full_document_available ? ' Full document is available below.'
             : ` The full document is not available: ${read.fullWhyNot}`)
        : `${page.next_offset} of ${page.total_characters} saved passage characters loaded. More is available below.`;
    }
    sourceNode('source-more').hidden = page.next_offset === null;
    sourceNode('source-more').textContent = read.view === 'document'
      ? 'Load more of this document' : 'Load more of this passage';
    sourceNode('source-passage').hidden = read.view !== 'document';
    sourceNode('source-beginning').hidden = read.view !== 'document';
    sourceNode('source-copy').disabled = false;
    paintSourceText();
    if (read.view === 'document' && offset === 0) scrollToCitedSpan();
  } catch { sourceReadError(read); }
  finally {
    read.loading = false;
    if (ownsSourceRead(read)) sourceNode('source-more').disabled = false;
  }
}

function openSourceReader(answer, el, elementIndex, opener) {
  closeSourceReader(false);
  const read = { generation: sourceReadGeneration, session: state.sessionGeneration,
    advocate: state.advocate, pageMatter: state.matterId, opener,
    digest: el.source.digest, text: '', pages: [], next: null, loading: false,
    view: 'passage', anchor: null, anchorLength: 0, fullWhyNot: '',
    documentIdentity: '', atCitation: true,
    url: `/api/matters/${encodeURIComponent(answer.matter_id)}/turns/`
      + `${encodeURIComponent(answer.turn_id)}/sources/${elementIndex}` };
  sourceRead = read;
  sourceNode('source-title').textContent = el.source.label;
  sourceNode('source-more').hidden = true;
  sourceNode('source-full').hidden = true;
  sourceNode('source-passage').hidden = true;
  sourceNode('source-beginning').hidden = true;
  sourceNode('source-anchor-note').hidden = true;
  sourceNode('source-coverage').textContent = 'Exact saved retrieved passage · extracted '
    + 'text, not an original facsimile or the complete Act or judgment.';
  sourceNode('source-reader').showModal();
  sourceNode('source-close').focus();
  loadSourcePage(read);
}

async function copySourcePassage() {
  const read = sourceRead;
  if (!read || read.loading || !read.text) return;
  const text = read.text, pages = [...read.pages], qualification = read.qualification;
  sourceNode('source-copy').disabled = true;
  try {
    // Reauthorise all copied pages; cached text is not an access grant.
    for (const offset of pages) if (!await readSourcePage(read, offset)) return;
  } catch { sourceReadError(read); return; }
  if (!ownsSourceRead(read)) return;
  try {
    const coverageLine = read.view === 'document'
      ? `Current document ${read.documentIdentity}.\n`
        + 'Loaded part of the stored document as this corpus holds it now; not a facsimile.\n'
        + sourceNode('source-anchor-note').textContent
      : 'Loaded saved passage only; not the full document.';
    await navigator.clipboard.writeText(`${read.label}\n${read.locator}\n`
      + `Saved content ${read.digest}\n${coverageLine}\n\n`
      + `${text}\n\nQualification recorded with this response:\n${qualification}`);
    if (ownsSourceRead(read)) sourceNode('source-status').textContent = 'Copied the loaded passage with its attribution, coverage and recorded qualifications.';
  } catch {
    if (ownsSourceRead(read)) sourceNode('source-status').textContent = 'Copy was not permitted by the browser. The passage remains selectable; include its attribution and qualifications.';
  } finally { if (ownsSourceRead(read)) sourceNode('source-copy').disabled = !read.text; }
}

sourceNode('source-close').addEventListener('click', () => closeSourceReader());
sourceNode('source-reader').addEventListener('cancel', event => { event.preventDefault(); closeSourceReader(); });
sourceNode('source-reader').addEventListener('close', () => {
  if (sourceRead && !sourceNode('source-reader').open) closeSourceReader();
});
sourceNode('source-more').addEventListener('click', () => { if (sourceRead) loadSourcePage(sourceRead, sourceRead.next); });
sourceNode('source-retry').addEventListener('click', () => { if (sourceRead) loadSourcePage(sourceRead); });
sourceNode('source-copy').addEventListener('click', copySourcePassage);
sourceNode('source-search').addEventListener('input', paintSourceText);
function scrollToCitedSpan() {
  const cited = sourceNode('source-cited-span');
  const target = cited || sourceNode('source-text');
  target.scrollIntoView({ block: 'center' });
  sourceNode('source-text').focus({ preventScroll: true });
}

function switchSourceView(view) {
  const read = sourceRead;
  if (!read || read.loading || read.view === view) return;
  read.view = view; read.text = ''; read.pages = []; read.next = null;
  read.documentIdentity = ''; read.atCitation = true;
  read.anchor = null; read.anchorLength = 0;
  sourceNode('source-search').value = '';
  loadSourcePage(read);
}

sourceNode('source-full').addEventListener('click', () => switchSourceView('document'));
sourceNode('source-passage').addEventListener('click', () => switchSourceView('passage'));
sourceNode('source-return').addEventListener('click', () => {
  if (sourceRead?.view === 'document' && !sourceNode('source-cited-span')) {
    sourceRead.atCitation = true; loadSourcePage(sourceRead);
  } else scrollToCitedSpan();
});
sourceNode('source-beginning').addEventListener('click', () => {
  if (sourceRead) { sourceRead.atCitation = false; loadSourcePage(sourceRead); }
});
