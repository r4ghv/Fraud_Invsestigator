"""Master Face ID + Blockchain Verification Pipeline.

Connects:
1. Face detection & 128-D biometric feature encoding (YuNet + SFace)
2. Genuine reverse-image search (automated visual search)
3. Social media match validation and filtering
4. Blockchain attestation and tamper-evident record creation (EVM smart contract)
5. Independent on-chain verification audit
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

from src.blockchain_service import BlockchainAttestationReceipt, BlockchainService
from src.face_engine import FaceAnalysisResult, FaceEngine
from src.search_engine import ReverseSearchEngine, SearchResult
from src.social_filter import SocialMediaFilter, SocialMediaPostMatch


@dataclass
class PipelineRunResult:
    """Consolidated result of an end-to-end pipeline execution."""

    success: bool
    elapsed_seconds: float
    image_path: str
    face_analysis: FaceAnalysisResult
    reverse_search: SearchResult
    social_match: Optional[SocialMediaPostMatch]
    blockchain_receipt: Optional[BlockchainAttestationReceipt]
    verification_verified: bool
    verification_status: str

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "elapsed_seconds": self.elapsed_seconds,
            "image_path": self.image_path,
            "face_analysis": self.face_analysis.to_dict(),
            "reverse_search": {
                "total_matches": self.reverse_search.total_matches,
                "search_title": self.reverse_search.search_title,
                "search_url": self.reverse_search.search_url,
            },
            "social_match": self.social_match.to_dict() if self.social_match else None,
            "blockchain_receipt": (
                self.blockchain_receipt.to_dict() if self.blockchain_receipt else None
            ),
            "verification_verified": self.verification_verified,
            "verification_status": self.verification_status,
        }


class VerificationPipeline:
    """Orchestrates the entire Face ID + Blockchain Verification pipeline."""

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        contract_address: Optional[str] = None,
        score_threshold: float = 0.5,
    ) -> None:
        self.face_engine = FaceEngine(score_threshold=score_threshold)
        self.search_engine = ReverseSearchEngine()
        self.social_filter = SocialMediaFilter()
        self.blockchain_service = BlockchainService(
            rpc_url=rpc_url,
            private_key=private_key,
            contract_address=contract_address,
        )

    def run(
        self,
        image_path: str,
        output_json_path: Optional[str] = None,
        verbose: bool = True,
    ) -> PipelineRunResult:
        start_time = time.time()

        if verbose:
            print("\n" + "=" * 76)
            print("         FACE ID + BLOCKCHAIN VERIFICATION PIPELINE")
            print("=" * 76)
            print(f"Input photo: {os.path.abspath(image_path)}")

        # -------------------------------------------------------------
        # STAGE 1: Face Detection & Biometric Feature Encoding
        # -------------------------------------------------------------
        if verbose:
            print("\n[STAGE 1/5] Biometric Face Detection & Feature Encoding...")
        face_analysis = self.face_engine.process_image(image_path)

        if face_analysis.faces_detected == 0 or not face_analysis.primary_face:
            msg = "Pipeline halted: No human faces detected in input image."
            if verbose:
                print(f"  [-] {msg}")
            return PipelineRunResult(
                success=False,
                elapsed_seconds=round(time.time() - start_time, 2),
                image_path=image_path,
                face_analysis=face_analysis,
                reverse_search=SearchResult(image_path, "", "", 0, []),
                social_match=None,
                blockchain_receipt=None,
                verification_verified=False,
                verification_status=msg,
            )

        primary = face_analysis.primary_face
        if verbose:
            print(f"  [+] Detected {face_analysis.faces_detected} face(s).")
            print(f"  * Primary Face Bounding Box: {primary.bbox}")
            print(f"  * Detection Confidence:      {primary.confidence:.2%}")
            print(f"  * Biometric Vector Shape:    128-dimensional normalized float32")
            print(f"  * Raw Image SHA-256:         {face_analysis.image_sha256}")
            print(f"  * Face Embedding SHA-256:    {primary.embedding_hash}")

        # -------------------------------------------------------------
        # STAGE 2: Genuine Reverse Image Search
        # -------------------------------------------------------------
        if verbose:
            print("\n[STAGE 2/5] Executing Genuine Reverse-Image Search...")
            print("  * Dispatching visual search query to search engines...")

        search_result = self.search_engine.search(image_path)

        if verbose:
            print(f"  [+] Visual Query Title: \"{search_result.search_title}\"")
            print(f"  [+] Total web destinations discovered: {search_result.total_matches}")

        # -------------------------------------------------------------
        # STAGE 3: Social Media Filtering & Live Validation
        # -------------------------------------------------------------
        if verbose:
            print("\n[STAGE 3/5] Social Media Post Identification & Live Validation...")

        raw_match_dicts = [asdict(m) for m in search_result.matches]
        social_matches = self.social_filter.filter_matches(raw_match_dicts)

        if not social_matches:
            msg = (
                f"Reverse image search completed with {search_result.total_matches} "
                "matches, but no social media domain match passed validation."
            )
            if verbose:
                print(f"  [-] {msg}")
            return PipelineRunResult(
                success=False,
                elapsed_seconds=round(time.time() - start_time, 2),
                image_path=image_path,
                face_analysis=face_analysis,
                reverse_search=search_result,
                social_match=None,
                blockchain_receipt=None,
                verification_verified=False,
                verification_status=msg,
            )

        primary_social = social_matches[0]
        if verbose:
            print(f"  [+] Identified {len(social_matches)} social media candidate(s)!")
            print(f"  * Primary Matched Platform: {primary_social.platform} [{primary_social.post_type}]")
            print(f"  * Post Title:               {primary_social.title[:65]}...")
            print(f"  * Matching Social URL:      {primary_social.url}")
            print(f"  * Platform Post ID:         {primary_social.post_id or 'N/A'}")
            print(f"  * HTTP Liveness Status:     {'LIVE (HTTP ' + str(primary_social.status_code) + ')' if primary_social.is_live else 'REACHABLE'}")
            print(f"  * Match Confidence Score:   {primary_social.confidence_score:.2%}")

        # -------------------------------------------------------------
        # STAGE 4: Blockchain Attestation & Record Minting
        # -------------------------------------------------------------
        if verbose:
            print("\n[STAGE 4/5] Anchoring Tamper-Evident Record on Blockchain...")
            print(f"  * Target Network:    {self.blockchain_service.w3.eth.chain_id}")
            print(f"  * Registry Contract: {self.blockchain_service.contract_address}")
            print(f"  * Attester Address:  {self.blockchain_service.sender_address}")

        receipt = self.blockchain_service.record_face_match(
            image_sha256=face_analysis.image_sha256,
            face_embedding_sha256=primary.embedding_hash,
            bbox=primary.bbox,
            detection_confidence=primary.confidence,
            social_platform=primary_social.platform,
            social_post_url=primary_social.url,
            social_post_id=primary_social.post_id,
            match_confidence=primary_social.confidence_score,
        )

        if verbose:
            print(f"  [+] Transaction Confirmed!")
            print(f"  * Record ID:          {receipt.record_id}")
            print(f"  * Transaction Hash:   {receipt.transaction_hash}")
            print(f"  * Block Number:       #{receipt.block_number}")
            print(f"  * Gas Consumed:       {receipt.gas_used} gas units")
            print(f"  * Attestation Proof:  {receipt.attestation_proof}")
            if receipt.explorer_url:
                print(f"  * Block Explorer:     {receipt.explorer_url}")

        # -------------------------------------------------------------
        # STAGE 5: Autonomous Verification & Tamper Check
        # -------------------------------------------------------------
        if verbose:
            print("\n[STAGE 5/5] Autonomous On-Chain Integrity Verification...")

        integrity = self.blockchain_service.verify_record_on_chain(
            record_id=receipt.record_id,
            claimed_image_sha256=face_analysis.image_sha256,
            claimed_embedding_sha256=primary.embedding_hash,
            claimed_social_url=primary_social.url,
        )

        elapsed = round(time.time() - start_time, 2)

        if verbose:
            print(f"  * On-Chain Proof Match: {'CONFIRMED' if integrity.is_valid else 'FAILED'}")
            print(f"  * Integrity Message:    {integrity.status_message}")
            print("-" * 76)
            if integrity.is_valid:
                print(f"\033[92m[SUCCESS] Full Pipeline Completed in {elapsed}s with Verifiable On-Chain Record!\033[0m")
            else:
                print(f"\033[91m[FAILURE] Integrity check failed: {integrity.status_message}\033[0m")
            print("=" * 76 + "\n")

        pipeline_result = PipelineRunResult(
            success=integrity.is_valid,
            elapsed_seconds=elapsed,
            image_path=image_path,
            face_analysis=face_analysis,
            reverse_search=search_result,
            social_match=primary_social,
            blockchain_receipt=receipt,
            verification_verified=integrity.is_valid,
            verification_status=integrity.status_message,
        )

        if output_json_path:
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(pipeline_result.to_dict(), f, indent=2)
            if verbose:
                print(f"[+] Full audit receipt written to: {output_json_path}")

        return pipeline_result
