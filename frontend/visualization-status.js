/* Shared visualization facts. JSON is canonical; this mirror keeps direct-file views usable. */
window.VISUALIZATION_STATUS = Object.freeze({
  snapshot:'Authoritative SRE snapshot · HEAD 18a4c39 · tested ancestor 397911e01029c8e626d98b9661263f8a2f7ff00c · 2026-08-15',
  commits:{head:'18a4c39',tested:'397911e01029c8e626d98b9661263f8a2f7ff00c',testedIsAncestor:true},
  migrations:{applied:[1,2,3,4,5,6,7],freshRun:'1..7',secondRun:'no-op'},
  evidenceScope:'Mock providers/reference evidence only; no live provider qualification.', production_qualification:false,
  mode:'MOCK / REFERENCE', decision:'Production NO-GO',
  statuses:{bdd:'PASS',sre:'CONDITIONAL DEVELOPER GO',qa:'SCRIPTED QA ONLY',production:'NO-GO'},
  dirtyWorktree:'Dirty only due excluded frontend/repository-metrics.json; excluded from evidence.',
  evidenceRun:{runDate:'2026-08-15',nix:{label:'Nix suite · no PostgreSQL DSN',passed:221,skipped:34,failed:0},disposablePostgresql:{label:'Fresh disposable PostgreSQL suite',passed:221,skipped:0,failed:0},frontendBdd:{label:'Frontend BDD',passed:9,failed:0}},
  next:'Refresh evidence/runbook metadata, then scripted test-operator handoff; production gates remain deferred.',
  horizons:['Prototype/reference','Production-shaped non-prod','Production qualification/release'],
  limitations:['Mock providers/reference only','No live provider qualification','Read-only/observational surface','Production gates deferred'], readOnly:true,
  provider:{liveCalls:0,qualification:'not performed'}, p4:{authoritySequence:{accepted:42,applied:40,state:'stale'},barriers:['fresh','pending','stale','blocked','timeout'],ingestOutcomes:['accepted','duplicate','stale','gap','conflict','rejected','failed'],lifecycle:['delete','tombstone','purge','replay']}
});
window.visualizationEvidence=()=>window.VISUALIZATION_STATUS.evidenceRun;
window.visualizationRunLabel=run=>`${run.passed} passed / ${run.skipped ?? 0} skipped / ${run.failed} failed`;
window.renderVisualizationStatus=()=>{const s=window.VISUALIZATION_STATUS;let el=document.querySelector('#shared-status');if(!el){el=document.createElement('aside');el.id='shared-status';el.className='shared-status';el.setAttribute('aria-label','Authoritative SRE snapshot');document.querySelector('main')?.prepend(el);}el.innerHTML=`<strong>${s.decision}</strong><span>HEAD <code>${s.commits.head}</code> · tested ancestor <code>${s.commits.tested}</code> · migrations ${s.migrations.freshRun} (second run ${s.migrations.secondRun})</span><span>BDD ${s.statuses.bdd} · SRE ${s.statuses.sre} · test-operator ${s.statuses.qa} · production ${s.statuses.production}</span><span>${s.dirtyWorktree}</span>`;};
window.validateVisualizationStatus=json=>json?.commits?.head==='18a4c39'&&json?.commits?.tested===window.VISUALIZATION_STATUS.commits.tested&&json?.production_qualification===false&&JSON.stringify(json?.migrations?.applied)===JSON.stringify([1,2,3,4,5,6,7])&&json?.evidenceRun?.nix?.passed===221&&json?.evidenceRun?.nix?.skipped===34&&json?.evidenceRun?.disposablePostgresql?.passed===221&&json?.evidenceRun?.frontendBdd?.passed===9;
window.renderVisualizationStatus();
fetch('visualization-status.json',{headers:{Accept:'application/json'}}).then(r=>r.ok?r.json():Promise.reject()).then(j=>{if(!window.validateVisualizationStatus(j))throw new Error('visualization status mismatch');document.documentElement.dataset.statusValidated='true';}).catch(()=>{document.documentElement.dataset.statusValidated='false';});
