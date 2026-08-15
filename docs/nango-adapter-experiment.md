# Synthetic Nango adapter experiment

## Decision: EXPERIMENT only

Bounded success. **66 serial tests pass**, including adapter contract scenarios.
This does not recommend production Nango adoption. Real-data pilot remains **NO-GO**.

Adapter maps deterministic Nango-like poll/webhook fixtures into paired `RawRecord`
and `CanonicalChange` envelopes. Scenarios cover duplicate webhooks, retryable polls,
acknowledgement-gated cursors, deletes, incomplete reconciliation, unknown-permission
denial, provenance, capability status, and retention limits.

Local ledger remains authority. Adapter has no ledger, projection, archive, SDK,
network, or credential dependency. Nango cache is not an archive. Caller acknowledges
cursor only after durable ledger acceptance; incomplete snapshots produce no deletes.

## Limitations

Revisions, raw retention, permissions, replay, purge, and credentials remain
unproven for production. Adapter does not own durable checkpoints, provider identity
mapping, credential lifecycle, or deletion across Nango, raw data, projections,
backups, caches, and audit records.

Dynamic-port test isolation fix removes fixed-port collision from covered QA. Serial tests pass;
parallel validation requires port isolation.

Evidence: [`GATE4_QA_RESULTS.json`](../GATE4_QA_RESULTS.json),
[`tests/test_nango_adapter.py`](../tests/test_nango_adapter.py).
