// Targeted edits through the bundled Artifact Tool, with its permitted unavailable-library fallback.
// Preview first. Publish only after the independent saved-file preservation check.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

let artifact;
try { artifact = await import('@oai/artifact-tool'); }
catch (error) {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  console.log('Bundled Artifact Tool unavailable; using the permitted openpyxl fallback.');
}

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const sourceFlag = process.argv.indexOf('--source');
const source = sourceFlag < 0 ? path.join(root, 'docs/Nyaymalaw_Implementation_Plan.xlsx')
  : path.resolve(process.argv[sourceFlag + 1]);
const progressFlag = process.argv.indexOf('--progress');
const progress = progressFlag < 0 ? null : JSON.parse(await fs.readFile(
  path.resolve(process.argv[progressFlag + 1]), 'utf8'));
const output = path.join(root, 'outputs/01a07b76-6b21-71f3-bb09-261f64617594',
  progress ? 'legal-brain-build-20260927' : 'legal-brain-refinements-20260927');
const stamp = '27 September 2026 targeted refinements (owner authorised)';
const python = 'C:/Users/rahul/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
await fs.mkdir(output, { recursive: true });
const sourceBytes = await fs.readFile(source);
const book = artifact ? await artifact.SpreadsheetFile.importXlsx(await artifact.FileBlob.load(source)) : null;
const fallbackRows = book ? null : JSON.parse(execFileSync(python, ['-B', '-c', `
import json,sys
from openpyxl import load_workbook
b=load_workbook(sys.argv[1],read_only=True)
print(json.dumps({s.title:list(s.values) for s in b},default=str))
b.close()
`, source], { maxBuffer: 16 * 1024 * 1024, encoding: 'utf8' }));
const before = book?.worksheets.getItem('Before Build');
const plan = book?.worksheets.getItem('Implementation Plan');
const bb = book ? before.getUsedRange().values : fallbackRows['Before Build'];
const ip = book ? plan.getUsedRange().values : fallbackRows['Implementation Plan'];
const byId = new Map(bb.flatMap((row, i) => {
  const id = String(row[0] ?? '').match(/^(LB-\d+|OM-[PIQ]\d+)\b/)?.[1];
  return id ? [[id, i]] : [];
}));
const planById = new Map(ip.map((row, i) => [row[0], i]));
const edits = [];
const changed = new Set();
function column(n) {
  let s = '';
  for (let x = n; x; x = Math.floor((x - 1) / 26)) s = String.fromCharCode(65 + (x - 1) % 26) + s;
  return s;
}
function write(sheet, matrix, row, col, value) {
  const old = matrix[row]?.[col - 1] ?? null;
  if (old === value) return;
  const address = column(col) + (row + 1);
  edits.push({ sheet: matrix === bb ? 'Before Build' : 'Implementation Plan', address, before: old, after: value });
  if (book) sheet.getRange(address).values = [[value]];
  matrix[row][col - 1] = value;
}
function set(id, col, value) {
  if (!byId.has(id)) throw new Error(`No Before Build row: ${id}`);
  changed.add(id);
  write(before, bb, byId.get(id), col, value);
}
function replace(id, col, old, value) {
  const text = String(bb[byId.get(id)]?.[col - 1] ?? '');
  if (text.split(old).length !== 2) throw new Error(`${id} column ${col}: expected one exact old clause`);
  set(id, col, text.replace(old, value));
}
function append(id, col, text) {
  const old = bb[byId.get(id)][col - 1];
  set(id, col, old ? `${old}\n\n${text}` : text);
}

function fallbackPreview(file, target) {
  // A labelled reading preview, not a claim to have run Excel's layout engine.
  const entries = progress ? [
    ...progress.rows.map(row => ({sheet:'Before Build',cell:`J${byId.get(row.id) + 1}`})),
    {sheet:'Implementation Plan',cell:`AM${planById.get(progress.rows[0].id) + 1}`},
    {sheet:'Implementation Plan',cell:`AN${planById.get(progress.rows[0].id) + 1}`},
    ...progress.rows.map(row => ({sheet:'Implementation Plan',cell:`AR${planById.get(row.id) + 1}`})),
  ] : ['C190','D190','E190','H191','H225'].map(cell => ({sheet:'Before Build',cell}));
  execFileSync(python, ['-B', '-c', `
import json,sys,textwrap
from openpyxl import load_workbook
from PIL import Image,ImageDraw,ImageFont
b=load_workbook(sys.argv[1],read_only=True)
s=b['Before Build']
font=ImageFont.truetype('C:/Windows/Fonts/calibri.ttf',16)
bold=ImageFont.truetype('C:/Windows/Fonts/calibrib.ttf',18)
entries=[(e['sheet']+'!'+e['cell'],str(b[e['sheet']][e['cell']].value or '')) for e in json.loads(sys.argv[3])]
wrapped=[(k,[line for para in v.splitlines() for line in (textwrap.wrap(para,112) or [''])]) for k,v in entries]
height=70+sum(42+22*len(lines) for _,lines in wrapped)
im=Image.new('RGB',(980,height),'white'); d=ImageDraw.Draw(im); y=20
d.text((20,y),'Before Build - expanded reading preview (not an Excel rendering)',font=bold,fill='#1C3B35'); y+=45
for k,lines in wrapped:
 d.text((20,y),k,font=bold,fill='#1C3B35'); y+=28
 for line in lines:
  d.text((20,y),line,font=font,fill='#202020'); y+=22
 y+=14
im.save(sys.argv[2]); b.close()
`, file, target, JSON.stringify(entries)]);
}
if (process.argv.includes('--preview-only')) {
  if (book) {
    const image = await book.render({ sheetName: 'Before Build', range: 'C190:E190', scale: 1 });
    await fs.writeFile(path.join(output, 'before.png'), new Uint8Array(await image.arrayBuffer()));
  } else fallbackPreview(source, path.join(output, 'before.png'));
  console.log(JSON.stringify({ source_hash: digest(sourceBytes), preview: path.join(output, 'before.png') }));
  process.exit(0);
}
if (!process.argv.includes('--edit')) throw new Error('Use --preview-only before --edit');
if (progress) {
  if (progress.schema !== 1 || typeof progress.record !== 'string' || !progress.record.trim()
      || !Array.isArray(progress.rows) || !progress.rows.length) throw new Error('Invalid progress record');
  if (progress.checkpoint !== undefined && (typeof progress.checkpoint !== 'string'
      || !progress.checkpoint.trim())) throw new Error('Invalid progress checkpoint');
  const ids = new Set();
  for (const entry of progress.rows) {
    if (ids.has(entry.id) || !byId.has(entry.id) || !planById.has(entry.id)) throw new Error('Unknown/duplicate progress row');
    ids.add(entry.id);
    if (Object.keys(entry).sort().join(',') !== 'evidence,gaps,id,progress,verification') throw new Error('Unknown progress fields');
    if ([entry.progress, entry.evidence, entry.gaps].some(value => typeof value !== 'string' || !value.trim())) throw new Error('Empty progress evidence');
    if (entry.verification !== 'Controlled checks passed; acceptance incomplete') throw new Error('This build record cannot self-certify acceptance');
    const old = String(bb[byId.get(entry.id)][9] ?? '');
    if (old.includes(progress.record)) throw new Error(`Progress already recorded: ${entry.id}`);
    append(entry.id, 10, `${progress.record}: ${entry.progress} Acceptance remains incomplete. Normal client cutover is not authorised.`);
    const row = planById.get(entry.id);
    write(plan, ip, row, 30, bb[byId.get(entry.id)][9]);
    write(plan, ip, row, 39, 'In progress');
    write(plan, ip, row, 40, entry.verification);
    write(plan, ip, row, 41, entry.evidence);
    write(plan, ip, row, 43, progress.checkpoint ?? '27 September 2026: scoped controlled tests; no paid model quality evaluation or professional acceptance.');
    write(plan, ip, row, 44, entry.gaps);
  }
} else {
if (String(bb[byId.get('LB-43')][9]).includes(stamp)) throw new Error('Already applied');

replace('LB-163', 8,
  'LB-163-AC3 (planted): an answer missing a required section with no stated reason is refused.',
  'LB-163-AC3 (planted): for the analysis the request calls for, a missing material finding or required analysis on the working record is refused. A narrow reply without irrelevant headings passes; the harness does not require every published reply to reproduce the seven-part comprehensive brief.');
replace('LB-165', 8,
  'LB-165-AC1: on a golden two-dispute matter each dispute carries all seven sections, or a reason for each one absent.',
  'LB-165-AC1: when a comprehensive brief is requested on a golden multi-dispute matter, each dispute covers the seven applicable analysis areas or records why an area cannot be assessed or is inapplicable. The working record retains that assessment. A narrow question, acknowledgement or correction publishes only the relevant supported response and does not list unused headings.');
replace('LB-161', 4,
  'asks one focused question and records it so it is not asked again',
  'asks a focused question or a small related group justified by the highest-value gaps (LB-118), and records them so answered questions are not repeated');
replace('LB-161', 4,
  'asks the one question that would change it',
  'asks only the question or small group that would materially change it, without a fixed numerical quota');
set('LB-161', 5,
  'The advocate receives the useful checked answer already supportable, any necessary focused question or small related group, and an approval request only when an external act needs approval. An answer and questions may coexist in one turn.');
replace('LB-143', 8,
  'LB-143-AC2 (planted): a result with no locator is refused before the model sees it.',
  'LB-143-AC2: a source-read receipt missing its required exact locator is refused before model use. Valid computation and action receipts without document locators are accepted when their own inputs/rule/calculation or approval/effect fields are complete. Planted: omitting a required field for any registered tool kind is refused; inventing a document locator cannot cure it.');

set('LB-141', 3,
  'Every submitted claim of law, authority or document fact, every applied legal assessment, and every derived legal or strategic conclusion or recommendation, including the final conclusion and its dependent claims.');
set('LB-141', 4,
  'An independent model instance, never the author and never shown the conversation, receives a typed evidence package: the claim, exact minimum source spans, established premises (facts, dates, jurisdiction and governing law), dependency links and contrary material. It states its reason with supporting words before its verdict. Four judgments are recorded separately: textual support, applicability, inference from the premises, and unresolved material opposition. Applied assessments and derived recommendations require all relevant judgments, including review of the final conclusion itself. A genuinely textual report with no implied applicability, inference or recommendation requires textual support only. Eligibility follows independently checked claim content and dependencies; the author cannot exempt applied advice by labelling it textual. A missing or ambiguous classification goes to repair or the fuller review, never a bypass. Partial support permits only an independently checked, self-contained supported part whose meaning survives the omitted part. Deterministic citation, quote, in-force and binding checks run first. Failed judgments repair under LB-133. Tier qualification and both error directions are measured under LB-71 and AC2/AC4.');
set('LB-141', 5,
  'Every released claim has passed the judgments it requires. A recommendation is released only when its material premises and final inference pass, with no unresolved decisive contrary information. Partial release preserves only independently checked, self-contained material and states the specific remaining gap. A disclaimer never grants release eligibility.');
set('LB-141', 6,
  'Unavailable verification is recorded as not assessed, never supports. Withhold the affected decisive conclusion and its dependants, disclose the capability gap, and preserve unresolved work for repair or qualified review. Independently verified material may still be answered. No unverified assertion is released merely because it is labelled background or carries a disclaimer.');
append('LB-141', 7,
  'Never let an author-supplied claim label determine which semantic checks may be skipped. Never treat correct premises as proof of the inference drawn from them.');
replace('LB-141', 8,
  'LB-141-AC2: on a set of claim-passage pairs labelled by the owner, the verifier\'s agreement is measured and reported, never assumed.',
  'LB-141-AC2: on owner-labelled evidence packages containing exact spans, established premises, contrary material and final derived conclusions, measure and report agreement separately for textual support, applicability, inference and unresolved opposition. Include both valid and invalid conclusions, partial/unavailable verification and claim-misclassification controls; never assume agreement from citation accuracy.');
replace('LB-141', 9,
  'OPEN: the labelled pair set and the agreement threshold.',
  'OPEN: the labelled evidence-package set, qualified four-judgment labels and the agreement threshold.');
replace('LB-141', 8,
  "LB-141-AC3: a verifier that cannot run yields a disclosed 'not verified'.",
  'LB-141-AC3 (planted): when a required verifier cannot run, the verdict is not assessed; a disclaimer does not release the decisive recommendation or its dependants. Independent checked material remains available, and the unfinished need stays open.');
append('LB-141', 8,
  'LB-141-AC6 (planted): every cited premise is correct but the derived conclusion does not follow; the inference judgment fails and blocks that conclusion. Labelling the same applied assessment as a textual quotation does not remove its applicability/inference checks. Repeat across varied practice areas and recommendation forms, not one wording.');

replace('LB-156', 4,
  'All wrap existing code: the manifest\'s exact resolution, the evidence port\'s fetch, and the governing-law table.',
  'Exact identity and governing-code lookup wrap existing code. Historical provision-version selection remains to be built: select the exact provision revision on a verified effective interval, retaining amendment/commencement authority, transition premises, source version and span. A whole Act\'s lifetime is not proof that its section wording applied on a date.');
append('LB-156', 6,
  'If the requested historical revision cannot be established, return not assessed naming the missing version evidence. Do not silently return current text as historical text. Current text may be read separately with its own date and version, without establishing the historical proposition.');
append('LB-156', 8,
  'LB-156-AC4: for the same exact Act and provision, dates before and after a verified amendment resolve to the respective distinct spans with effective intervals and amendment/commencement sources. Planted: remove historical-version evidence while retaining current text and the Act lifetime; the historical request becomes not assessed, never current text presented as historical. Where transitional applicability is unresolved, disclose and withhold the dependent conclusion.');
append('LB-156', 9,
  'Historical provision-version and effective-interval proof is owned by BK-98-AC2 (P48), read through the BK-99-AC2 tools (P50). Exact identity improvement alone does not close LB-156-AC4. This prerequisite remains pending.');
replace('LB-156', 9,
  'Delivery owner (registered 26 September 2026, LB-43): BK-99-AC2 for the tools, packet P50; exact Act identity stays BK-97 (P21).',
  'Delivery owner (registered 26 September 2026, refined 27 September 2026 under LB-43): BK-99-AC2 for the tools (P50); BK-98-AC2 for provision read-back and historical-version proof (P48); exact Act identity stays BK-97 (P21).');

replace('LB-43', 8,
  'LB-43-AC4: Enumerate all 92 LB requirements and 324 clauses: each selected delivery clause must resolve to an accountable registered owner/evidence contract; missing mappings block that scope, not silently vanish.',
  'LB-43-AC4: Enumerate every LB and OM requirement and acceptance clause from the current sheet. Resolve each selected delivery row to registered criterion/item and packet ownership; invalid or unowned scope blocks readiness. This row-level ownership check does not establish clause-level evidence coverage.');
append('LB-43', 4,
  'Before each slice starts, its approved scope record enumerates the selected requirement/AC IDs and the transitive prerequisite closure, including unowned requirements and owner decisions. For each clause map the registered criterion, serving path, verification method, rejecting control and expected evidence artifact. Shared evidence may cover several clauses only when each coverage relationship is explicit. Store the map with the requirement/registry version and tested source identity; regenerate it when scope changes. Row ownership and prerequisites in a packet alone do not certify this coverage.');
append('LB-43', 8,
  'LB-43-AC7: each selected slice has a non-empty explicit clause/evidence map and prerequisite closure checked against current workbook and packet registries. Planted: retain the row owner but add an unmapped acceptance clause, omit a transitive prerequisite, or select an unowned prerequisite; that scope remains blocked. An unresolved owner decision is recorded as a blocker, not silently excluded. This coverage checker and the slice records remain pending until implemented and exercised.');
append('LB-138', 4,
  'Before building and again before completion, each slice provides LB-43\'s explicit clause/evidence map and prerequisite closure at the current requirement version. The row-ownership CLI is a narrower preliminary check, not permission to skip the missing coverage checker or required owner decisions.');
append('LB-138', 8,
  'LB-138-AC4 (planted): a slice whose row ownership passes but which lacks a selected clause\'s evidence contract or a required prerequisite fails readiness; no completion claim is made from the ownership CLI alone.');

append('LB-40', 4,
  'RG-32 defines evaluation tolerance, never runtime permission to publish a known unsupported claim. RG-37 counts all attempt spend, including failed/cancelled work, retries, repairs and unfinished tasks, with populations and completion rate disclosed. The exact measurement definitions and unchanged thresholds remain owned by release.yaml.');

// The mirror is the same source contract used by plan_scenarios.requirement_problems().
const mirror = new Map([[8, 1], [9, 4], [10, 2], [12, 3], [15, 4], [16, 5], [17, 6], [19, 7], [28, 9], [30, 10], [33, 8]]);
for (const id of changed) {
  append(id, 10,
    `${stamp}: revised current contract and acceptance wording. This amendment is approved as specification only; it does not establish future loop, verifier, historical-version or clause-coverage implementation or acceptance.`);
  const row = planById.get(id);
  if (row === undefined) throw new Error(`No Implementation Plan mirror for ${id}`);
  for (const [target, origin] of mirror) write(plan, ip, row, target, bb[byId.get(id)][origin - 1] ?? null);
  const old = ip[row][31];
  write(plan, ip, row, 32, `${old ? old + '\n\n' : ''}${stamp}: scope-matched answers/questions, kind-specific receipts, conclusion verification, dated provisions, all-attempt measurement and explicit slice coverage as applicable to this row.`);
}
const gap = (id, value) => write(plan, ip, planById.get(id), 44, value);
gap('LB-43',
  'Current row ownership is enumerated by requirement_owners.py, including packet-scoped bare-item criteria. Invalid/declared rows do not claim delivery coverage. The explicit clause-to-criterion/evidence map, dependency-closure checker and approved per-slice records under AC7 are not implemented. Run the row report for current population counts; it is not full slice readiness or acceptance.');
gap('LB-156',
  'Exact Act identity is improved. Historical section revision/effective-interval selection is not established by whole-Act validity dates; LB-156-AC4 and BK-98-AC2 historical-version proof remain pending.');
gap('LB-141',
  'The independent loop verifier and qualified evidence-package measurement remain pending, including final-inference review, classification bypass, partial-support and unavailable-verifier controls. No model evaluation or professional acceptance claimed.');
gap('LB-138',
  'Explicit clause/evidence maps and prerequisite closure remain pending under LB-43-AC7/LB-138-AC4. Absolute release measurements and approved live comparisons remain required; the row-ownership CLI is not this sign-off.');
}

const changedIds = [...changed].sort();
await fs.writeFile(path.join(output, 'edits.json'), JSON.stringify({ source_hash: digest(sourceBytes), ids: changedIds, edits }, null, 2));
const saved = path.join(output, 'Nyaymalaw_Implementation_Plan.xlsx');
if (book) {
  const check = await book.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 30 }, maxChars: 1500 });
  await fs.writeFile(path.join(output, 'formula-scan.json'), check.ndjson);
  const image = await book.render({ sheetName: 'Before Build', range: 'C190:E190', scale: 1 });
  await fs.writeFile(path.join(output, 'after.png'), new Uint8Array(await image.arrayBuffer()));
  await (await artifact.SpreadsheetFile.exportXlsx(book)).save(saved);
}
// Independent saved-byte verification. On fallback this also applies only the named edits.
const verification = execFileSync(python, ['-B', '-c', `
import copy,hashlib,json,re,sys
from openpyxl import load_workbook
from openpyxl.xml.functions import tostring
source,target,edits_file,mode=sys.argv[1:]
spec=json.load(open(edits_file,encoding='utf-8'))
assert hashlib.sha256(open(source,'rb').read()).hexdigest()==spec['source_hash'],'source changed'
b=load_workbook(source)
def features(s):
 return {
 'merged':tuple(map(str,s.merged_cells.ranges)), 'freeze':s.freeze_panes,
 'state':s.sheet_state,'views':tostring(s.views.to_tree()),
 'validations':tostring(s.data_validations.to_tree()),
 'conditional':tuple((str(k),tuple(tostring(r.to_tree()) for r in rules)) for k,rules in s.conditional_formatting._cf_rules.items()),
 'protection':tostring(s.protection.to_tree()),'margins':tostring(s.page_margins.to_tree()),
 'print_options':tostring(s.print_options.to_tree()),
 'rows':{k:dict(v) for k,v in s.row_dimensions.items()},
 'cols':{k:dict(v) for k,v in s.column_dimensions.items()},
 'tables':tuple(tostring(t.to_tree()) for t in s.tables.values()),
 'dimensions':(s.max_row,s.max_column),
 'print_area':str(s.print_area),'print_titles':(s.print_title_rows,s.print_title_cols)}
native={s.title:features(s) for s in b}
old={(s.title,c.coordinate):(c.value,copy.copy(c._style),copy.copy(c.hyperlink),copy.copy(c.comment)) for s in b for row in s for c in row}
allowed={(x['sheet'],x['address']) for x in spec['edits']}
assert all(not (x['sheet']=='Before Build' and x['address'].startswith('A')) for x in spec['edits'])
if mode=='fallback':
 for e in spec['edits']:
  c=b[e['sheet']][e['address']]
  assert c.value==e['before'],(e['sheet'],e['address'],'precondition')
  c.value=e['after']
 b.save(target)
v=load_workbook(target)
assert v.sheetnames==b.sheetnames,'tabs changed'
for s in v:
 assert features(s)==native[s.title],(s.title,'native feature changed')
 for row in s:
  for c in row:
   prior=old[(s.title,c.coordinate)]
   assert (c._style,c.hyperlink,c.comment)==prior[1:],(s.title,c.coordinate,'style/annotation changed')
   if (s.title,c.coordinate) not in allowed: assert c.value==prior[0],(s.title,c.coordinate,'unrelated value changed')
final={}
for e in spec['edits']: final[(e['sheet'],e['address'])]=e['after']
for (sheet,coord),value in final.items(): assert v[sheet][coord].value==value,(sheet,coord,'saved value')
errors=[(s.title,c.coordinate,c.value) for s in v for row in s for c in row if c.data_type=='e']
assert not errors,errors
ids=lambda s:[str(row[0].value or '').splitlines()[0] for row in s if re.match(r'^(LB-[0-9]+|OM-[PIQ][0-9]+)',str(row[0].value or ''))]
assert ids(v['Before Build'])==ids(b['Before Build']),'requirement ordering changed'
count=sum(len(set(re.findall(str(row[0].value)+'-AC[0-9]+',str(row[32].value or '')))) for row in v['Implementation Plan'] if re.fullmatch(r'LB-[0-9]+|OM-[PIQ][0-9]+',str(row[0].value or '')))
print(json.dumps({'authoring_engine':mode,'cells_changed':len(final),'requirements':len(ids(v['Before Build'])),'acceptance_clauses':count,'unrelated_cells_changed':0,'native_features_changed':0,'cell_errors':errors,'output_hash':hashlib.sha256(open(target,'rb').read()).hexdigest()}))
b.close();v.close()
`, source, saved, path.join(output, 'edits.json'), book ? 'artifact-tool' : 'fallback'], { encoding: 'utf8', maxBuffer: 4096 });
await fs.writeFile(path.join(output, 'verification.json'), verification);
if (!book) fallbackPreview(saved, path.join(output, 'after.png'));
if (digest(await fs.readFile(source)) !== digest(sourceBytes)) throw new Error('Source changed during authoring; do not publish');
console.log(JSON.stringify({ candidate: saved, ids: changedIds, cells_changed: edits.length, source_hash: digest(sourceBytes), verification: JSON.parse(verification) }));
