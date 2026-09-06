"""Face ID detection and biometric encoding engine using YuNet and SFace.

Detects faces, localizes 5 facial landmarks, aligns facial crops, extracts
128-dimensional biometric embeddings, and generates cryptographic hashes for
on-chain attestation and tamper verification.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple, Union

import cv2
import numpy as np


@dataclass
class DetectedFace:
    """Represents a detected and biometrically encoded face."""

    face_id: int
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    confidence: float
    landmarks: List[Tuple[float, float]]  # 5 landmarks
    embedding: List[float]  # 128-D normalized embedding vector
    embedding_hash: str  # SHA-256 hash of the embedding vector
    aligned_crop_shape: Tuple[int, int, int]


@dataclass
class FaceAnalysisResult:
    """Aggregate result of analyzing an image for faces."""

    image_path: str
    image_width: int
    image_height: int
    image_sha256: str
    faces_detected: int
    faces: List[DetectedFace]
    primary_face: Optional[DetectedFace]

    def to_dict(self) -> dict:
        return asdict(self)


class FaceEngine:
    """Production face detection and encoding pipeline."""

    DEFAULT_DETECTOR_MODEL = os.path.join(
        os.path.dirname(__file__), "..", "models", "face_detection_yunet.onnx"
    )
    DEFAULT_RECOGNIZER_MODEL = os.path.join(
        os.path.dirname(__file__), "..", "models", "face_recognition_sface.onnx"
    )

    def __init__(
        self,
        detector_path: Optional[str] = None,
        recognizer_path: Optional[str] = None,
        score_threshold: float = 0.5,
        nms_threshold: float = 0.3,
        top_k: int = 5000,
    ) -> None:
        self.detector_path = os.path.abspath(detector_path or self.DEFAULT_DETECTOR_MODEL)
        self.recognizer_path = os.path.abspath(
            recognizer_path or self.DEFAULT_RECOGNIZER_MODEL
        )
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k

        if not os.path.exists(self.detector_path):
            raise FileNotFoundError(
                f"Face detector model not found at {self.detector_path}"
            )
        if not os.path.exists(self.recognizer_path):
            raise FileNotFoundError(
                f"Face recognizer model not found at {self.recognizer_path}"
            )

        self._recognizer = cv2.FaceRecognizerSF.create(self.recognizer_path, "")

    def _get_detector(self, width: int, height: int) -> cv2.FaceDetectorYN:
        return cv2.FaceDetectorYN.create(
            model=self.detector_path,
            config="",
            input_size=(width, height),
            score_threshold=self.score_threshold,
            nms_threshold=self.nms_threshold,
            top_k=self.top_k,
        )

    @staticmethod
    def compute_sha256_of_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def compute_embedding_hash(embedding: np.ndarray) -> str:
        """Compute deterministic SHA-256 hash of the float32 embedding."""
        vec = np.ascontiguousarray(embedding.reshape(-1), dtype=np.float32)
        return hashlib.sha256(vec.tobytes()).hexdigest()

    def load_image(self, image_input: Union[str, bytes, np.ndarray]) -> Tuple[np.ndarray, str]:
        """Loads image and returns BGR numpy array + sha256 of raw data."""
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Input image not found: {image_input}")
            with open(image_input, "rb") as f:
                raw_bytes = f.read()
            img_hash = self.compute_sha256_of_bytes(raw_bytes)
            img = cv2.imread(image_input)
            if img is None:
                raise ValueError(f"Could not decode image at {image_input}")
            return img, img_hash
        elif isinstance(image_input, bytes):
            img_hash = self.compute_sha256_of_bytes(image_input)
            nparr = np.frombuffer(image_input, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Could not decode image bytes")
            return img, img_hash
        elif isinstance(image_input, np.ndarray):
            img = image_input
            img_hash = self.compute_sha256_of_bytes(img.tobytes())
            return img, img_hash
        else:
            raise TypeError("Unsupported image input type")

    def process_image(
        self, image_input: Union[str, bytes, np.ndarray], image_label: str = "input_image"
    ) -> FaceAnalysisResult:
        """Detect faces and extract biometric embeddings."""
        img, img_hash = self.load_image(image_input)
        h, w, _ = img.shape

        detector = self._get_detector(w, h)
        _, raw_faces = detector.detect(img)

        detected_faces: List[DetectedFace] = []

        if raw_faces is not None and len(raw_faces) > 0:
            for idx, raw_face in enumerate(raw_faces):
                conf = float(raw_face[-1])
                bbox = (
                    int(raw_face[0]),
                    int(raw_face[1]),
                    int(raw_face[2]),
                    int(raw_face[3]),
                )
                landmarks = [
                    (float(raw_face[i]), float(raw_face[i + 1]))
                    for i in range(4, 14, 2)
                ]

                # Align crop and extract feature
                aligned = self._recognizer.alignCrop(img, raw_face)
                feature = self._recognizer.feature(aligned)

                # Normalize embedding to unit sphere
                norm = float(np.linalg.norm(feature))
                if norm > 0:
                    normalized_vec = feature / norm
                else:
                    normalized_vec = feature

                emb_list = [float(v) for v in normalized_vec.reshape(-1)]
                emb_hash = self.compute_embedding_hash(normalized_vec)

                detected_faces.append(
                    DetectedFace(
                        face_id=idx,
                        bbox=bbox,
                        confidence=conf,
                        landmarks=landmarks,
                        embedding=emb_list,
                        embedding_hash=emb_hash,
                        aligned_crop_shape=aligned.shape,
                    )
                )

        # Sort by confidence descending
        detected_faces.sort(key=lambda f: f.confidence, reverse=True)
        primary = detected_faces[0] if detected_faces else None

        source_path = image_input if isinstance(image_input, str) else image_label

        return FaceAnalysisResult(
            image_path=str(source_path),
            image_width=w,
            image_height=h,
            image_sha256=img_hash,
            faces_detected=len(detected_faces),
            faces=detected_faces,
            primary_face=primary,
        )

    def compare_embeddings(
        self, emb1: Union[List[float], np.ndarray], emb2: Union[List[float], np.ndarray]
    ) -> Tuple[float, float, bool]:
        """Compares two embeddings.

        Returns: (cosine_similarity, l2_distance, is_match)
        """
        v1 = np.array(emb1, dtype=np.float32).reshape(-1)
        v2 = np.array(emb2, dtype=np.float32).reshape(-1)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 > 0:
            v1 = v1 / norm1
        if norm2 > 0:
            v2 = v2 / norm2

        cosine_sim = float(np.dot(v1, v2))
        l2_dist = float(np.linalg.norm(v1 - v2))

        # SFace cosine similarity threshold is typically 0.363
        is_match = cosine_sim >= 0.363
        return cosine_sim, l2_dist, is_match

    def draw_detections(
        self, image_input: Union[str, np.ndarray], result: FaceAnalysisResult
    ) -> np.ndarray:
        """Annotates image with bounding boxes, landmarks, confidence, and embedding hashes."""
        img, _ = self.load_image(image_input)
        annotated = img.copy()

        for face in result.faces:
            x, y, w, h = face.bbox
            # Draw bounding box
            color = (0, 255, 0) if face == result.primary_face else (255, 180, 0)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)

            # Draw 5 landmarks
            colors = [
                (0, 0, 255),    # right eye
                (0, 255, 255),  # left eye
                (255, 0, 0),    # nose tip
                (0, 165, 255),  # mouth right
                (255, 0, 255),  # mouth left
            ]
            for (lx, ly), c in zip(face.landmarks, colors):
                cv2.circle(annotated, (int(lx), int(ly)), 4, c, -1)

            # Tag with conf and short hash
            label = f"Face #{face.face_id} ({face.confidence:.1%}) Hash:{face.embedding_hash[:8]}..."
            cv2.putText(
                annotated,
                label,
                (x, max(20, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )

        return annotated
