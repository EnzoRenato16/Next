# /// script
# requires-python = ">=3.8"
# dependencies = ["numpy", "opencv-python-headless"]
# ///
"""Quanto da para espremer desta caixa. Roda NA CAIXA, nao no PC.

    python3 aibox/medir.py            # tudo
    python3 aibox/medir.py --camera   # so o teto da camera
    python3 aibox/medir.py --modelo   # so o modelo
    python3 aibox/medir.py --nucleos  # nucleos grandes x todos (QCS6490)

POR QUE MEDIR ANTES DE OTIMIZAR. O alvo de 30 quadros por segundo tem DOIS
tetos independentes, e mexer no errado e trabalho jogado fora:

  1. O TETO DA CAMERA. Se o substream entrega 15/s, 30/s e impossivel por mais
     rapido que o modelo fique. Isso se resolve na configuracao da camera, nao
     no codigo.
  2. O TETO DO MODELO. Quanto tempo a inferencia leva, por tamanho de entrada.

Este arquivo mede os dois separados e diz qual esta segurando.

A medida do modelo descarta as primeiras inferencias de proposito: a primeira
carrega pesos e aloca buffers, e incluir isso na media daria um numero que nao
se repete em nenhum outro quadro do dia.
"""
import argparse
import os
import statistics
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

TAMANHOS = (320, 288, 256, 224, 192, 160)
AQUECE = 5
MEDE = 25


def carregar_env():
    caminho = os.path.join(RAIZ, ".env")
    if not os.path.exists(caminho):
        return
    for linha in open(caminho, encoding="utf-8"):
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def teto_da_camera(segundos=12.0):
    from aibox.gstcam import Gst
    url = os.environ.get("CAMERA_RTSP")
    if not url:
        print("  (sem CAMERA_RTSP no .env — pulando)")
        return None
    cap = Gst(url)
    t0 = time.monotonic()
    while time.monotonic() - t0 < segundos:
        cap.read()
        time.sleep(0.005)
    seg = time.monotonic() - t0
    n = cap.lidos
    cap.release()
    taxa = n / seg
    print(f"  a camera entregou {n} quadros em {seg:.0f}s  ->  "
          f"{taxa:.1f} quadros/s")
    if taxa < 1:
        print("  NENHUM quadro chegou. Confira usuario, senha e o caminho do "
              "fluxo no .env.")
    elif taxa < 20:
        print(f"  ESTE E O TETO. Nenhuma otimizacao de modelo passa de "
              f"{taxa:.0f}/s enquanto a camera entregar isto.")
        print("  Para subir: no site da camera, aumente o FPS do substream, ou")
        print("  troque subtype=1 por subtype=0 (fluxo principal, mais pesado")
        print("  de decodificar — meça de novo depois de trocar).")
    else:
        print("  a camera nao e o gargalo.")
    return taxa


def teto_do_modelo():
    import numpy as np
    try:
        from ultralytics import YOLO
    except Exception as e:
        print(f"  ultralytics nao importou ({e}); pulando")
        return {}
    modelo = os.environ.get("MODELO", "yolo11n-pose.pt")
    if not os.path.exists(os.path.join(RAIZ, modelo)) and not os.path.exists(modelo):
        print(f"  nao achei {modelo}")
        return {}
    print(f"  modelo: {modelo}")
    print(f"  threads que o Python ve: {os.cpu_count()}   "
          f"OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS', '(padrao)')}")
    m = YOLO(modelo)
    img = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
    saida = {}
    print(f"\n  {'entrada':>8} {'mediana':>9} {'p95':>8} {'fps teorico':>12}")
    print("  " + "-" * 41)
    for t in TAMANHOS:
        try:
            for _ in range(AQUECE):
                m.predict(img, imgsz=t, verbose=False, classes=[0])
            tempos = []
            for _ in range(MEDE):
                a = time.perf_counter()
                m.predict(img, imgsz=t, verbose=False, classes=[0])
                tempos.append((time.perf_counter() - a) * 1000)
        except Exception as e:
            print(f"  {t:>6}px  falhou: {e}")
            continue
        tempos.sort()
        med = statistics.median(tempos)
        p95 = tempos[min(len(tempos) - 1, int(0.95 * (len(tempos) - 1)))]
        saida[t] = med
        print(f"  {t:>6}px {med:>8.1f}ms {p95:>7.1f}ms {1000 / med:>11.1f}")
    return saida


def _uma_bancada(modo):
    """Roda DENTRO de um processo novo: o modelo so aprende em quais nucleos
    pode rodar no momento em que e carregado. Imprime MEDIANA=<ms>."""
    import numpy as np
    from ultralytics import YOLO
    from aibox import nucleos
    if modo == "grandes":
        nucleos.prender_nos_grandes()
    t = int(os.environ.get("CAM_IMGSZ", "320"))
    m = YOLO(os.environ.get("MODELO", "yolo11n-pose.pt"))
    img = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
    for _ in range(AQUECE):
        m.predict(img, imgsz=t, verbose=False, classes=[0])
    tempos = []
    for _ in range(MEDE):
        a = time.perf_counter()
        m.predict(img, imgsz=t, verbose=False, classes=[0])
        tempos.append((time.perf_counter() - a) * 1000)
    print(f"MEDIANA={statistics.median(tempos):.2f}", flush=True)


def comparar_nucleos():
    """Todos os nucleos contra so os grandes, no tamanho que a caixa usa.

    Existe porque a QCS6490 tem nucleos de dois tamanhos e o ONNX Runtime
    divide o modelo igualmente entre todos — o que pode fazer os pequenos virem
    o gargalo. Pode. Por isso e medido, e nao ligado por palpite."""
    import subprocess
    from aibox import nucleos
    fq = nucleos.frequencias()
    grandes, pequenos = nucleos.grupos()
    if not fq:
        print("  nao consegui ler as frequencias em /sys; pulando")
        return None
    for n in sorted(fq):
        tipo = "grande" if n in grandes else ("pequeno" if n in pequenos else "")
        print(f"  nucleo {n}: {fq[n] / 1e6:.2f} GHz  {tipo}")
    if not grandes:
        print("  todos iguais: nao ha o que separar")
        return None

    res = {}
    for modo in ("todos", "grandes"):
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--_bancada", modo],
                           capture_output=True, text=True, cwd=RAIZ)
        linha = [x for x in r.stdout.splitlines() if x.startswith("MEDIANA=")]
        if not linha:
            print(f"  {modo}: falhou  {(r.stderr or '').strip()[-200:]}")
            return None
        res[modo] = float(linha[0].split("=")[1])
    t, g = res["todos"], res["grandes"]
    print(f"\n  todos os {len(fq)} nucleos : {t:6.1f} ms  ({1000 / t:4.1f}/s)")
    print(f"  so os {len(grandes)} grandes  : {g:6.1f} ms  ({1000 / g:4.1f}/s)")
    # 5% de folga: menos que isso e ruido de medida, e trocar configuracao por
    # ruido e o jeito mais facil de piorar sem perceber.
    if g < t * 0.95:
        print(f"  GANHA {100 * (1 - g / t):.0f}%. Ponha no .env:  NUCLEOS=grandes")
        print("  e confira na linha do --mostrar que os quadros/s subiram de verdade:")
        print("  esta bancada mede o modelo sozinho, sem a camera decodificando junto.")
    else:
        print("  NAO GANHA nesta caixa. Deixe como esta (sem NUCLEOS no .env).")
    return res


def main():
    carregar_env()
    p = argparse.ArgumentParser(description="quanto esta caixa aguenta")
    p.add_argument("--camera", action="store_true")
    p.add_argument("--modelo", action="store_true")
    p.add_argument("--nucleos", action="store_true")
    p.add_argument("--_bancada", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a._bancada:
        return _uma_bancada(a._bancada)
    tudo = not (a.camera or a.modelo or a.nucleos)

    taxa = None
    if tudo or a.camera:
        print("\n=== TETO DA CAMERA ===")
        taxa = teto_da_camera()
    modelo = {}
    if tudo or a.modelo:
        print("\n=== TETO DO MODELO ===")
        modelo = teto_do_modelo()

    if tudo or a.nucleos:
        print("\n=== NUCLEOS GRANDES x TODOS ===")
        comparar_nucleos()

    if modelo:
        print("\n=== LEITURA ===")
        # O orcamento do laco NAO e so a inferencia: sobra decodificar o video,
        # casar as trilhas e desenhar. Descontar 25% e a folga que a medicao na
        # caixa mostrou entre a latencia do modelo e a taxa real alcancada.
        melhor = min(modelo.values())
        real = 1000 / melhor * 0.75
        print(f"  no melhor tamanho, o modelo permitiria ~{real:.0f} quadros/s")
        if taxa:
            print(f"  a camera permite {taxa:.0f}/s")
            print(f"  QUEM MANDA: {'a camera' if taxa < real else 'o modelo'}")
        print("\n  para subir mais, em ordem de retorno:")
        print("   1. quantizar para INT8  ->  python3 aibox/quantizar.py")
        print("   2. baixar o tamanho de entrada (CAM_IMGSZ no .env)")
        print("   3. aumentar o FPS do substream no site da camera")


if __name__ == "__main__":
    raise SystemExit(main())
