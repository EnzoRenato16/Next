"""Deteccao + reconhecimento facial com OpenCV (YuNet + SFace).

Por que YuNet + SFace (OpenCV Zoo) e nao dlib/face_recognition:
  - Sao modelos ONNX pequenos, rodam em CPU/ARM64 (o AIBOX nao tem GPU CUDA).
  - Ja vem suportados pelo opencv-contrib-python (cv2.FaceDetectorYN /
    cv2.FaceRecognizerSF) — nao precisa compilar dlib no Python 3.8 ARM.
  - Nao dependem do modelo YOLO do professor; sao "nossos" e leves.

YuNet detecta o rosto e 5 pontos (olhos, nariz, cantos da boca). SFace usa
esses pontos para alinhar e gerar um embedding de 128 dimensoes. Comparamos
por distancia de cosseno com o cadastro (data/embeddings.npz).
"""

import numpy as np
import cv2

from . import config


class FaceEngine:
    def __init__(self):
        if not config.YUNET_MODEL.exists() or not config.SFACE_MODEL.exists():
            raise FileNotFoundError(
                "Modelos ONNX ausentes em models/. Veja models/README.md "
                "(YuNet + SFace do OpenCV Zoo)."
            )
        # input_size e ajustado por frame em detect(); comeca em 320x320 (leve).
        self.detector = cv2.FaceDetectorYN.create(
            str(config.YUNET_MODEL), "", (320, 320),
            score_threshold=0.7, nms_threshold=0.3, top_k=50,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(config.SFACE_MODEL), "")

        # Cadastro: matriz de embeddings + labels alinhados.
        self.known_embeddings = np.empty((0, 128), dtype=np.float32)
        self.known_ids: list = []
        self.known_names: list = []
        self.load_enrollment()

    # ---- Cadastro ----------------------------------------------------------
    def load_enrollment(self) -> int:
        if config.EMBEDDINGS_PATH.exists():
            data = np.load(config.EMBEDDINGS_PATH, allow_pickle=True)
            self.known_embeddings = data["embeddings"].astype(np.float32)
            self.known_ids = list(data["ids"])
            self.known_names = list(data["names"])
        return len(self.known_ids)

    # ---- Deteccao ----------------------------------------------------------
    def detect(self, frame):
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)
        return faces if faces is not None else np.empty((0, 15), dtype=np.float32)

    def embedding(self, frame, face_row) -> np.ndarray:
        """Alinha o rosto (usando os landmarks da linha do YuNet) e extrai o embedding."""
        aligned = self.recognizer.alignCrop(frame, face_row)
        feat = self.recognizer.feature(aligned)
        return feat.flatten().astype(np.float32)

    # ---- Matching ----------------------------------------------------------
    def identify(self, feat: np.ndarray):
        """Retorna (student_id, name, score) do melhor match, ou (None, 'Desconhecido', score)."""
        if len(self.known_ids) == 0:
            return None, "Desconhecido", 0.0
        # Cosseno: embeddings do SFace nao sao normalizados; normalizamos aqui.
        a = feat / (np.linalg.norm(feat) + 1e-9)
        b = self.known_embeddings / (
            np.linalg.norm(self.known_embeddings, axis=1, keepdims=True) + 1e-9
        )
        scores = b @ a
        idx = int(np.argmax(scores))
        best = float(scores[idx])
        if best >= config.COSINE_THRESHOLD:
            return self.known_ids[idx], self.known_names[idx], best
        return None, "Desconhecido", best
