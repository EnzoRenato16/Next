# /// script
# requires-python = ">=3.8"
# dependencies = ["numpy", "onnx", "onnxruntime"]
# ///
"""Tenta deixar o modelo mais rapido em INT8 — e MEDE se adiantou.

    python3 aibox/quantizar.py

HONESTIDADE SOBRE O QUE ISTO FAZ. Quantizacao DINAMICA troca os pesos para 8
bits sem precisar de dados de calibracao, e por isso e barata de tentar. Mas ela
acelera principalmente multiplicacao de matriz, e uma rede de visao como o YOLO
e quase toda convolucao — pode ganhar muito, pode ganhar nada, e em ARM as duas
coisas acontecem dependendo da versao do runtime.

Por isso este arquivo NAO promete: ele converte, mede os dois lado a lado e diz
o numero. Se nao melhorar, ele mesmo avisa para nao usar — e o modelo original
continua onde estava, intacto.

O caminho que ganha MAIS que isto, e que este arquivo nao faz, e a quantizacao
ESTATICA com calibracao: precisa de umas centenas de imagens da propria sala,
que e coisa para depois da apresentacao.
"""
import os
import statistics
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

TAM = int(os.environ.get("CAM_IMGSZ", "320"))
AQUECE, MEDE = 5, 20


def medir(caminho, img):
    from ultralytics import YOLO
    m = YOLO(caminho)
    for _ in range(AQUECE):
        m.predict(img, imgsz=TAM, verbose=False, classes=[0])
    t = []
    for _ in range(MEDE):
        a = time.perf_counter()
        m.predict(img, imgsz=TAM, verbose=False, classes=[0])
        t.append((time.perf_counter() - a) * 1000)
    return statistics.median(t)


def main():
    import numpy as np
    origem = os.environ.get("MODELO", "yolo11n-pose.onnx")
    if not origem.endswith(".onnx"):
        origem = origem.rsplit(".", 1)[0] + ".onnx"
    if not os.path.exists(origem):
        print(f"nao achei {origem}. Exporte antes:\n"
              f"  python3 -c \"from ultralytics import YOLO; "
              f"YOLO('yolo11n-pose.pt').export(format='onnx', imgsz={TAM})\"")
        return 2
    destino = origem.replace(".onnx", "-int8.onnx")

    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic
    except Exception as e:
        print(f"falta o pacote de quantizacao ({e}).\n"
              f"  python3 -m pip install --target ~/pylibs --no-deps "
              f"onnx onnxruntime")
        return 2

    print(f"convertendo {origem} -> {destino} ...")
    quantize_dynamic(origem, destino, weight_type=QuantType.QUInt8)
    a = os.path.getsize(origem) / 1e6
    b = os.path.getsize(destino) / 1e6
    print(f"tamanho no disco: {a:.1f} MB -> {b:.1f} MB")

    img = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
    print(f"\nmedindo os dois a {TAM}px, {MEDE} inferencias cada...")
    t0 = medir(origem, img)
    t1 = medir(destino, img)
    print(f"  original: {t0:6.1f} ms   ({1000 / t0:.1f}/s)")
    print(f"  int8    : {t1:6.1f} ms   ({1000 / t1:.1f}/s)")

    # O CORTE E 5%. Abaixo disso a diferenca cabe no ruido de duas medicoes
    # seguidas na mesma maquina, e trocar o modelo por causa de ruido e o jeito
    # de piorar achando que melhorou.
    ganho = (t0 - t1) / t0 * 100
    if ganho > 5:
        print(f"\nVALE A PENA: {ganho:.0f}% mais rapido.")
        print(f"No .env, troque para:\n  MODELO={destino}")
    else:
        print(f"\nNAO VALE A PENA ({ganho:+.0f}%). Fique com o original.")
        print("E esperado: a rede e quase toda convolucao, e a quantizacao")
        print("dinamica acelera sobretudo multiplicacao de matriz.")
    print(f"\nO original continua em {origem}, intacto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
