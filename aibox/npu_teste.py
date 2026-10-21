"""VERSAO NPU: o primeiro teste na caixa. Carrega cada .dlc na NPU, mede o
tempo e compara com o modelo de hoje (CPU) na MESMA imagem.

    source aibox/npu_env.sh && $P aibox/npu_teste.py [foto.jpg]

Sem foto, usa um quadro da camera (CAMERA_ARENA do .env) ou, sem camera, uma
imagem de teste. Nao grava nada, nao abre porta, nao mexe em ~/auditix.
"""
import os
import sys
import time

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox import npu  # noqa: E402


def tempo(f, n=20):
    f()
    t0 = time.monotonic()
    for _ in range(n):
        f()
    return 1000 * (time.monotonic() - t0) / n


def quadro(cv2):
    if len(sys.argv) > 1:
        return cv2.imread(sys.argv[1])
    try:
        from aibox.sala import carregar_env
        carregar_env()
    except Exception:
        pass
    url = os.environ.get("CAMERA_ARENA")
    if url:
        cap = cv2.VideoCapture(url)
        ok, img = cap.read()
        cap.release()
        if ok:
            return img
    print("(sem camera: usando imagem de teste)")
    return cv2.imread(os.path.join(RAIZ, "daten", "models", "teste.jpg")) \
        if os.path.exists(os.path.join(RAIZ, "daten", "models", "teste.jpg")) \
        else np.random.default_rng(1).integers(0, 255, (1080, 1920, 3), np.uint8)


def main():
    import cv2
    img = quadro(cv2)
    print(f"imagem {img.shape[1]}x{img.shape[0]}")
    print(f"runtime pedido: {os.environ.get('NPU_RUNTIME', 'dsp')}  "
          f"SNPE_LIB={os.environ.get('SNPE_LIB', '(padrao)')}")

    # YuNet: CPU de hoje (OpenCV, 1280 de largura) contra a NPU
    cpu = cv2.FaceDetectorYN.create(os.path.join(RAIZ, "daten", "models",
                                                 "face_detection_yunet_2023mar.onnx"),
                                    "", (320, 320), score_threshold=0.7, nms_threshold=0.3)
    e = 1280 / img.shape[1]
    menor = cv2.resize(img, (1280, int(round(img.shape[0] * e))), interpolation=cv2.INTER_AREA)
    cpu.setInputSize((menor.shape[1], menor.shape[0]))
    t_cpu = tempo(lambda: cpu.detect(menor))
    _, a = cpu.detect(menor)
    print(f"\n[YuNet] CPU: {t_cpu:.0f} ms, {0 if a is None else len(a)} rostos")
    det = npu.tentar(npu.DetectorNPU, "YuNet")
    if det:
        b = det.detect(img)
        print(f"[YuNet] NPU: {tempo(lambda: det.detect(img)):.0f} ms (com redimensionar e "
              f"decodificar), {len(b)} rostos")

    arq = os.path.join(npu.NPU_DIR, "arcface.dlc")
    if (os.path.exists(arq) or os.path.exists(arq.replace(".dlc", "_pc.dlc"))) and a is not None and len(a):
        from aibox.arcface import ArcFace
        linha = a[0].copy()
        linha[:14] /= e
        ref = ArcFace()
        va = ref.embedding(img, linha)
        print(f"\n[ArcFace] CPU: {tempo(lambda: ref.embedding(img, linha)):.0f} ms por rosto")
        for nome in ("arcface_pc.dlc", "arcface_pce.dlc", "arcface.dlc", "arcface_a8.dlc"):
            if not os.path.exists(os.path.join(npu.NPU_DIR, nome)):
                continue
            q = npu.tentar(lambda: npu.ArcFaceNPU(os.path.join(npu.NPU_DIR, nome)), nome)
            if q:
                vb = q.embedding(img, linha)
                cos = float(va @ vb / np.linalg.norm(va) / np.linalg.norm(vb))
                print(f"[ArcFace] {nome}: {tempo(lambda: q.embedding(img, linha)):.0f} ms, "
                      f"cosseno com a CPU {cos:.4f}")

    for nome in ("pose.dlc", "pose_a8.dlc"):
        if not os.path.exists(os.path.join(npu.NPU_DIR, nome)):
            continue
        r = npu.tentar(lambda: npu.Rede(os.path.join(npu.NPU_DIR, nome)), nome)
        if r:
            x = np.zeros(r.forma(), np.float32)
            print(f"\n[pose] {nome}: {tempo(lambda: r(entrada=x)):.0f} ms so a rede "
                  f"(na CPU, ONNX 320: ~110 ms)")


if __name__ == "__main__":
    main()
