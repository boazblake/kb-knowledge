# Reproducible Nix environment

`flake.nix` pins nixpkgs through `flake.lock` and exposes Python 3.11, Node.js
22, SQLite CLI, Git, `jq`, and coreutils. Python dependencies are empty in
`pyproject.toml`; project code uses Python standard library only.

## Commands

Enter environment:

```sh
nix develop
```

Run QA checks directly:

```sh
python -m unittest discover -v
python -m compileall -q kb_pipeline tests
node --check frontend/app.js
```

Run packaged checks without entering shell:

```sh
nix run .#check
nix flake check
```

Generate environment/provenance evidence:

```sh
nix run .#evidence -- gate6-environment-evidence.json
```

Run repeatable Gate 6 QA preflight (two unittest passes plus compile and Node
checks):

```sh
nix run .#benchmark
```

Run synthetic SLO harness inside pinned environment:

```sh
nix run .#slo-harness -- --records 200 --searches 200 --concurrency 4 --warmup 20
```

Harness emits local/simulated measurements only. Do not treat output or `.#benchmark`
as production capacity, SLO, RPO, RTO, concurrency, or rollback evidence.

## Reproducibility and rollback

Commit `flake.nix` and `flake.lock`. `nix develop`, `nix run`, and
`nix flake check` use lock-pinned nixpkgs. Roll back environment-only changes by
reverting those files and this document; no application or deployment state is
modified.
