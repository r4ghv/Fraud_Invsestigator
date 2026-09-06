"""Compiles FaceVerificationRegistry.sol into ABI and bytecode artifacts."""

from __future__ import annotations

import json
import os
import solcx

CONTRACT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "contracts", "FaceVerificationRegistry.sol"
)
ARTIFACTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "contracts", "artifacts"
)


def compile_registry(solc_version: str = "0.8.24") -> dict:
    abs_contract = os.path.abspath(CONTRACT_PATH)
    if not os.path.exists(abs_contract):
        raise FileNotFoundError(f"Contract not found: {abs_contract}")

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # Ensure solc installed
    installed = [str(v) for v in solcx.get_installed_solc_versions()]
    if solc_version not in installed:
        print(f"[Compiler] Installing solc {solc_version}...")
        solcx.install_solc(solc_version)

    print(f"[Compiler] Compiling {os.path.basename(abs_contract)} with solc {solc_version}...")
    compiled = solcx.compile_files(
        [abs_contract],
        output_values=["abi", "bin", "bin-runtime"],
        solc_version=solc_version,
        optimize=True,
        optimize_runs=200,
        via_ir=True,
    )

    artifact = next(
        (v for k, v in compiled.items() if k.endswith(":FaceVerificationRegistry")),
        None,
    )
    if artifact is None:
        raise KeyError(
            f"Contract FaceVerificationRegistry not found in compiled output: {compiled.keys()}"
        )
    out_file = os.path.join(ARTIFACTS_DIR, "FaceVerificationRegistry.json")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "contractName": "FaceVerificationRegistry",
                "compiler": f"solc-{solc_version}",
                "abi": artifact["abi"],
                "bytecode": artifact["bin"],
                "deployedBytecode": artifact["bin-runtime"],
            },
            f,
            indent=2,
        )

    print(f"[Compiler] Artifact saved successfully to: {out_file}")
    print(f"  ABI methods: {len(artifact['abi'])}")
    print(f"  Bytecode length: {len(artifact['bin'])} characters")
    return artifact


if __name__ == "__main__":
    compile_registry()
