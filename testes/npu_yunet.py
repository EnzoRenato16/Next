"""O pos-processamento do YuNet reescrito para a NPU (aibox/npu.py,
decodificar_yunet) da o MESMO resultado que o cv2.FaceDetectorYN?

    python3 testes/npu_yunet.py [foto.jpg ...]

Sem a caixa e sem a NPU: as 12 saidas cruas do YuNet saem do cv2.dnn com o
ONNX que ja esta no Git, e passam pelo decodificador do npu.py. Se as caixas,
os 5 pontos e a nota nao baterem com o detector do OpenCV, qualquer diferenca
vista na caixa entre NPU e CPU poderia ser do codigo, e nao da quantizacao.
Com a NPU de verdade a conta e a mesma; so a rede muda.

Sem foto, monta uma imagem sintetica (um rosto nao e garantido; o teste entao
so confere que os dois concordam em "nenhum rosto").
"""
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox import npu  # noqa: E402

MODELO = os.path.join(RAIZ, "daten", "models", "face_detection_yunet_2023mar.onnx")
H, W = 736, 1280            # a entrada fixa do yunet.dlc
NOMES = [f"{t}_{p}" for t in ("cls", "obj", "bbox", "kps") for p in (8, 16, 32)]


def tela(cv2, img):
    h, w = img.shape[:2]
    e = min(W / w, H / h)
    nw, nh = int(round(w * e)), int(round(h * e))
    t = np.zeros((H, W, 3), np.uint8)
    t[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return t


def main():
    import cv2
    fotos = [cv2.imread(f) for f in sys.argv[1:]]
    fotos = [f for f in fotos if f is not None]
    if not fotos:
        rng = np.random.default_rng(3)
        fotos = [rng.integers(0, 255, (1080, 1920, 3), np.uint8)]
        print("(sem foto: imagem sintetica, so confere que os dois dizem 'nenhum rosto')")
    ref = cv2.FaceDetectorYN.create(MODELO, "", (W, H), score_threshold=0.7,
                                    nms_threshold=0.3, top_k=50)
    net = cv2.dnn.readNetFromONNX(MODELO)
    falhas = 0
    for img in fotos:
        t = tela(cv2, img)
        _, a = ref.detect(t)
        a = a if a is not None else np.empty((0, 15), np.float32)
        net.setInput(cv2.dnn.blobFromImage(t))
        saida = dict(zip(NOMES, net.forward(NOMES)))
        b = npu.decodificar_yunet(saida, W, H, 0.7, 0.3, 50, cv2)
        if len(a) != len(b):
            print(f"  FALHA: OpenCV achou {len(a)} rosto(s), npu.py achou {len(b)}")
            falhas += 1
            continue
        pior = 0.0
        for la in a:
            j = int(np.argmin([abs(lb[0] - la[0]) + abs(lb[1] - la[1]) for lb in b]))
            pior = max(pior, float(np.abs(la - b[j]).max()))
        ok = pior <= 0.01
        print(f"  {'ok   ' if ok else 'FALHA'} {len(a)} rosto(s), maior diferenca {pior:.4f}")
        falhas += not ok
    print("RESULTADO", "ok" if not falhas else f"{falhas} FALHA(S)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
