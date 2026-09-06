"""Blockchain verification and attestation service for Face ID records.

Interacts with the FaceVerificationRegistry smart contract on EVM networks
(Base Sepolia, Sepolia, Arbitrum Sepolia, local Anvil/Hardhat, or embedded EVM).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional, Tuple

from eth_account import Account
from hexbytes import HexBytes
from web3 import Web3


@dataclass
class BlockchainAttestationReceipt:
    """Receipt for a face verification record anchored on the blockchain."""

    record_id: str
    record_id_bytes32: str
    transaction_hash: str
    block_number: int
    block_timestamp: int
    gas_used: int
    contract_address: str
    attester_address: str
    attestation_proof: str
    network_name: str
    chain_id: int
    explorer_url: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IntegrityCheckResult:
    """Result of verifying on-chain integrity against claimed data."""

    record_id: str
    is_valid: bool
    status_message: str
    on_chain_image_hash: str
    on_chain_embedding_hash: str
    on_chain_social_url: str
    on_chain_timestamp: int
    on_chain_attester: str
    attestation_proof: str
    block_number: int

    def to_dict(self) -> dict:
        return asdict(self)


class BlockchainService:
    """EVM Blockchain Attestation & Verification Service."""

    ARTIFACT_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "contracts",
        "artifacts",
        "FaceVerificationRegistry.json",
    )
    DEPLOYED_ADDR_PATH = os.path.join(
        os.path.dirname(__file__), "..", "contracts", "deployed_address.json"
    )

    EXPLORERS = {
        84532: "https://sepolia.basescan.org/tx/",
        11155111: "https://sepolia.etherscan.io/tx/",
        421614: "https://sepolia.arbiscan.io/tx/",
        80002: "https://amoy.polygonscan.com/tx/",
        1337: None,
        31337: None,
    }

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        contract_address: Optional[str] = None,
    ) -> None:
        self.rpc_url = rpc_url or os.getenv("RPC_URL")
        self.private_key = private_key or os.getenv("PRIVATE_KEY")
        self.contract_address = contract_address or os.getenv("CONTRACT_ADDRESS")

        self.w3 = self._init_web3()
        self.chain_id = self.w3.eth.chain_id
        self.account = self._init_account()

        # Load contract artifacts
        self.artifact = self._load_artifact()
        self.abi = self.artifact["abi"]
        self.bytecode = self.artifact["bytecode"]

        # Ensure contract is deployed
        self.contract = self._ensure_contract()

    def _init_web3(self) -> Web3:
        if self.rpc_url:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not w3.is_connected():
                raise ConnectionError(f"Could not connect to RPC URL: {self.rpc_url}")
            return w3

        # Auto-detect local EVM node (Anvil / Hardhat)
        local_w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
        try:
            if local_w3.is_connected():
                self.rpc_url = "http://127.0.0.1:8545"
                return local_w3
        except Exception:
            pass

        # Default to embedded cryptographic EVM tester
        from web3 import EthereumTesterProvider

        provider = EthereumTesterProvider()
        return Web3(provider)
    def _init_account(self) -> Any:
        if self.private_key:
            return Account.from_key(self.private_key)
        else:
            # Use account[0] from the provider (e.g. test accounts)
            accounts = self.w3.eth.accounts
            if accounts:
                return accounts[0]
            # Generate a transient account
            new_acc = Account.create()
            return new_acc

    @property
    def sender_address(self) -> str:
        if hasattr(self.account, "address"):
            return self.account.address
        return str(self.account)

    def _load_artifact(self) -> dict:
        abs_path = os.path.abspath(self.ARTIFACT_PATH)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(
                f"Contract artifact not found at {abs_path}. Run scripts/compile_contract.py first."
            )
        with open(abs_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _ensure_contract(self) -> Any:
        """Loads existing contract or deploys a new one if not configured."""
        target_addr = self.contract_address

        # Check deployed_address.json cache if address not explicitly set
        if not target_addr and os.path.exists(self.DEPLOYED_ADDR_PATH):
            try:
                with open(self.DEPLOYED_ADDR_PATH, "r") as f:
                    data = json.load(f)
                    cached_addr = data.get(str(self.chain_id))
                    if cached_addr:
                        target_addr = cached_addr
            except Exception:
                pass

        if target_addr and self.w3.is_address(target_addr):
            code = self.w3.eth.get_code(self.w3.to_checksum_address(target_addr))
            if len(code) > 0:
                self.contract_address = self.w3.to_checksum_address(target_addr)
                return self.w3.eth.contract(address=self.contract_address, abi=self.abi)

        # Deploy contract
        return self._deploy_contract()

    def _deploy_contract(self) -> Any:
        print(f"[Blockchain] Deploying FaceVerificationRegistry to chain ID {self.chain_id}...")
        factory = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)

        if hasattr(self.account, "key"):
            nonce = self.w3.eth.get_transaction_count(self.sender_address)
            tx = factory.constructor().build_transaction(
                {
                    "from": self.sender_address,
                    "nonce": nonce,
                    "gasPrice": self.w3.eth.gas_price,
                    "chainId": self.chain_id,
                }
            )
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        else:
            tx_hash = factory.constructor().transact({"from": self.sender_address})

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        contract_addr = receipt.contractAddress
        self.contract_address = self.w3.to_checksum_address(contract_addr)

        # Cache deployed address
        try:
            cache = {}
            if os.path.exists(self.DEPLOYED_ADDR_PATH):
                with open(self.DEPLOYED_ADDR_PATH, "r") as f:
                    cache = json.load(f)
            cache[str(self.chain_id)] = self.contract_address
            with open(self.DEPLOYED_ADDR_PATH, "w") as f:
                json.dump(cache, f, indent=2)
        except Exception:
            pass

        print(f"[Blockchain] Deployed at: {self.contract_address} (Block #{receipt.blockNumber})")
        return self.w3.eth.contract(address=self.contract_address, abi=self.abi)

    @staticmethod
    def str_to_bytes32(val: str) -> bytes:
        """Converts hex string (SHA-256 or UUID) to 32 bytes."""
        clean = val.lower().replace("-", "")
        if clean.startswith("0x"):
            clean = clean[2:]
        # Pad or truncate to 64 hex chars (32 bytes)
        clean = clean.ljust(64, "0")[:64]
        return bytes.fromhex(clean)

    def record_face_match(
        self,
        image_sha256: str,
        face_embedding_sha256: str,
        bbox: Tuple[int, int, int, int],
        detection_confidence: float,
        social_platform: str,
        social_post_url: str,
        social_post_id: Optional[str] = None,
        match_confidence: float = 0.95,
        record_id: Optional[str] = None,
    ) -> BlockchainAttestationReceipt:
        """Uploads a face match record to the blockchain registry."""
        rec_id_str = record_id or str(uuid.uuid4())
        rec_id_bytes = self.str_to_bytes32(rec_id_str)
        img_hash_bytes = self.str_to_bytes32(image_sha256)
        emb_hash_bytes = self.str_to_bytes32(face_embedding_sha256)

        # Scale bbox to uint16
        bounded_bbox = [max(0, min(65535, int(v))) for v in bbox]

        # Scale confidences to basis points (0-10000)
        det_conf_bp = int(detection_confidence * 10000)
        match_conf_bp = int(match_confidence * 10000)

        post_id_str = social_post_id or ""

        # Struct input matching VerificationInput
        verification_input = {
            "recordId": rec_id_bytes,
            "imageHash": img_hash_bytes,
            "faceEmbeddingHash": emb_hash_bytes,
            "boundingBox": bounded_bbox,
            "detectionConfidence": det_conf_bp,
            "socialPlatform": social_platform,
            "socialPostUrl": social_post_url,
            "socialPostId": post_id_str,
            "matchConfidence": match_conf_bp,
        }

        fn = self.contract.functions.registerVerification(verification_input)

        if hasattr(self.account, "key"):
            nonce = self.w3.eth.get_transaction_count(self.sender_address)
            gas_est = fn.estimate_gas({"from": self.sender_address})
            tx = fn.build_transaction(
                {
                    "from": self.sender_address,
                    "nonce": nonce,
                    "gas": int(gas_est * 1.2),
                    "gasPrice": self.w3.eth.gas_price,
                    "chainId": self.chain_id,
                }
            )
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        else:
            tx_hash = fn.transact({"from": self.sender_address})

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Get block timestamp
        block = self.w3.eth.get_block(receipt.blockNumber)
        block_timestamp = block.timestamp

        # Extract event logs
        logs = self.contract.events.FaceVerificationRecorded().process_receipt(receipt)
        proof_hex = ""
        if logs:
            proof_bytes = logs[0].args.attestationProof
            proof_hex = (
                proof_bytes.hex() if isinstance(proof_bytes, bytes) else str(proof_bytes)
            )
            if not proof_hex.startswith("0x"):
                proof_hex = "0x" + proof_hex

        # Format explorer URL if network is known
        explorer_base = self.EXPLORERS.get(self.chain_id)
        tx_hex = receipt.transactionHash.hex()
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex

        explorer_url = f"{explorer_base}{tx_hex}" if explorer_base else None

        network_names = {
            84532: "Base Sepolia Testnet",
            11155111: "Ethereum Sepolia Testnet",
            421614: "Arbitrum Sepolia Testnet",
            80002: "Polygon Amoy Testnet",
            1337: "Local Ethereum / PyEVM",
            31337: "Local Anvil / Hardhat",
        }
        net_name = network_names.get(self.chain_id, f"EVM Network (Chain #{self.chain_id})")

        return BlockchainAttestationReceipt(
            record_id=rec_id_str,
            record_id_bytes32="0x" + rec_id_bytes.hex(),
            transaction_hash=tx_hex,
            block_number=receipt.blockNumber,
            block_timestamp=block_timestamp,
            gas_used=receipt.gasUsed,
            contract_address=self.contract_address,
            attester_address=self.sender_address,
            attestation_proof=proof_hex,
            network_name=net_name,
            chain_id=self.chain_id,
            explorer_url=explorer_url,
        )

    def verify_record_on_chain(
        self,
        record_id: str,
        claimed_image_sha256: str,
        claimed_embedding_sha256: str,
        claimed_social_url: str,
    ) -> IntegrityCheckResult:
        """Performs on-chain tamper detection and integrity check."""
        rec_id_bytes = self.str_to_bytes32(record_id)
        img_bytes = self.str_to_bytes32(claimed_image_sha256)
        emb_bytes = self.str_to_bytes32(claimed_embedding_sha256)

        # Call verifyIntegrity view function
        is_valid, reason = self.contract.functions.verifyIntegrity(
            rec_id_bytes, img_bytes, emb_bytes, claimed_social_url
        ).call()

        # Fetch full on-chain record
        raw_rec = self.contract.functions.getVerification(rec_id_bytes).call()
        # raw_rec fields: [recordId, imageHash, faceEmbeddingHash, boundingBox, detectionConfidence, socialPlatform, socialPostUrl, socialPostId, matchConfidence, attestationProof, timestamp, attester, blockNumber]

        return IntegrityCheckResult(
            record_id=record_id,
            is_valid=is_valid,
            status_message=reason,
            on_chain_image_hash="0x" + HexBytes(raw_rec[1]).hex(),
            on_chain_embedding_hash="0x" + HexBytes(raw_rec[2]).hex(),
            on_chain_social_url=raw_rec[6],
            on_chain_timestamp=raw_rec[10],
            on_chain_attester=raw_rec[11],
            attestation_proof="0x" + HexBytes(raw_rec[9]).hex(),
            block_number=raw_rec[12],
        )

    def total_records(self) -> int:
        return self.contract.functions.totalRecords().call()
