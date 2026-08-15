# MOCK/REFERENCE connector qualification

Status: **MOCK/REFERENCE PASS**. This evidence is synthetic-local only and
cannot qualify production or approve real-provider data.

Approved fixture: `ApprovedMockConnectorFixture` using existing
`NangoAdapter`/`FakeNangoTransport`. No provider SDK, credentials, or customer
data used.

## Evidence path

1. Fixture emits namespaced provider/tenant/connector/source identity.
2. Nango contract tests verify cursor acknowledgement, revisions, upsert/update,
   delete, permission changes, retry/permanent classification, duplicate webhook,
   incomplete snapshot safety, provenance, and credential redaction.
3. Fresh UTF-8 Nix PostgreSQL receives four revisions in one synthetic batch.
4. Mock OIDC authorizes tenant/source scope; mock KMS encrypts; existing encrypted
   S3 adapter writes mock raw object; PostgreSQL commits authority and outbox;
   mock workflow starts; telemetry sink records auth/ingestion spans.
5. Existing purge/replay tests establish purge/no-resurrection invariants.

Command:

```sh
nix develop -c bash -c 'set -euo pipefail; PGDATA=$(mktemp -d /tmp/kb-pg.XXXXXX); SOCK=$(mktemp -d /tmp/kb-sock.XXXXXX); PORT=55439; initdb -D "$PGDATA" -A trust --no-locale --encoding=UTF8; pg_ctl -D "$PGDATA" -o "-p $PORT -k $SOCK" -w start; trap "pg_ctl -D \"$PGDATA\" -m immediate stop; rm -rf \"$PGDATA\" \"$SOCK\"" EXIT; P3_POSTGRES_DSN="postgresql://$USER@localhost:$PORT/postgres" python -m unittest discover -v; python -m compileall -q kb_pipeline tests; node --check frontend/app.js'
```

Observed: **186 tests passed**, compile passed, Node syntax check passed.

## Remaining blockers

- No real provider transport or credentials qualified.
- No customer-data authorization or production OIDC/KMS/S3 evidence.
- No production Temporal or OTLP deployment evidence.
- Nix PostgreSQL run is local synthetic integration, not availability, load,
  recovery, or production qualification evidence.
