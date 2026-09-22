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
  const page = await api(read.url + `?offset=${offset}`);
  if (!ownsSourceRead(read)) return null;
  if (page.digest !== read.digest || page.offset !== offset
      || page.coverage !== 'saved_passage' || typeof page.text !== 'string') {
    throw new Error('The saved source identity changed.');
  }
  return page;
}

function sourceReadError(read) {
  if (!ownsSourceRead(read)) return;
  read.text = ''; read.pages = []; read.next = null;
  for (const id of ['source-text', 'source-qualification', 'source-meta']) {
    sourceNode(id).replaceChildren();
  }
  sourceNode('source-status').textContent = 'The saved passage could not be opened. '
    + 'No replacement source has been substituted. Check your access and retry.';
  sourceNode('source-retry').hidden = false;
  sourceNode('source-more').hidden = true;
  sourceNode('source-copy').disabled = true;
}

function paintSourceText() {
  if (!sourceRead) return;
  const text = sourceRead.text, query = sourceNode('source-search').value;
  const host = sourceNode('source-text');
  host.replaceChildren();
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
  sourceNode('source-search-result').textContent = query
    ? `${count === 500 ? 'At least ' : ''}${count} match${count === 1 ? '' : 'es'} in loaded text only (case-sensitive).`
    : 'Search covers the loaded saved passage only, not the full document.';
}

async function loadSourcePage(read, offset = 0) {
  if (!ownsSourceRead(read) || read.loading) return;
  read.loading = true;
  sourceNode('source-more').disabled = true;
  sourceNode('source-copy').disabled = true;
  sourceNode('source-retry').hidden = true;
  sourceNode('source-status').textContent = 'Opening the saved passage…';
  try {
    const page = await readSourcePage(read, offset);
    if (!page) return;
    if (offset === 0) { read.text = ''; read.pages = []; }
    read.text += page.text; read.pages.push(offset); read.next = page.next_offset;
    read.qualification = page.qualification; read.label = page.label;
    read.locator = page.locator;
    sourceNode('source-title').textContent = page.label;
    sourceNode('source-meta').textContent = `Saved with the response on ${page.recorded_at}. `
      + `Content identity ${page.digest.slice(0, 12)}. `
      + (page.valid_from ? `Recorded effective from ${page.valid_from}. ` : '')
      + (page.valid_to ? `Recorded effective to ${page.valid_to}. ` : '')
      + 'This is not a new check of legal currency or applicability.';
    sourceNode('source-qualification').textContent = page.qualification;
    sourceNode('source-status').textContent = page.next_offset === null
      ? 'All of this saved passage is loaded. The full document was not retained with this answer.'
      : `${page.next_offset} of ${page.total_characters} saved passage characters loaded. More is available below.`;
    sourceNode('source-more').hidden = page.next_offset === null;
    sourceNode('source-copy').disabled = false;
    paintSourceText();
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
    url: `/api/matters/${encodeURIComponent(answer.matter_id)}/turns/`
      + `${encodeURIComponent(answer.turn_id)}/sources/${elementIndex}` };
  sourceRead = read;
  sourceNode('source-title').textContent = el.source.label;
  sourceNode('source-more').hidden = true;
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
    await navigator.clipboard.writeText(`${read.label}\n${read.locator}\n`
      + `Saved content ${read.digest}\nLoaded saved passage only; not the full document.\n\n`
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
sourceNode('source-return').addEventListener('click', () => {
  sourceNode('source-text').scrollIntoView({ block: 'start' });
  sourceNode('source-text').focus({ preventScroll: true });
});
