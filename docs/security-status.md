# Security adapter status

Implemented: fail-closed offline OIDC claim/signature/expiry validation;
tenant, role, and source-scope decisions; KMS-shaped authenticated envelopes;
rotation, retirement, erasure states; production guards; DTO allow-list.

Not implemented: network JWKS refresh, real KMS calls, credentials,
transparent artifact reads, or canonical ledger ciphertext migration.
