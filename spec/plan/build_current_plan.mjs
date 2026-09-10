/** Build the current end-to-end plan from registered claims and bound evidence.
 *
 * node build_current_plan.mjs --python <project-python> --runtime-path <scratch-dir>
 *   [--output <xlsx>] [--preview-dir <dir>] [--snapshot-time <ISO UTC>]
 *
 * runtime-path contains a node_modules junction to the bundled artifact runtime.
 * No workbook cell is an input to delivery status. This never alters the historical
 * slice workbook or the user's original end-to-end workbook.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const python = option('--python', process.env.NM_PLAN_PYTHON);
const runtime = option('--runtime-path', process.env.NM_PLAN_ARTIFACT_RUNTIME);
if (!python || !runtime) throw new Error('Provide --python and --runtime-path. See spec/plan/README.md.');
const requireArtifact = createRequire(path.join(path.resolve(runtime), 'runtime-entry.cjs'));
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(requireArtifact.resolve('@oai/artifact-tool')).href);
const output = path.resolve(option('--output', path.join(root, 'docs/Nyaymalaw_End_to_End_Project_Plan.xlsx')));
const previews = option('--preview-dir', null);
const snapshotTime = new Date(option('--snapshot-time', new Date().toISOString()));
const data = JSON.parse(execFileSync(python, [path.join(root, 'spec/plan/export_current_plan.py')], {
  cwd: root, encoding: 'utf8', maxBuffer: 30 * 1024 * 1024,
}));
const context = JSON.parse(await fs.readFile(path.join(root, 'spec/plan/view_content.json'), 'utf8'));
const items = new Map(data.items.map(r => [r.id, r]));
const features = new Map(data.features.map(r => [r.id, r]));
const steps = new Map(data.steps.map(r => [r.id, r]));
const waves = new Map(data.plan.item_waves.map(r => [r.id, r.wave]));
const professional = data.professional;
const blueprint = data._blueprint;
if (!blueprint?.packets?.packets?.length) throw new Error('Execution contracts are absent.');
const contractFields = ['actor', 'entry_conditions', 'user_action', 'expected_visible_result',
  'expected_domain_effect', 'failure_behaviour', 'recovery_behaviour', 'exit_conditions'];
const text = value => Array.isArray(value) ? value.map(text).join('\n') : value && typeof value === 'object'
  ? Object.entries(value).map(([k, v]) => `${k}: ${text(v)}`).join('\n') : value == null ? '' : String(value);
const list = value => (value || []).join(', ');
const nextAction = row => row.delivery_status === 'deferred'
  ? `${row.next_action ? row.next_action + ' ' : ''}Review on ${row.review_on} (India date). Live status shows due/overdue; recorded reassessment is required before reactivation.`
  : row.next_action || '';
const unique = values => [...new Set(values)];
const contractComplete = row => contractFields.every(k => row[k] && (typeof row[k] === 'string' || row[k].length));
const phaseNames = {A:'Arrive', B:'Open a matter', C:'Take the Brief', D:'Work the File', E:'Advise',
  F:'Act', G:'Carry', H:'Close', I:'Leave'};
const source = name => `docs/backlog/${name}`;
const checkUnique = (label, rows) => {
  if (!rows.length) throw new Error(`${label} is empty; a zero-population reconciliation is invalid.`);
  if (new Set(rows.map(r => r.id)).size !== rows.length) throw new Error(`${label} has duplicate IDs.`);
};
for (const [label, rows] of Object.entries({items:data.items, features:data.features, steps:data.steps,
  waves:data.plan.item_waves, ...Object.fromEntries(['advocate_standards','workflow_states','advice_maturity','roles','gap_closures'].map(k=>[k,professional[k]]))})) checkUnique(label, rows);
if (!data.plan.wave_contracts?.length || !data.plan.release_profiles?.length) throw new Error('Wave contracts and release profiles must be registered before export.');
for (const rows of [context.scenarios, context.risks, context.review_gates]) for (const row of rows)
  for (const id of row.work_items) if (!items.has(id)) throw new Error(`${row.id} refers to missing work ${id}`);
for (const [key, reference] of [['standards_context','advocate_standards'],['workflow_context','workflow_states'],['roles_context','roles'],['gaps_context','gap_closures']]) {
  const ids = new Set(professional[reference].map(r=>r.id));
  for (const id of Object.keys(context[key])) if (!ids.has(id)) throw new Error(`Supplementary context has an unregistered ${id}`);
}

const wb = Workbook.create();
const tables = new Map();
const lastColumn = n => { let s=''; for (;n;n=Math.floor((n-1)/26)) s=String.fromCharCode(65+(n-1)%26)+s; return s; };
function addTable(name, title, note, headers, rows, widths, freeze = true) {
  const sheet = wb.worksheets.add(name);
  sheet.showGridLines = false;
  const last = lastColumn(headers.length), end = rows.length + 3;
  const used = sheet.getRange(`A1:${last}${end}`);
  used.format.font = {name:'Arial', size:10, color:'#20272B'};
  used.format.wrapText = true;
  used.format.verticalAlignment = 'top';
  sheet.getRange('A1').values = [[title]];
  sheet.getRange('A1').format.font = {name:'Arial',size:15,bold:true,color:'#0F4C5C'};
  sheet.mergeCells(`A1:${last}1`);
  sheet.getRange(`A1:${last}1`).format.rowHeight = 29;
  sheet.getRange(`A1:${last}1`).format.borders = {bottom:{style:'thin',color:'#0F4C5C'}};
  sheet.getRange('A2').values = [[note]];
  sheet.mergeCells(`A2:${last}2`);
  sheet.getRange(`A2:${last}2`).format.font = {name:'Arial',size:10,italic:true,color:'#58666B'};
  sheet.getRange(`A2:${last}2`).format.rowHeight = 43;
  sheet.getRange(`A3:${last}3`).values = [headers];
  if (rows.length) sheet.getRange(`A4:${last}${end}`).values = rows.map(row => row.map(v => typeof v === 'number' || typeof v === 'boolean' || v instanceof Date ? v : text(v)));
  sheet.getRange(`A3:${last}3`).format = {fill:'#0F4C5C',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,verticalAlignment:'center',horizontalAlignment:'left'};
  sheet.getRange(`A3:${last}3`).format.rowHeight = 40;
  sheet.getRange(`A3:${last}3`).format.borders = {insideVertical:{style:'thin',color:'#FFFFFF'}};
  widths.forEach((width,c) => sheet.getRange(`${lastColumn(c+1)}1:${lastColumn(c+1)}${end}`).format.columnWidth = width);
  rows.forEach((row, idx) => {
    // The spreadsheet engine recognises ISO instants as dates. Preserve their
    // readable UTC representation instead of exposing a General-format serial.
    row.forEach((value,c) => {
      if(typeof value==='string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$/.test(value))
        sheet.getRange(`${lastColumn(c+1)}${idx+4}`).setNumberFormat('yyyy-mm-dd"T"hh:mm:ss"Z"');
    });
    const estimatedLines = Math.max(...row.map((value,c) => text(value).split('\n').reduce((n,line) => n + Math.max(1, Math.ceil(line.length/Math.max(5, widths[c]-3))),0)));
    if(estimatedLines*15+10>400) throw new Error(`${name} row ${idx+4} would clip; widen or divide that reader view.`);
    sheet.getRange(`A${idx+4}:${last}${idx+4}`).format.rowHeight = Math.max(27,estimatedLines*15+10);
    if (idx%2) sheet.getRange(`A${idx+4}:${last}${idx+4}`).format.fill='#F2F5F6';
  });
  if (freeze) { sheet.freezePanes.freezeRows(3); sheet.freezePanes.freezeColumns(1); }
  const table = sheet.tables.add(`A3:${last}${end}`,true,`Plan_${name.replace(/[^A-Za-z0-9]/g,'')}`);
  table.showFilterButton = true;
  tables.set(name,{sheet,headers,rows,end,last,widths});
  return sheet;
}

const readme = [
  ['Purpose','Build the intended advocate journey and distinguish it from what is implemented, currently proved and authorised for release.'],
  ['How to read','Start with Overview, Modules and Execution Packets. Read that packet in Packet Guide and Acceptance, then the affected Journey Steps and professional standards. Use only the applicable Start / Build / Test / Sign-off guide.'],
  ['Execution order','Packet prerequisites consume scoped outputs. Completed-item prerequisites require full sign-off. Modules are capability groups, not whole-module completion barriers. P01 and P02 are independent local synthetic starting points.'],
  ['Approval boundary',`${blueprint.decisions.choices.filter(r=>r.approval===null).length} choices have no recorded confidential-scope approval. ${blueprint.evaluations.release_portfolios.length} real evaluation portfolios and ${blueprint.evaluations.manual_review_protocols.length} independent review protocols remain subject to actual execution and sign-off. Run blueprint readiness for the current named blockers; this workbook cannot approve a release.`],
  ['Intended behaviour','PRD and journey/professional contracts state the target. A populated contract is a specification, not an implementation or a passing browser test.'],
  ['Implemented','The implementation column is copied exactly from status.yaml. Complete means the implementation claim exists; it does not establish conformance or permission to ship.'],
  ['Currently proved','Effective evidence and derived done come from the existing backlog functions bound to the current execution artifact. Missing, failing or stale proof remains unproved. Legacy closures are identified separately.'],
  ['Execution evidence at snapshot',(data._execution_problems||[]).length?data._execution_problems:'No execution-artifact validation problem reported by the existing binder. This does not replace counsel, browser or deployment evidence.'],
  ['Released','This workbook records no deployment authorisation. Item readiness is not a release decision. Use a separately recorded release-profile decision with its exact population, environment, owners and current evidence.'],
  ['Wave and release controls','Wave contracts and release profiles are intended manual decisions until BK-80 implements their mechanical gate. A populated profile or green registry lint cannot approve a release.'],
  ['Core workflow','Take the Brief is an interactive loop: hear or receive material, retrieve what is permitted, assess, ask the next useful question, preserve the response, and reassess. Work the File and Advise return to the affected earlier state when facts, law, scope or readiness change.'],
  ['Senior-advocate quality','Test independent judgment, adverse-case candour, proportionality, source discipline, scope and role authority. Accurate calculation does not establish the legal premise. Professional review is independent of code-test success.'],
  ['Media scope','The intended intake includes voice, audio/video, images and documents. Publish supported formats, limits, language and processing capability; quarantine or refuse unsupported, unsafe or unconsented material without pretending it was read.'],
  ['Before a change','docs/playbooks/START_A_CHANGE.md — register the claim, affected journey, acceptance, evidence scope, risk and authority.'],
  ['While building','docs/playbooks/BUILD_A_CHANGE.md — build the registered outcome, preserve boundaries and maintain recovery and correction behaviour.'],
  ['While testing','docs/playbooks/TEST_A_CHANGE.md — verify the promised outcome, negative controls and applicable integration, browser and legal evidence.'],
  ['At sign-off','docs/playbooks/SIGN_OFF_A_CHANGE.md — reconcile claims, evidence, residual risks and release authority. Do not turn a test-run approval into risk acceptance.'],
  ['Maintenance','Change the authoritative source, then regenerate. Do not edit workbook status cells. Source hashes in Sources identify this snapshot and prevent concurrent-source changes during export.'],
  ['Source hash convention',data._snapshot.hash_semantics],
  ['Prior plans','The original vertical-slice workbook and the 9 September end-to-end workbook remain historical references. This is the current generated view; it does not replace their evidence record.'],
  ['Scenario and risk catalogues','JS-, R- and G-labels organise preserved design examples in spec/plan/view_content.json. They are not extra work items or executed proofs. Each points to registered delivery work; execution coverage must be recorded there.'],
  ['Journey principle',data.plan.journey_model.principle],
  ['Normal working loop',data.plan.journey_model.normal_loop],
  ['Return triggers',data.plan.journey_model.return_triggers],
  ['Return behaviour',data.plan.journey_model.return_behavior],
  ['Stop and resume',data.plan.journey_model.stop_and_resume],
  ['Maturity rule',data.plan.journey_model.maturity],
  ['Snapshot',snapshotTime],
  ['Git identity',data._snapshot.git_head],
  ['Execution fingerprint',data._snapshot.verification_fingerprint],
];
const read = addTable('Read Me','Nyaymalaw end-to-end project plan','Current derived view. No release is authorised by this workbook.',['Topic','Meaning'],readme,[28,128],false);
read.getRange(`B${readme.findIndex(r=>r[0]==='Snapshot')+4}`).setNumberFormat('yyyy-mm-dd hh:mm "UTC"');

const overviewRows = Object.entries(phaseNames).map(([phase,name])=>[
  phase,name,0,0,0,0,0,0,
  data.items.filter(i=>(i.phase===phase||i.affects_phases?.includes(phase))&&i.priority==='P0'&&!i._plan_view.done).length,
  'No phase conformance or release verdict is inferred from counts.',
]);
const overview = addTable('Overview','The full advocate journey','Counts describe implementation claims and written contracts. Neither is a current end-to-end proof.',['Phase','Journey','Features','Implemented complete','Partial','None','Steps','Full intended contracts','Unclosed P0 affecting phase','Proof / release meaning'],overviewRows,[9,25,12,18,12,12,12,22,21,58]);

addTable('Delivery Plan','Risk-ordered delivery waves','Each wave is an intended outcome. Existing item-wave assignments remain authoritative; manual exit conditions do not assert current gate implementation.',['Wave','Outcome','Scope','Entry conditions','Exit conditions','Release claim limit','Control','Assigned work'],data.plan.wave_contracts.map(r=>[
  r.id,`${r.name}\n${r.goal}`,r.scope,r.entry_conditions,r.exit_conditions,r.release_claim,r.control,
  list(data.plan.item_waves.filter(i=>i.wave===r.id).map(i=>i.id)),
]),[9,48,40,65,80,42,27,48]);

addTable('Journey Steps','Login-to-logout journey','Step order is the named user journey, not a one-way wizard. Use Step Contracts for the intended behaviour and return/recovery conditions.',['Seq','Phase','Step ID','Journey step','Basis','Features','Registered work','Intended contract','Visible result','Failure behaviour','Recovery behaviour','Proof meaning'],data.steps.map((r,i)=>[
  i+1,r.phase,r.id,r.name,r.basis,list(r.features),list(r.items),contractComplete(r)?'Full written contract':'Contract incomplete',r.expected_visible_result,r.failure_behaviour,r.recovery_behaviour,
  'Written contract only. Verify the linked acceptance and current served journey; no step-level pass is inferred.',
]),[7,8,18,37,24,20,34,23,67,65,62,42]);
const aspects={actor:'Actor',entry_conditions:'Entry conditions',user_action:'User action',expected_visible_result:'Visible result',expected_domain_effect:'Domain effect',failure_behaviour:'Failure / refusal',recovery_behaviour:'Recovery / return',exit_conditions:'Exit conditions',notes:'Context'};
addTable('Step Contracts','Intended journey contracts','Each clause is target behaviour, not evidence that the product implements it. The same step may recur after new facts, changed law, corrections or a resumed matter.',['Step ID','Phase','Step','Aspect','Intended contract','Registered work'],data.steps.flatMap(r=>Object.entries(aspects).filter(([k])=>r[k]).map(([k,label])=>[r.id,r.phase,r.name,label,text(r[k]),list(r.items)])),[18,8,36,25,120,38]);

addTable('Features','Registered product features','Implementation and disposition are copied, not reinterpreted. Required assurance lives in the linked acceptance and applicable journey and release profile.',['Feature','Phase','Title','Build slice','Implementation','Disposition','Delivery items','Journey steps','Delivery waves','Proof meaning','Source'],data.features.map(r=>{
  const at=data.steps.filter(s=>s.features.includes(r.id));
  const linked=unique([...(r.delivery_items||[]),...at.flatMap(s=>s.items||[])]);
  return [r.id,r.phase,r.title,r.slice,r.implementation,r.disposition,list(r.delivery_items),list(at.map(s=>s.id)),list(unique(linked.map(id=>waves.get(id)).filter(Boolean)).sort()),'Implementation is not current feature conformance. Inspect linked acceptance and release scope.',source('status.yaml')];
}),[11,8,46,14,18,18,34,48,24,65,34]);

addTable('Work Items','Registered delivery work','Authored workflow, implementation and verification are retained separately from effective execution-bound evidence. Derived done includes declared legacy exceptions; no row authorises a deployment.',['ID','Title','Phase / affects','Kind','Priority','Delivery status','Implementation','Authored verification','Wave','Hard dependencies','Sequenced after','Blocker / reason','Next action','Acceptance count','Effective evidence','Derived completion','Item readiness only','Record'],data.items.map(r=>[
  r.id,r.title,r.phase||list(r.affects_phases),r.kind,r.priority,r.delivery_status,r.implementation,r.verification,waves.get(r.id)||'Unscheduled',list(r.depends_on),list(r.sequenced_after),r.blocked_by||r.reason||'',nextAction(r),r.acceptance?.length||0,r._plan_view.effective_evidence,r._plan_view.done?(r.legacy?'Legacy closure; prose exception':'Done from bound evidence'):'Not done',r._plan_view.item_readiness,r.record,
]),[12,55,20,15,11,19,18,22,14,30,30,52,65,15,22,32,24,58]);

addTable('Traceability','Journey-to-evidence traceability','One row per linked step, feature, work item and acceptance criterion. A missing criterion remains explicitly unproved. A step with several features does not imply that every linked item implements every feature.',['Phase','Step ID','Journey step','Features in step','Work item','Item implementation','Acceptance','Requirement','Required evidence','Effective result','Wave','Record'],data.steps.flatMap(s=>(s.items||[]).flatMap(id=>{
  const it=items.get(id); if(!it) throw new Error(`Unregistered ${id} on ${s.id}`);
  const acc=it.acceptance?.length?it.acceptance:[null];
  return acc.map(a=>[s.phase,s.id,s.name,list(s.features),id,it.implementation,a?.id||'No atomic criterion',a?.requirement||'No atomic requirement registered',list(a?.required_evidence),a?it._plan_view.criteria[a.id]:'NOT_PROVEN',waves.get(id)||'Unscheduled',it.record]);
})),[8,18,38,25,12,20,24,95,45,20,14,50]);

addTable('Build Assurance','Registered build-guide rules','Enforcement is the recorded mechanism, qualified by its coverage and remaining gap. A named check or preserved phrase is not proof of the whole principle.',['Rule','Stage','Kind','Requirement','Enforcement','Named check / review','Coverage scope','Remaining gap / reason','Stage guide'],data.build_rules.rules.map(r=>[
  r.id,r.stage,r.kind,r.statement,r.enforcement,r.check||r.review||'',r.coverage_scope||'',r.remaining_gap||r.why_not||'',`docs/playbooks/${r.card}`,
]),[13,13,17,85,19,60,68,68,55]);
addTable('Release Gates','Cumulative review decisions','Preserved design review sequence. These G-labels are catalogue keys, not executable gate verdicts. Release Profiles determines the applicable scope; registered work owns enforcement.',['Gate','Decision','When','Inputs','Required decision rule','Evidence to record','Owner role','Failure effect','Registered work'],context.review_gates.map(r=>[r.id,r.decision,r.when,r.inputs,r.rule,r.evidence,r.owner,r.failure,list(r.work_items)]),[9,26,33,55,80,42,28,47,34]);
const profileRows=data.plan.release_profiles.flatMap(r=>[
  [r.id,'Profile name',r.name],
  [r.id,'Scope',r.scope],
  [r.id,'Entry conditions',r.entry_conditions],
  [r.id,'Required work',(r.required_items||[]).length?list(r.required_items):'No unconditional work items are listed. Apply the conditional scope requirements below.'],
  [r.id,'Conditional work',(r.conditional_items||[]).length?r.conditional_items.map(c=>`${c.when}: ${list(c.items)}`):'No additional conditional items are listed.'],
  [r.id,'Required evidence',r.required_evidence],
  [r.id,'Excluded claims',r.excluded_claims],
  [r.id,'Approval',r.approval],
  [r.id,'Control',r.control],
]);
const profiles=addTable('Release Profiles','Permitted release scopes','Intended manual profiles until BK-80 enforces membership and evidence. This snapshot does not approve a release or waive MFA, privacy or legal-quality protections.',['Profile','Aspect','Requirement'],profileRows,[23,25,142]);
profiles.getRange(`A4:C${profileRows.length+3}`).format.font={name:'Arial',size:11,color:'#20272B'};
profiles.getRange('A3:C3').format.font={name:'Arial',size:11,bold:true,color:'#FFFFFF'};
profileRows.forEach((row,i)=>{
  const lines=Math.max(...row.map((value,c)=>text(value).split('\n').reduce((n,line)=>n+Math.max(1,Math.ceil(line.length/([23,25,142][c]-4))),0)));
  profiles.getRange(`A${i+4}:C${i+4}`).format.rowHeight=Math.max(30,lines*17+12);
});
addTable('Journey Scenarios','Risk-selected journey scenarios','Specification catalogue, not an execution report. Every scenario links to registered work; a passing unit or scripted test does not supply browser or legal-quality proof.',['Scenario','User / matter','Phases','Journey','Required outcome','Failure injection','Suggested cadence','Registered work','Evidence meaning'],context.scenarios.map(r=>[r.id,r.user,r.phases,r.journey,r.outcome,r.failure_injection,r.cadence,list(r.work_items),'No execution verdict inferred; bind actual scenarios and evidence to registered acceptance.']),[13,34,14,75,80,58,28,42,55]);
addTable('Risks','Programme risk catalogue','Triggers and mitigations describe what to watch. They do not assert a fresh risk assessment or certify controls. Registered work carries actual delivery status.',['Risk','Failure risk','Initial likelihood','Impact','Observable trigger','Mitigation','Owner role','Registered work'],context.risks.map(r=>[r.id,r.risk,r.likelihood,r.impact,r.trigger,r.mitigation,r.owner,list(r.work_items)]),[12,68,19,17,68,74,30,45]);

addTable('Advocate Standard','Expert advocate standard','Registered professional requirements. Linked-work state is derived from the status registry and can include legacy closures; it is not independent counsel certification.',['ID','Quality','Observable behaviour','Trust-destroying failure','Applies to','Product behaviour context','Suggested proof','Registered work','Features / steps','Linked-work state'],professional.advocate_standards.map(r=>{
  const c=context.standards_context[r.id]||{};
  return [r.id,r.quality,r.observable,r.failure,c.applies_to,c.product_behaviour,c.suggested_proof,list(r.work_items),`${list(r.features)}\n${list(r.steps)}`,r._linked_work_state];
}),[13,32,74,65,27,80,68,40,65,24]);
addTable('Expert Workflow','The expert working loop','Registered states and required outputs; supplementary interaction and return guidance is preserved in the tracked plan view source. Task readiness is specific to the requested decision, not exhaustive questioning.',['ID','Working state','Expert purpose','Inputs','NM behaviour','Required output','Return / stop rule','Features / steps','Registered work','Linked-work state'],professional.workflow_states.map(r=>{
  const c=context.workflow_context[r.id]||{};
  return [r.id,r.state,r.purpose,c.inputs,c.behaviour,r.required_output,c.return_rule,`${list(r.features)}\n${list(r.steps)}`,list(r.work_items),r._linked_work_state];
}),[13,35,72,70,83,67,75,58,42,24]);
addTable('Advice Maturity','Advice maturity and reliance limits','Advice levels describe permitted reliance on an output. They are not a score or a guarantee of outcome; considered advice does not confer authority to act.',['ID','Level','When permitted','Must contain','Must not imply','Features / steps','Registered work','Linked-work state'],professional.advice_maturity.map(r=>[r.id,r.level,r.when_permitted,r.must_contain,r.must_not_imply,`${list(r.features)}\n${list(r.steps)}`,list(r.work_items),r._linked_work_state]),[13,35,79,65,72,58,42,24]);
addTable('Roles & Authority','Roles and authority','Role labels in the intended product do not establish current professional-law compliance. Verify the applicable jurisdiction, court rules, engagement and instruction chain before release.',['ID','Role','Interaction context','May do','Required approval context','Controlled / restricted','System-control context','Reference context','Registered work','Linked-work state'],professional.roles.map(r=>{
  const c=context.roles_context[r.id]||{};
  return [r.id,r.role,c.interaction,r.may,c.approval,r.controlled,c.controls,c.reference,list(r.work_items),r._linked_work_state];
}),[15,35,74,73,64,71,68,65,42,24]);
addTable('Gap Closure','Professional gap closure','The professional registry owns each gap, stage and work link. Foundation, feature-complete and release horizons remain distinct.',['ID','Gap','Why it matters','Required plan change','Minimum acceptance','Registered stage links','Foundation','Feature complete','Release gate','Standards / workflow / advice','Linked-work state'],professional.gap_closures.map(r=>[
  r.id,r.gap,context.gaps_context[r.id]?.why||'',r.plan_change,r.minimum_acceptance,list(r.links.map(l=>`${l.item} (${l.stage})`)),r.foundation_wave,r.feature_complete_wave,r.release_gate_wave,`${list(r.standards)}\n${list(r.workflow)}\n${list(r.advice)}`,r._linked_work_state,
]),[13,55,70,75,83,48,14,19,16,59,24]);

addTable('Modules','Capability homes','Navigation only. Use packet prerequisites for build order and registered item dependencies for completion.',['Module','Capability','Context modules','Work items','Features','Steps','Chapter'],blueprint.modules.map(r=>[
  r.id,r.title,list(r.requires),list(r.items),list(r.features),list(r.steps),`docs/blueprint/${r.guide}`,
]),[12,45,24,62,38,68,50]);
const packetRows=blueprint.packets.packets;
addTable('Execution Packets','The bounded work queue','Numeric labels are not a mandatory total order. A final criterion owner still needs its actual required proof; no packet is declared done here.',['Packet','Module','Outcome','Kind','Scoped predecessor outputs','Completed items required','Criteria','Final criteria','Required choices','Command contracts'],packetRows.map(r=>[
  r.id,r.module,r.title,r.kind,list(r.prerequisites),list(r.requires_completed_items),r.criteria.length,r.final_criteria.length,list(r.decisions),list(r.commands),
]),[12,12,63,20,36,70,13,16,38,68]);
const packetGuideRows=packetRows.flatMap(r=>['inputs','outputs','steps','expected','rollback'].flatMap(aspect=>
  (Array.isArray(r[aspect])?r[aspect]:[r[aspect]]).map((instruction,i)=>[r.id,r.title,aspect,i+1,instruction])));
addTable('Packet Guide','Use only the current packet','Each row is one input, output, build instruction, expected result or rollback step. Acceptance supplies every criterion-specific failure control.',['Packet','Outcome','Aspect','Order','Instruction'],packetGuideRows,[12,60,20,10,140]);
const acceptanceRows=data.items.flatMap(item=>(item.acceptance||[]).map(ac=>{
  const contributors=packetRows.filter(p=>p.criteria.includes(ac.id));
  return [ac.id,item.id,ac.requirement,list(ac.required_evidence),text(ac.negative_control?.mutation),text(ac.negative_control?.expected_failure),
    list(contributors.map(p=>p.id)),list(contributors.filter(p=>p.final_criteria.includes(ac.id)).map(p=>p.id))||'Current planning delivery',
    text(item._plan_view.criteria[ac.id]),'Declared tests and criteria are not execution results.'];
}));
addTable('Acceptance','Every registered acceptance criterion','Exactly one final packet owns each in-scope criterion. BK-87, BK-89 and BK-90 are planning deliveries, explicitly outside future application packets.',['Criterion','Work item','Required behaviour','Required evidence methods','Planted mutation','Expected refusal / failure','Contributing packets','Final packet','Effective proof','Limit'],acceptanceRows,[20,14,100,42,88,88,25,28,30,58]);
addTable('Decisions','Recommended defaults and approval boundaries','Manual adoption records: docs/blueprint/approvals.json. Their schema and verification contract are in APPROVALS.md. Recorded is not verified; BK-80/P03 owns automated authority resolution.',['Choice','Decision','Recommendation','Reason','Fallback','Accountable approver','Approval required for','Current approval'],blueprint.decisions.choices.map(r=>[
  r.id,r.title,r.recommendation,r.rationale,r.fallback,r.approver,list(r.approval_required_for),blueprint.adoption_labels[r.id],
]),[18,40,100,68,90,42,44,50]);
addTable('Command Contracts','Versioned application command contracts','Target contracts, not routes claimed implemented. Complete JSON schemas and positive/negative witnesses live in docs/blueprint/contracts/commands.json.',['Command','Method','Target path','Owner criteria','Current route / migration','Request schema','Response schema','Retry / concurrency'],blueprint.commands['x-commands'].map(r=>[
  r.id,r.method,r.path,list(r.owner_ac),text(r.current_route),text(r.request_schema),text(r.response_schema),text(r.retry),
]),[32,14,60,45,100,50,50,125]);
addTable('Evaluation Specs','Concrete synthetic baseline scenarios','NOT RUN: these are test specifications, not legal gold labels or current browser evidence. Use Evaluation Details for fixtures and assertions. Every packet also owes its exact registered criterion proofs.',['Scenario','Module','Purpose','Owner criteria','Required paths','Method','Planted negative','Execution'],blueprint.evaluations.synthetic_cases.map(r=>[
  r.id,r.module,r.title,list(r.owner_criteria),list(r.required_paths),r.method,text(r.planted_negative),'NOT RUN — specification only',
]),[18,12,55,60,32,65,125,34]);
const evaluationDetailRows=blueprint.evaluations.synthetic_cases.flatMap(r=>[
  ...Object.entries(r.inputs).map(([key,value])=>[r.id,'Input',key,text(value)]),
  ...r.sequence.map((value,i)=>[r.id,'Sequence',i+1,value]),
  ...r.expected.map(value=>[r.id,'Expected observation',value.path,`${value.operator}: ${text(value.value)}`]),
  ...r.live_observation.map((value,i)=>[r.id,'Live observation',i+1,value]),
]);
for (const [key,label] of [['observation_contract','Observation contract'],['media_contract','Media policy']]) {
  for (const [field,value] of Object.entries(blueprint.evaluations[key])) {
    evaluationDetailRows.push(['Shared contract',label,field,text(value)]);
  }
}
function autonomyLeaves(value,path=[]) {
  if(value!==null && typeof value==='object' && !Array.isArray(value)) {
    return Object.entries(value).flatMap(([key,child])=>autonomyLeaves(child,[...path,key]));
  }
  if(Array.isArray(value) && value.some(child=>child!==null && typeof child==='object')) {
    return value.flatMap((child,index)=>autonomyLeaves(child,[...path,child.id??String(index+1)]));
  }
  return [['Autonomy contract',path[0],path.slice(1).join('.')||path[0],text(value)]];
}
evaluationDetailRows.push(...autonomyLeaves(blueprint.autonomy));
addTable('Evaluation Details','Fixtures and exact observable checks','Synthetic specifications and bounded-autonomy contract. Expected values are test inputs, never actual results; autonomy is design-only, NOT RUN.',['Scenario','Aspect','Field / order','Specification'],evaluationDetailRows,[18,28,62,155]);

const sourceRows = Object.entries(data._snapshot.source_sha256).map(([name,hash])=>[
  name,name==='docs/backlog/evidence/class_a.json'?'Captured execution artifact':'Snapshot source',hash,
  name==='docs/backlog/evidence/class_a.json'?'Historical evidence captured at export, not a current test input. Promotion cannot certify or invalidate its own source. Refresh the view to show newly published proof.':'Authoritative content or rendering input; status authority remains status.yaml.',
]);
sourceRows.push(['Git identity','Snapshot provenance',data._snapshot.git_head,'Source hashes, not the commit label alone, identify this view.']);
sourceRows.push(['Execution fingerprint','Effective evidence binding',data._snapshot.verification_fingerprint,'Matches the current check system; execution integrity limitations remain registered under BK-80.']);
for(const r of context.external_references) sourceRows.push([r.source,r.authority,r.url,`Preserved historical reference: ${r.scope}. Current governing authority must be rechecked for the release jurisdiction.`]);
sourceRows.push(['Nyaymalaw_Project_Plan.xlsx','Historical slice plan','Preserved unchanged','Not the current wave/status owner.']);
sourceRows.push(['9 September 2026 end-to-end workbook','Historical plan source','Preserved unchanged','Supplementary design context is now tracked in spec/plan/view_content.json; no historical verification counts carry forward.']);
addTable('Sources','Sources and snapshot provenance','Source paths are included intentionally for build-plan traceability. External links are preserved references, not a new legal-research certification.',['Source','Role','Fingerprint / URL','Use and limits'],sourceRows,[61,29,104,93]);

const reconGroups = [
  ['Items',data.items,'Work Items','A'],['Features',data.features,'Features','A'],['Steps',data.steps,'Journey Steps','C'],
  ['Advocate standards',professional.advocate_standards,'Advocate Standard','A'],['Workflow states',professional.workflow_states,'Expert Workflow','A'],
  ['Advice levels',professional.advice_maturity,'Advice Maturity','A'],['Roles',professional.roles,'Roles & Authority','A'],
  ['Gaps',professional.gap_closures,'Gap Closure','A'],['Wave contracts',data.plan.wave_contracts,'Delivery Plan','A'],
  ['Build rules',data.build_rules.rules,'Build Assurance','A'],
  ['Modules',blueprint.modules,'Modules','A'],
  ['Execution packets',packetRows,'Execution Packets','A'],
  ['Acceptance criteria',acceptanceRows.map(r=>({id:r[0]})),'Acceptance','A'],
  ['Choices',blueprint.decisions.choices,'Decisions','A'],
  ['Command contracts',blueprint.commands['x-commands'],'Command Contracts','A'],
  ['Synthetic specifications',blueprint.evaluations.synthetic_cases,'Evaluation Specs','A'],
];
const reconRows=reconGroups.map(([label,rows,sheet,column])=>[label,rows.length,0,0,`'${sheet}'!${column}4:${column}${rows.length+3}`,'Exact IDs checked in generator; formula counts exported populated rows.']);
reconRows.push(['Release profiles',data.plan.release_profiles.length,0,0,`'Release Profiles'!B4:B${profileRows.length+3}`,'One Scope aspect per profile; exact unique profile IDs and all aspect rows checked in generator.']);
reconRows.push(['Wave assignments',data.plan.item_waves.length,data.items.length,data.plan.item_waves.length-data.items.length,'plan.json item_waves','Exact item-ID sets checked, including explicitly unscheduled terminal work.']);
reconRows.push(['Full intended step contracts',data.steps.filter(contractComplete).length,data.steps.filter(contractComplete).length,0,'steps.yaml','Contract completeness only, never implementation or conformance.']);
reconRows.push(['Structural lint problems',0,data._snapshot.structural_lint_problems,data._snapshot.structural_lint_problems,'tools/backlog.py lint','Does not certify manual wave or release-profile gates.']);
const reconciliation=addTable('Reconciliation','Population and source reconciliation','A matching population proves export coverage, not feature quality. The generator also checks exact IDs and source hashes, including concurrent edits during export.',['Population','Source count','Workbook count','Difference','Compared source / range','Meaning'],reconRows,[31,16,19,16,57,95]);
for(let i=0;i<reconGroups.length;i++){
  const [,rows,sheet,column]=reconGroups[i],r=i+4;
  reconciliation.getRange(`C${r}`).formulas=[[`=COUNTA('${sheet}'!${column}4:${column}${rows.length+3})`]];
  reconciliation.getRange(`D${r}`).formulas=[[`=C${r}-B${r}`]];
}
const profileReconciliationRow=reconGroups.length+4;
reconciliation.getRange(`C${profileReconciliationRow}`).formulas=[[`=COUNTIF('Release Profiles'!B4:B${profileRows.length+3},"Scope")`]];
reconciliation.getRange(`D${profileReconciliationRow}`).formulas=[[`=C${profileReconciliationRow}-B${profileReconciliationRow}`]];
reconciliation.getRange(`B4:D${reconRows.length+3}`).setNumberFormat('#,##0');
reconciliation.getRange(`D4:D${reconRows.length+3}`).conditionalFormats.add('cellIs',{operator:'notEqual',formula:0,format:{fill:'#F3E3E1',font:{color:'#96382F'}}});
for(let i=0;i<overviewRows.length;i++){
  const r=i+4,fe=data.features.length+3,se=data.steps.length+3;
  overview.getRange(`C${r}:H${r}`).formulas=[[
    `=COUNTIF('Features'!$B$4:$B$${fe},A${r})`,
    `=COUNTIFS('Features'!$B$4:$B$${fe},A${r},'Features'!$E$4:$E$${fe},"complete")`,
    `=COUNTIFS('Features'!$B$4:$B$${fe},A${r},'Features'!$E$4:$E$${fe},"partial")`,
    `=COUNTIFS('Features'!$B$4:$B$${fe},A${r},'Features'!$E$4:$E$${fe},"none")`,
    `=COUNTIF('Journey Steps'!$B$4:$B$${se},A${r})`,
    `=COUNTIFS('Journey Steps'!$B$4:$B$${se},A${r},'Journey Steps'!$H$4:$H$${se},"Full written contract")`,
  ]];
}
overview.getRange(`C4:I${overviewRows.length+3}`).setNumberFormat('#,##0');
reconGroups.forEach(([,expected],i)=>{
  const actual=reconciliation.getRange(`C${i+4}:D${i+4}`).values[0];
  if(actual[0]!==expected.length||actual[1]!==0) throw new Error('Reconciliation formula result differs from source population.');
});
if(reconciliation.getRange(`C${profileReconciliationRow}`).values[0][0]!==data.plan.release_profiles.length) throw new Error('Release-profile formula population differs from source.');
Object.keys(phaseNames).forEach((phase,i)=>{
  const phaseFeatures=data.features.filter(f=>f.phase===phase),phaseSteps=data.steps.filter(s=>s.phase===phase);
  const expected=[phaseFeatures.length,...['complete','partial','none'].map(state=>phaseFeatures.filter(f=>f.implementation===state).length),phaseSteps.length,phaseSteps.filter(contractComplete).length];
  if(JSON.stringify(overview.getRange(`C${i+4}:H${i+4}`).values[0])!==JSON.stringify(expected)) throw new Error(`${phase}: overview formula result differs from source.`);
});

// Check actual written cells, not the input array that created them.
for(const [label,rows,name,column] of reconGroups){
  const got=tables.get(name).sheet.getRange(`${column}4:${column}${rows.length+3}`).values.map(r=>r[0]);
  const expected=rows.map(r=>r.id);
  if(JSON.stringify(got)!==JSON.stringify(expected)) throw new Error(`${label}: exact-ID reconciliation failed`);
}
const savedProfileRows=profiles.getRange(`A4:C${profileRows.length+3}`).values;
if(JSON.stringify(savedProfileRows)!==JSON.stringify(profileRows.map(row=>row.map(text)))) throw new Error('Release-profile aspect projection mismatch.');
if(JSON.stringify(unique(savedProfileRows.map(row=>row[0])))!==JSON.stringify(data.plan.release_profiles.map(row=>row.id))) throw new Error('Release-profile exact-ID reconciliation failed.');
const statusWritten=tables.get('Work Items').sheet.getRange(`A4:R${data.items.length+3}`).values;
data.items.forEach((item,i)=>{if(statusWritten[i][5]!==item.delivery_status||statusWritten[i][6]!==item.implementation||statusWritten[i][7]!==item.verification||statusWritten[i][8]!==(waves.get(item.id)||'Unscheduled')) throw new Error(`${item.id}: status/wave projection mismatch`);});
const featuresWritten=tables.get('Features').sheet.getRange(`A4:K${data.features.length+3}`).values;
data.features.forEach((feature,i)=>{if(featuresWritten[i][4]!==feature.implementation||featuresWritten[i][5]!==feature.disposition) throw new Error(`${feature.id}: feature projection mismatch`);});
data.steps.forEach((step,i)=>{if(tables.get('Journey Steps').sheet.getRange(`E${i+4}`).values[0][0]!==step.basis) throw new Error(`${step.id}: basis mismatch`);});
console.log((await wb.inspect({kind:'table',range:'Reconciliation!A3:F18',include:'values,formulas',tableMaxRows:16,tableMaxCols:6,maxChars:7000})).ndjson);
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'Final formula error scan',maxChars:3000});
console.log(errors.ndjson);
if(/"kind":"match"/.test(errors.ndjson)) throw new Error('Formula error detected.');
if(previews){
  await fs.mkdir(path.resolve(previews),{recursive:true});
  for(const [name,entry] of tables){
    const preview=await wb.render({sheetName:name,range:`A1:${entry.last}${Math.min(entry.end,6)}`,scale:1,format:'png'});
    await fs.writeFile(path.join(path.resolve(previews),`${name.replace(/[^A-Za-z0-9]/g,'_')}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
}
for(const [name,expected] of Object.entries(data._snapshot.source_sha256)){
  const raw=await fs.readFile(path.join(root,name));
  const content=['.md','.json','.yaml','.js','.mjs','.py'].includes(path.extname(name))?Buffer.from(raw.toString('utf8').replace(/\r\n/g,'\n')):raw;
  const actual=createHash('sha256').update(content).digest('hex');
  if(actual!==expected) throw new Error(`Source changed while rendering: ${name}. Regenerate after edits settle.`);
}
await fs.mkdir(path.dirname(output),{recursive:true});
const xlsx=await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(output);
if(previews){
  try { await fs.rename(`${output}.inspect.ndjson`,path.join(path.resolve(previews),'xlsx.inspect.ndjson')); }
  catch(error) { if(error.code!=='ENOENT') throw error; }
}
const report={output,snapshotTime:snapshotTime.toISOString(),sheets:tables.size,items:data.items.length,features:data.features.length,steps:data.steps.length,fullContracts:data.steps.filter(contractComplete).length,professional:Object.fromEntries(['advocate_standards','workflow_states','advice_maturity','roles','gap_closures'].map(k=>[k,professional[k].length])),waveRows:data.plan.item_waves.length,sourceHashes:data._snapshot.source_sha256,formulaErrors:0,statusMismatches:0,basisMismatches:0,exactIdMismatches:0};
if(previews) await fs.writeFile(path.join(path.resolve(previews),'verification.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,sourceHashes:'Recorded in workbook Sources and local verification report'},null,2));
