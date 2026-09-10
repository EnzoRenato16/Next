"""Medicao de desempenho no proprio aparelho — rode antes de otimizar.

    python -m app.bench

Existe porque a recomendacao "troque para ONNX Runtime" nao se confirmou aqui:
em x86 o ORT ficou mais lento que o OpenCV DNN nas duas versoes testadas. No
ARM64 do AIBOX pode inverter. Em vez de escolher por suposicao, este script
mede as duas coisas que realmente pesam e imprime o que colocar no camera.env.

O que ele mede:
  1. DETECT_WIDTH — quanto custa o YuNet em cada largura, e a partir de que
     largura um rosto do tamanho que voce informou ainda e encontrado.
  2. SFACE_BACKEND — OpenCV DNN contra ONNX Runtime, no mesmo rosto, com
     conferencia de que os dois devolvem o MESMO embedding.
"""

import sys
import time

import numpy as np
import cv2

from . import config

LARGURAS = (1280, 960, 640, 480, 320)


def _cronometrar(fn, repeticoes=15) -> float:
    """Milissegundos por chamada, descartando a primeira (aquecimento)."""
    fn()
    inicio = time.perf_counter()
    for _ in range(repeticoes):
        fn()
    return (time.perf_counter() - inicio) / repeticoes * 1000


def _frame_de_teste():
    """Usa o frame real da camera se existir; senao, uma cena sintetica.

    O frame real vale muito mais: com ele a coluna "achou" da tabela vira a
    resposta de verdade — em que largura o YuNet ainda enxerga as pessoas
    NA SUA SALA. Para gerar:  python -m app.capture_once

    Sem ele a medicao de CUSTO continua valida (o custo depende da resolucao,
    nao do conteudo), mas a de ACERTO nao, e o script avisa isso.
    """
    caminho = config.DATA_DIR / "frame.jpg"
    if caminho.exists():
        frame = cv2.imread(str(caminho))
        if frame is not None:
            print(f"Frame real: {caminho} ({frame.shape[1]}x{frame.shape[0]})")
            return frame, True
    print("Sem data/frame.jpg — usando cena sintetica.")
    print("Para medir ACERTO tambem, rode antes: python -m app.capture_once")
    frame = np.full((720, 1280, 3), 60, np.uint8)
    cv2.ellipse(frame, (640, 300), (55, 68), 0, 0, 360, (170, 150, 140), -1)
    return frame, False


def medir_deteccao(engine, frame, real: bool) -> None:
    h, w = frame.shape[:2]
    print(f"\n1. DETECT_WIDTH — custo do YuNet em {w}x{h}")
    print("   " + "-" * 58)
    base = None
    for largura in LARGURAS:
        if largura > w:
            continue
        anterior = config.DETECT_WIDTH
        config.DETECT_WIDTH = largura
        try:
            ms = _cronometrar(lambda: engine.detect(frame))
            achados = len(engine.detect(frame))
        finally:
            config.DETECT_WIDTH = anterior
        if base is None:
            base = ms
        rosto_min = int(config.MIN_FACE_PX / (largura / w))
        marca = f"[achou {achados}]" if real else ""
        print(f"   W={largura:<5} {ms:7.2f} ms  ({base / ms:4.1f}x)   "
              f"rosto precisa ter >= {rosto_min:3d} px no frame   {marca}")
    print(f"\n   Regra: o rosto tem que passar de {config.MIN_FACE_PX} px DEPOIS de reduzir.")
    if real:
        print("   Escolha a MENOR largura que ainda ache todo mundo da sala.")
    else:
        print("   A coluna 'achou' so aparece com frame real (app.capture_once).")


def medir_backend(engine, frame) -> None:
    print("\n2. SFACE_BACKEND — OpenCV DNN contra ONNX Runtime")
    print("   " + "-" * 58)

    faces = engine.detect(frame, full_res=True)
    if len(faces):
        alinhado = engine.recognizer.alignCrop(frame, faces[0])
    else:
        # Sem rosto detectado a medicao do custo continua valida: o SFace
        # sempre recebe um recorte 112x112, venha ele de onde vier.
        rng = np.random.default_rng(7)
        alinhado = rng.integers(0, 255, (112, 112, 3), dtype=np.uint8)
        print("   (sem rosto na cena sintetica; medindo com recorte 112x112)")

    ms_cv = _cronometrar(lambda: engine.recognizer.feature(alinhado), 25)
    print(f"   OpenCV DNN     : {ms_cv:7.2f} ms/rosto")

    try:
        from .recognizer import _SFaceORT
        ort_engine = _SFaceORT(str(config.SFACE_MODEL), config.ORT_THREADS)
    except ImportError:
        print("   ONNX Runtime   : nao instalado (pip install onnxruntime)")
        print("\n   Mantenha SFACE_BACKEND=opencv.")
        return
    except Exception as e:
        print(f"   ONNX Runtime   : nao subiu ({e})")
        return

    ms_ort = _cronometrar(lambda: ort_engine.feature(alinhado), 25)
    a = engine.recognizer.feature(alinhado).flatten().astype(np.float32)
    b = ort_engine.feature(alinhado).flatten().astype(np.float32)
    cos = float((a / np.linalg.norm(a)) @ (b / np.linalg.norm(b)))

    print(f"   ONNX Runtime   : {ms_ort:7.2f} ms/rosto")
    print(f"   paridade do embedding: {cos:.6f}  (tem que ser 1.000000)")

    print()
    if cos < 0.9999:
        print("   NAO troque: os backends discordam, o cadastro de um nao vale no outro.")
    elif ms_ort < ms_cv * 0.9:
        print(f"   Troque: ORT e {ms_cv / ms_ort:.2f}x mais rapido aqui.")
        print("   Ponha no config/camera.env:  export SFACE_BACKEND=ort")
    else:
        print(f"   Nao compensa: ORT e {ms_ort / ms_cv:.2f}x o tempo do OpenCV.")
        print("   Mantenha SFACE_BACKEND=opencv (que ja e o padrao).")


def main() -> int:
    from .recognizer import FaceEngine

    print("=" * 64)
    print("EduVision — medicao de desempenho")
    print(f"OpenCV {cv2.__version__} · threads {cv2.getNumThreads()} · "
          f"backend atual: {config.SFACE_BACKEND}")
    print("=" * 64)

    try:
        engine = FaceEngine()
    except FileNotFoundError as e:
        print(f"\n[ERRO] {e}")
        return 1

    frame, real = _frame_de_teste()
    medir_deteccao(engine, frame, real)
    medir_backend(engine, frame)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
