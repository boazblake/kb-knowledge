# Phase 4 P1/P2 BDD specification (v1)

Checked-in acceptance source. `production_qualification=false`. Links point to
executable tests, not narrative evidence.

## E2E scenarios

### E2E-001 — durable authority-to-query path
**Given** accepted canonical change exists in PostgreSQL authority
**When** outbox row is claimed, envelope is applied, and watermark advances
**Then** barrier is fresh and scoped query returns identity tuple
**Test:** [`test_e2e001_authority_commit_outbox_projection_barrier_query`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-002 — identity and idempotency
**Given** object has full provider/tenant/connector/source-instance/object identity
**When** same request repeats or same revision changes payload
**Then** outcomes are duplicate and conflict respectively
**Test:** [`test_e2e002_duplicate_same_revision_conflict_full_identity_tuple`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-003 — gap recovery
**Given** revision 1 is absent
**When** revision 2 arrives, then revision 1, then revision 2 retries
**Then** gap remains quarantined until ordered recovery
**Test:** [`test_e2e003_gap_quarantine_recovery`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-004 — delete no resurrection
**Given** object has applied revision 1
**When** delete revision 2 applies and stale upsert arrives
**Then** tombstone remains authoritative and projection cannot resurrect
**Test:** [`test_e2e004_delete_no_resurrection`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-005 — source scope isolation
**Given** document belongs to tenant and source namespace
**When** principal lacks source scope or tenant differs
**Then** query is rejected or empty
**Test:** [`test_e2e005_source_scope_and_full_identity_rejection`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-006 — citation tombstone rejection
**Given** citation matches current projection
**When** source scope is changed or authority tombstones document
**Then** citation verification fails
**Test:** [`test_e2e006_citation_tombstone_source_scope_rejection`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-007 — bounded failure replay
**Given** claimed outbox delivery fails to terminal attempt
**When** operator replays dead letter with Principal
**Then** unauthorized Principal is denied and authorized Principal is accepted
**Test:** [`test_p4011_dlq_replay_authorized_vs_unauthorized_principal`](../../tests/test_p1_p2_backend_bdd.py)

### E2E-008 — evidence traceability
**Given** checked-in scenario ledger names current commit and ledger fields
**When** validator runs
**Then** every scenario resolves to an executable test
**Test:** [`test_phase4_bdd_evidence_validator`](../../tests/test_phase4_evidence.py)

### E2E-009 — observational frontend boundary
**Given** backend evidence is non-production
**When** frontend QA runs
**Then** no backend qualification claim is inferred
**Test:** [`tests/frontend_project_visualization_bdd.sh`](../../tests/frontend_project_visualization_bdd.sh) — assertions `Given reference metadata...`, `Given read-only visualization...`, `When page loads...no mutation network request`, `Given stale reference state...`.

### E2E-010 — accessibility boundary
**Given** frontend tests are outside this backend change
**When** existing frontend QA runs
**Then** backend BDD evidence remains independent
**Test:** [`tests/frontend_project_visualization_bdd.sh`](../../tests/frontend_project_visualization_bdd.sh) — assertions `Given keyboard focus...`, `Given visual alternatives...`, `Given failed snapshot delivery...`.

## P4 scenarios

| ID | Given / When / Then | Exact test |
|---|---|---|
| P4-01 | Given full semantic identity; When projection stores it; Then tuple is preserved | `tests/test_p1_p2_backend_bdd.py::BackendBDDPostgres::test_e2e002_duplicate_same_revision_conflict_full_identity_tuple` |
| P4-02 | Given replay envelope; When outbox serializes/deserializes; Then identity and revision round-trip | `tests/test_p4_core.py::P4CoreTests::test_replay_envelope_serialization_round_trip` |
| P4-03 | Given authority commit; When claim/apply/barrier runs; Then durable watermark gates query | `tests/test_p1_p2_backend_bdd.py::BackendBDDPostgres::test_e2e001_authority_commit_outbox_projection_barrier_query` |
| P4-04 | Given unauthorized rows rank higher; When scoped query runs; Then ACL precedes limit | `tests/test_p4_postgres_integration.py::P4PostgresIntegrationTests::test_e2e002_p4_04_acl_before_limit_and_tenant_isolation` |
| P4-05 | Given source-scoped principal; When FTS query runs; Then provenance DTO is bounded | `tests/test_p4_postgres_integration.py::P4PostgresIntegrationTests::test_e2e009_p4_05_source_filter_is_enforced` |
| P4-06 | Given applied watermark below minimum; When barrier observes; Then state is pending/stale, never fresh | `tests/test_p4_postgres_integration.py::P4PostgresIntegrationTests::test_e2e003_p4_06_barrier_blocks_until_watermark` |
| P4-07 | Given delete tombstone; When stale replay arrives; Then no resurrection | `tests/test_p1_p2_backend_bdd.py::BackendBDDPostgres::test_e2e004_delete_no_resurrection` |
| P4-08 | Given citation; When hash, revision, ACL, or tombstone mismatches; Then verification fails | `tests/test_p1_p2_backend_bdd.py::BackendBDDPostgres::test_e2e006_citation_tombstone_source_scope_rejection` |
| P4-09 | Given terminal DLQ; When unauthorized/authorized Principal replays; Then terminal state, recovery, watermark advancement, and authority immutability are observable | `tests/test_p4_postgres_integration.py::P4PostgresIntegrationTests::test_e2e007_p4_09_retry_bounded_dlq_authorized_recovery_and_tombstone` |
| P4-10 | Given evidence ledger; When validator runs; Then current commit and production boundary are checked | `tests/test_phase4_evidence.py::test_phase4_bdd_evidence_validator` |
| P4-11 | Given frontend observation and accessibility checks run; When browser BDD executes; Then read-only, no-mutation, stale, failed-state, and accessibility assertions remain separate from backend evidence | [`tests/frontend_project_visualization_bdd.sh`](../../tests/frontend_project_visualization_bdd.sh) — assertions `Given read-only visualization...`, `When page loads...no mutation network request`, `Given keyboard focus...`, `Given visual alternatives...`, `Given stale reference state...`, `Given failed snapshot delivery...` |
