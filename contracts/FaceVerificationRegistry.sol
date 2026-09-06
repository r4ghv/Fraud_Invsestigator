// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FaceVerificationRegistry
 * @dev Tamper-evident registry for facial biometric embeddings matched to social media posts.
 * Stores cryptographically anchored hashes and attestation proofs on-chain.
 */
contract FaceVerificationRegistry {
    struct VerificationInput {
        bytes32 recordId;
        bytes32 imageHash;            // SHA-256 / keccak hash of input image bytes
        bytes32 faceEmbeddingHash;    // SHA-256 / keccak hash of normalized face embedding
        uint16[4] boundingBox;        // [x, y, w, h] of primary face
        uint16 detectionConfidence;   // e.g. 9516 = 95.16%
        string socialPlatform;        // e.g. "LinkedIn", "Pinterest", "X"
        string socialPostUrl;         // Genuine matching social media post URL
        string socialPostId;          // Platform-specific post/pin identifier
        uint16 matchConfidence;       // e.g. 9900 = 99.00%
    }

    struct VerificationRecord {
        bytes32 recordId;
        bytes32 imageHash;
        bytes32 faceEmbeddingHash;
        uint16[4] boundingBox;
        uint16 detectionConfidence;
        string socialPlatform;
        string socialPostUrl;
        string socialPostId;
        uint16 matchConfidence;
        bytes32 attestationProof;
        uint256 timestamp;
        address attester;
        uint256 blockNumber;
    }

    mapping(bytes32 => VerificationRecord) private _records;
    bytes32[] private _recordIds;
    mapping(bytes32 => bytes32) private _imageToRecord;

    event FaceVerificationRecorded(
        bytes32 indexed recordId,
        address indexed attester,
        bytes32 indexed imageHash,
        string socialPlatform,
        string socialPostUrl,
        uint16 matchConfidence,
        bytes32 attestationProof,
        uint256 timestamp
    );

    /**
     * @notice Registers a tamper-evident face verification match on-chain.
     */
    function registerVerification(VerificationInput calldata input)
        external
        returns (bytes32)
    {
        require(input.recordId != bytes32(0), "Invalid record ID");
        require(input.imageHash != bytes32(0), "Invalid image hash");
        require(input.faceEmbeddingHash != bytes32(0), "Invalid embedding hash");
        require(bytes(input.socialPostUrl).length > 0, "Empty social URL");
        require(_records[input.recordId].timestamp == 0, "Record already exists");

        bytes32 proof = keccak256(
            abi.encodePacked(
                input.recordId,
                input.imageHash,
                input.faceEmbeddingHash,
                input.socialPostUrl,
                msg.sender,
                block.timestamp,
                block.chainid
            )
        );

        _records[input.recordId] = VerificationRecord({
            recordId: input.recordId,
            imageHash: input.imageHash,
            faceEmbeddingHash: input.faceEmbeddingHash,
            boundingBox: input.boundingBox,
            detectionConfidence: input.detectionConfidence,
            socialPlatform: input.socialPlatform,
            socialPostUrl: input.socialPostUrl,
            socialPostId: input.socialPostId,
            matchConfidence: input.matchConfidence,
            attestationProof: proof,
            timestamp: block.timestamp,
            attester: msg.sender,
            blockNumber: block.number
        });

        _recordIds.push(input.recordId);
        _imageToRecord[input.imageHash] = input.recordId;

        emit FaceVerificationRecorded(
            input.recordId,
            msg.sender,
            input.imageHash,
            input.socialPlatform,
            input.socialPostUrl,
            input.matchConfidence,
            proof,
            block.timestamp
        );

        return proof;
    }

    /**
     * @notice Retrieves a verification record by its record ID.
     */
    function getVerification(bytes32 recordId)
        external
        view
        returns (VerificationRecord memory)
    {
        require(_records[recordId].timestamp > 0, "Record does not exist");
        return _records[recordId];
    }

    /**
     * @notice Checks if a record exists.
     */
    function recordExists(bytes32 recordId) external view returns (bool) {
        return _records[recordId].timestamp > 0;
    }

    /**
     * @notice Verifies whether claims match the immutable on-chain record.
     * Tamper-detection function.
     */
    function verifyIntegrity(
        bytes32 recordId,
        bytes32 claimedImageHash,
        bytes32 claimedEmbeddingHash,
        string calldata claimedUrl
    ) external view returns (bool isValid, string memory reason) {
        if (_records[recordId].timestamp == 0) {
            return (false, "Record not found on blockchain");
        }

        VerificationRecord storage rec = _records[recordId];

        if (rec.imageHash != claimedImageHash) {
            return (false, "TAMPER DETECTED: Image hash mismatch");
        }

        if (rec.faceEmbeddingHash != claimedEmbeddingHash) {
            return (false, "TAMPER DETECTED: Face embedding biometric hash mismatch");
        }

        if (keccak256(bytes(rec.socialPostUrl)) != keccak256(bytes(claimedUrl))) {
            return (false, "TAMPER DETECTED: Social media post URL mismatch");
        }

        return (true, "Cryptographic integrity verified. No tampering detected.");
    }

    /**
     * @notice Total registered verification records.
     */
    function totalRecords() external view returns (uint256) {
        return _recordIds.length;
    }

    /**
     * @notice Get record ID by index.
     */
    function getRecordIdByIndex(uint256 index) external view returns (bytes32) {
        require(index < _recordIds.length, "Index out of bounds");
        return _recordIds[index];
    }
}
