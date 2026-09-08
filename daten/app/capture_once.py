"""Passo 6 do roteiro — captura 1 frame e salva em data/frame.jpg.

Teste minimo ANTES do streaming continuo. Nao avance para a IA enquanto
isso nao funcionar.

    source config/camera.env
    python -m app.capture_once
"""

import sys
import cv2
from . import config


def main() -> int:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("RTSP:", config.mask_secret(config.RTSP_URL))
    cap = cv2.VideoCapture(config.RTSP_URL)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("[ERRO] Falha ao capturar frame RTSP.")
        return 1
    out = config.DATA_DIR / "frame.jpg"
    cv2.imwrite(str(out), frame)
    print(f"OK: {out} ({frame.shape[1]}x{frame.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
