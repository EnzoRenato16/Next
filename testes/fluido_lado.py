"""Video fluido (--fluido) — roda pelo testes/fluido.mjs.

Uma camera de mentira a 30 quadros/s e uma analise de mentira a 8/s, que e o
que a AIBOX faz. Cobra: a tela anda no ritmo da camera (com teto), a analise
nao paga o desenho, e sem ninguem assistindo o custo e zero.
"""
import os
import socket
import sys
import threading
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from aibox import trilhas, vivo  # noqa: E402

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


def porta_livre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


janela = vivo.Vivo(porta_livre())
pintor = vivo.Pintor(janela, cv2, teto=25.0)

# Uma pessoa de verdade no rebanho, para o desenho ter o que desenhar.
reb = trilhas.Rebanho()
kp = [[0.5, 0.2 + i * 0.04, 0.9] for i in range(17)]
reb.quadro([(1, kp)], 16 / 9, 0.0)

parar = threading.Event()
quadro = np.zeros((360, 640, 3), np.uint8)
chamadas = []


def camera():
    while not parar.is_set():
        t0 = time.perf_counter()
        pintor.novo_quadro(quadro)
        chamadas.append((time.perf_counter() - t0) * 1000)
        time.sleep(1 / 30)


def analise():
    while not parar.is_set():
        pintor.trilhas_da_analise(list(reb.trilhas.values()))
        time.sleep(1 / 8)


threading.Thread(target=camera, daemon=True).start()
threading.Thread(target=analise, daemon=True).start()

# ---- 1. NINGUEM ASSISTINDO: CUSTO ZERO -------------------------------------
janela.clientes = 0
time.sleep(1.0)
ok("sem ninguem assistindo, nenhum JPEG e feito", janela.jpeg is None)

# ---- 2. ALGUEM ASSISTINDO: O VIDEO ANDA NO RITMO DA CAMERA -----------------
janela.clientes = 1
feitos, ultimo = 0, None
fim = time.monotonic() + 3.0
while time.monotonic() < fim:
    j = janela.jpeg
    if j is not None and j is not ultimo:
        feitos += 1
        ultimo = j
    time.sleep(0.003)
fps = feitos / 3.0
ok("com alguem assistindo, a tela anda bem acima dos 8 da analise", fps > 15,
   f"{fps:.1f} quadros/s")
ok("e respeita o teto de 25/s — sobra de tempo vira folga para a analise",
   fps <= 26.5, f"{fps:.1f} quadros/s")
ok("o ritmo do video aparece nos numeros da tela",
   janela.estado.get("video", 0) > 15, f"{janela.estado.get('video', 0):.1f}")

img = cv2.imdecode(np.frombuffer(ultimo, np.uint8), cv2.IMREAD_COLOR)
ok("o quadro sai com o esqueleto desenhado por cima", img is not None and img.sum() > 0)

# ---- 3. A CAMERA NAO ESPERA O PINTOR ---------------------------------------
pior = max(chamadas[-60:])
ok("entregar o quadro ao pintor nao atrasa a leitura da camera", pior < 2.0,
   f"pior {pior:.3f} ms")

parar.set()
pintor.fechar()
janela.fechar()
print(f"\n{'FALHOU' if falhas else 'o video fluido passou'}")
sys.exit(1 if falhas else 0)
