{
  description = "Reproducible kb-pipeline QA and Gate 6 evidence environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = function:
        builtins.listToAttrs (map (system: {
          name = system;
          value = function system;
        }) systems);
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          runtimeInputs = [ pkgs.python311 pkgs.python311Packages.boto3 pkgs.python311Packages.cryptography pkgs.postgresql_16 pkgs.nodejs_22 pkgs.sqlite pkgs.git pkgs.jq pkgs.coreutils ];
        in {
          default = pkgs.mkShell {
            packages = runtimeInputs;
            shellHook = ''
              export PYTHONDONTWRITEBYTECODE=1
              export PYTHONUNBUFFERED=1
            '';
          };
        });

      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          runtimeInputs = [ pkgs.python311 pkgs.python311Packages.boto3 pkgs.python311Packages.cryptography pkgs.postgresql_16 pkgs.nodejs_22 pkgs.sqlite pkgs.git pkgs.jq pkgs.coreutils ];
        in {
          default = pkgs.writeShellApplication {
            name = "kb-pipeline-check";
            inherit runtimeInputs;
            text = ''
              set -euo pipefail
              python -m unittest discover -v
              python -m compileall -q kb_pipeline tests
              node --check frontend/app.js
            '';
          };
        });

      apps = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          runtimeInputs = [ pkgs.python311 pkgs.python311Packages.boto3 pkgs.python311Packages.cryptography pkgs.postgresql_16 pkgs.nodejs_22 pkgs.sqlite pkgs.git pkgs.jq pkgs.coreutils ];
          benchmarkScript = pkgs.writeShellApplication {
            name = "kb-pipeline-benchmark";
            inherit runtimeInputs;
            text = ''
              set -euo pipefail
              echo "Gate 6 repeatable QA preflight"
              python -m unittest discover -v
              python -m unittest discover -v
              python -m compileall -q kb_pipeline tests
              node --check frontend/app.js
            '';
          };
          evidenceScript = pkgs.writeShellApplication {
            name = "kb-pipeline-evidence";
            inherit runtimeInputs;
            text = ''
              set -euo pipefail
              output="''${1:-gate6-environment-evidence.json}"
              python - "$output" <<'PY'
              import json
              import platform
              import subprocess
              import sys
              from pathlib import Path

              def version(command):
                  return subprocess.check_output(command, text=True).strip()

              result = {
                  "schema": "kb-pipeline.gate6-environment-evidence.v1",
                  "python": version([sys.executable, "--version"]),
                  "node": version(["node", "--version"]),
                  "sqlite": version(["sqlite3", "--version"]),
                  "git": version(["git", "--version"]),
                  "platform": platform.platform(),
                  "commands": [
                      "python -m unittest discover -v",
                      "python -m compileall -q kb_pipeline tests",
                      "node --check frontend/app.js",
                      "nix run .#benchmark",
                  ],
                  "note": "Environment/provenance only; does not claim production SRE qualification.",
              }
              Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
              print(json.dumps(result, indent=2))
              PY
            '';
          };
        in {
          check = {
            type = "app";
            program = "${self.packages.${system}.default}/bin/kb-pipeline-check";
          };
          benchmark = {
            type = "app";
            program = "${benchmarkScript}/bin/kb-pipeline-benchmark";
          };
          slo-harness = {
            type = "app";
            program = "${pkgs.writeShellApplication {
              name = "kb-pipeline-slo-harness";
              inherit runtimeInputs;
              text = ''
                set -euo pipefail
                exec python -m kb_pipeline.benchmark "$@"
              '';
            }}/bin/kb-pipeline-slo-harness";
          };
          evidence = {
            type = "app";
            program = "${evidenceScript}/bin/kb-pipeline-evidence";
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          runtimeInputs = [ pkgs.python311 pkgs.postgresql_16 pkgs.nodejs_22 pkgs.sqlite pkgs.git pkgs.jq pkgs.coreutils ];
        in {
          default = pkgs.runCommand "kb-pipeline-check" {
            src = ./.;
            nativeBuildInputs = runtimeInputs;
          } ''
            cp -R "$src"/. .
            chmod -R u+w .
            export PYTHONDONTWRITEBYTECODE=1
            python -m unittest discover -v
            python -m compileall -q kb_pipeline tests
            node --check frontend/app.js
            touch "$out"
          '';
        });
    };
}
