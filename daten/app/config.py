"""Configuracao central do EduVision.

Regra do roteiro: NENHUMA senha no codigo-fonte. As credenciais da camera
vem de variaveis de ambiente carregadas de config/camera.env (chmod 600,
fora do git). Aqui so lemos os valores.
"""

import os
from pathlib import Path

# ----- Caminhos do projeto (tudo relativo a ~/eduvision) --------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FACES_DIR = DATA_DIR / "faces"          # subpastas por pessoa: data/faces/enzo/*.jpg
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

DB_PATH = DATA_DIR / "eduvision.db"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npz"   # cadastro pronto (gerado pelo enroll)

# ----- Modelos ONNX (OpenCV Zoo — pequenos, rodam em CPU/ARM) ----------------
# Baixe UMA vez antes do laboratorio e coloque em models/ (ver models/README.md).
YUNET_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# ----- Camera (RTSP) --------------------------------------------------------
# Preferimos a variavel CAMERA_RTSP inteira (como no roteiro). Se nao existir,
# montamos a URL a partir das partes (compat com o camera_stream.py de exemplo).
def _build_rtsp_url() -> str:
    url = os.environ.get("CAMERA_RTSP")
    if url:
        return url
    from urllib.parse import quote
    ip = os.environ.get("CAMERA_IP", "192.168.50.108")
    port = os.environ.get("CAMERA_PORT", "554")
    user = os.environ.get("CAMERA_USER", "FIAP")
    pwd = quote(os.environ.get("CAMERA_PASS", ""), safe="")
    subtype = os.environ.get("CAMERA_SUBTYPE", "1")  # 1 = sub-stream (mais leve p/ CPU)
    return (
        f"rtsp://{user}:{pwd}@{ip}:{port}"
        f"/cam/realmonitor?channel=1&subtype={subtype}"
    )

RTSP_URL = _build_rtsp_url()

# Forca RTSP sobre TCP (mais estavel que UDP na rede do lab).
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

ROOM_ID = os.environ.get("ROOM_ID", "SALA_01")
CAMERA_ID = os.environ.get("CAMERA_ID", "CAM_01")
GROUP_ID = os.environ.get("GROUP_ID", "grupo11")

# ----- Parametros de reconhecimento -----------------------------------------
# SFace usa distancia de cosseno. Acima do limiar = mesma pessoa.
# 0.363 (cosseno) e o valor recomendado pela OpenCV para SFace.
COSINE_THRESHOLD = float(os.environ.get("COSINE_THRESHOLD", "0.363"))

# Presenca so e confirmada apos ver a pessoa em N frames (nao confia em 1 frame).
PRESENCE_MIN_HITS = int(os.environ.get("PRESENCE_MIN_HITS", "5"))

# Roda o detector 1x a cada N frames (frame-skip) para aliviar a CPU do AIBOX.
DETECT_EVERY = int(os.environ.get("DETECT_EVERY", "3"))

# ----- API ------------------------------------------------------------------
API_HOST = os.environ.get("API_HOST", "127.0.0.1")   # rede so na validacao final
API_PORT = int(os.environ.get("API_PORT", "8000"))


def mask_secret(url: str) -> str:
    """Esconde a senha ao logar a URL RTSP."""
    import re
    return re.sub(r":([^:@/]+)@", ":****@", url)
