from __future__ import annotations

from .domain import Input


class IngestionSlice:
    """Connector transport → service → durable cursor workflow boundary."""
    def __init__(self, adapter, service, workflow, telemetry=None):
        self.adapter, self.service, self.workflow, self.telemetry = adapter, service, workflow, telemetry

    def poll_once(self, job_id: str):
        with (self.telemetry.span("ingestion.poll", connector=self.adapter.connector)
              if self.telemetry else _nullspan()):
            batch = self.adapter.poll()
            if hasattr(self.service, "ingest_batch"):
                accepted = self.service.ingest_batch(batch, job_id)
                self.adapter.acknowledge(batch, ledger_accepted=accepted, persist_checkpoint=False)
                checkpoint_acknowledged = True
            else:
                accepted = True
                checkpoint_acknowledged = False
                for raw, change in batch.envelopes:
                    if change.value is None:
                        continue
                    if hasattr(self.service, "ingest_change"):
                        accepted = self.service.ingest_change(raw, change, job_id) and accepted
                        continue
                    value = change.value
                    item = Input(self.adapter.connector, value.document_id, raw.payload,
                                 value.source.source_uri, value.source.observed_at,
                                 dict(raw.metadata), provider=self.adapter.provider_config,
                                 tenant=self.adapter.tenant, source_instance=self.adapter.connection)
                    accepted = self.service.ingest(item, job_id) and accepted
            if not checkpoint_acknowledged:
                self.adapter.acknowledge(batch, ledger_accepted=accepted)
            if accepted and batch.complete:
                with (self.telemetry.span("workflow.start", component="workflow", workload=self.adapter.connector)
                      if self.telemetry else _nullspan()):
                    self.workflow.start_ingestion(job_id, {"cursor": batch.cursor, "run_id": batch.run_id})
                if self.telemetry:
                    self.telemetry.counter("ingestion.accepted")
            return batch, accepted


class _nullspan:
    def __enter__(self): return self
    def __exit__(self, *args): return False
