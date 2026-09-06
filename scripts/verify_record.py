#!/usr/bin/env python3
"""Independent On-Chain Verification and Tamper Detection Tool.

Audits on-chain biometric attestation records against provided images and URLs,
detecting any manipulation or state divergence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.blockchain_service import BlockchainService
from src.face_engine import FaceEngine

def verify_record(
    record_id: str,
    image_path: str,
    social_url: str,
    rpc_url: str | None = None,
    contract_address: str | None = None,
) -> bool:
    print("\n" + "=" * 70)
    print("      FACE ID + BLOCKCHAIN RECORD INTEGRITY VERIFICATION")
    print("=" * 70)

    print(f"\n[1/3] Biometric Feature Extraction...")
    if not os.path.exists(image_path):
        print(f"[-] Error: Image not found: {image_path}")
        return False

    engine = FaceEngine()
    analysis = engine.process_image(image_path)
    if not analysis.primary_face:
        print(f"[-] Error: No face detected in {image_path}")
        return False

    print(f"  * Image SHA-256: {analysis.image_sha256}")
    print(f"  * Face Embedding SHA-256: {analysis.primary_face.embedding_hash}")
    print(f"  * Detection Confidence: {analysis.primary_face.confidence:.2%}")

    print(f"\n[2/3] Querying Blockchain State...")
    service = BlockchainService(rpc_url=rpc_url, contract_address=contract_address)
    print(f"  * Network: Chain ID {service.chain_id}")
    print(f"  * Contract: {service.contract_address}")
    print(f"  * Target Record ID: {record_id}")

    print(f"\n[3/3] Computing On-Chain Cryptographic Integrity Check...")
    result = service.verify_record_on_chain(
        record_id=record_id,
        claimed_image_sha256=analysis.image_sha256,
        claimed_embedding_sha256=analysis.primary_face.embedding_hash,
        claimed_social_url=social_url,
    )

    print("-" * 70)
    print(f"Record ID:                {result.record_id}")
    print(f"On-Chain Block Number:    #{result.block_number}")
    print(f"On-Chain Attester:        {result.on_chain_attester}")
    print(f"On-Chain Timestamp:       {result.on_chain_timestamp}")
    print(f"Attestation Proof Seal:   {result.attestation_proof}")
    print(f"On-Chain Image Hash:      {result.on_chain_image_hash}")
    print(f"On-Chain Biometric Hash:  {result.on_chain_embedding_hash}")
    print(f"On-Chain Social Post URL: {result.on_chain_social_url}")
    print("-" * 70)

    if result.is_valid:
        print(f"\033[92m[+] STATUS: VERIFIED - TAMPER-EVIDENT PROOF INTACT\033[0m")
        print(f"    {result.status_message}\n")
        return True
    else:
        print(f"\033[91m[-] STATUS: FAILED - {result.status_message}\033[0m\n")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Verify on-chain Face ID and social media match record integrity."
    )
    parser.add_argument(
        "--record-id",
        help="Blockchain record ID (UUID or bytes32)",
    )
    parser.add_argument(
        "--receipt-file",
        help="Path to attestation receipt JSON file (auto-extracts record-id, image, url)",
    )
    parser.add_argument(
        "--image",
        help="Path to candidate face image file",
    )
    parser.add_argument(
        "--url",
        help="Claimed matching social media post URL",
    )
    parser.add_argument(
        "--rpc-url",
        help="Ethereum RPC URL (optional)",
    )
    parser.add_argument(
        "--contract",
        help="FaceVerificationRegistry contract address (optional)",
    )

    args = parser.parse_args()

    record_id = args.record_id
    image_path = args.image
    social_url = args.url

    if args.receipt_file and os.path.exists(args.receipt_file):
        with open(args.receipt_file) as f:
            data = json.load(f)
            b_rec = data.get("blockchain_receipt") or {}
            s_match = data.get("social_match") or {}
            record_id = (
                record_id
                or data.get("record_id")
                or b_rec.get("record_id")
            )
            image_path = (
                image_path
                or data.get("image_path")
                or data.get("query_image")
            )
            social_url = (
                social_url
                or data.get("social_post_url")
                or s_match.get("url")
            )
    if not record_id or not image_path or not social_url:
        parser.error(
            "Missing parameters: specify --record-id, --image, and --url, "
            "or provide --receipt-file."
        )

    success = verify_record(
        record_id=record_id,
        image_path=image_path,
        social_url=social_url,
        rpc_url=args.rpc_url,
        contract_address=args.contract,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
