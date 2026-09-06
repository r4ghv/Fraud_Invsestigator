#!/usr/bin/env python3
"""Main CLI Entrypoint for Face ID + Blockchain Verification Pipeline.

Usage:
  python scripts/run_pipeline.py --image sample_images/portrait_female_1.jpg
  python scripts/run_pipeline.py --image <path> --output receipt.json
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.pipeline import VerificationPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Face ID + Blockchain Verification Pipeline: Biometric Encoding, Reverse Search, and On-Chain Attestation."
    )
    parser.add_argument(
        "--image",
        "-i",
        default="sample_images/portrait_female_1.jpg",
        help="Path to input photo containing face (default: sample_images/portrait_female_1.jpg)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="attestation_receipt.json",
        help="Path to save full JSON audit receipt (default: attestation_receipt.json)",
    )
    parser.add_argument(
        "--rpc-url",
        help="Custom Ethereum RPC URL (e.g. Base Sepolia, Sepolia). Defaults to .env or embedded EVM.",
    )
    parser.add_argument(
        "--private-key",
        help="Custom Ethereum private key. Defaults to .env or generated key.",
    )
    parser.add_argument(
        "--contract",
        help="Custom FaceVerificationRegistry address. Defaults to deployed address.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Face detection confidence threshold (default: 0.5)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"\033[91m[-] Error: Input image file not found: {args.image}\033[0m")
        sys.exit(1)

    pipeline = VerificationPipeline(
        rpc_url=args.rpc_url,
        private_key=args.private_key,
        contract_address=args.contract,
        score_threshold=args.threshold,
    )

    result = pipeline.run(
        image_path=args.image,
        output_json_path=args.output,
        verbose=True,
    )

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
