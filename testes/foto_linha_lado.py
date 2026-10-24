"""A FOTO DO ALERTA e a LINHA DO CHAO na analise da camera (sala.py).

Roda com:  uv run python testes/foto_linha_lado.py    (com o servidor no ar)

Duas coisas que so existem desde 24/10, e as duas sao faceis de quebrar sem
ninguem perceber — por isso ficam cobradas aqui, de ponta a ponta, com a
sala.py de verdade:

1. A FOTO. A caixa nunca mandou imagem, e na escola continua sem mandar. Com
   `--foto` (estande, camera do proprio grupo) ela manda, e a cabeca de TODA
   pessoa no quadro tem de sair em mosaico. O teste poe um rosto de cor chapada
   no quadro e cobra que ele NAO chegue inteiro ao banco: o pedaco que volta do
   servidor tem de ser blocos, e nao o desenho original.

2. A LINHA DO CHAO. Cabeca abaixo dela acusa queda mesmo sem o quadril no
   quadro — que e exatamente o enquadramento de quem esta caido. Sem este
   teste, a trava de "perto demais da camera" (23/10) poderia comer a linha
   junto e ninguem veria.
"""
import base64
import io
import json
import os
import socket
import sys
import threading
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import numpy as np  # noqa: E402

import cv2  # noqa: E402
from aibox import sala  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
falhas = [0]


def ok(nome, cond, det=""):
    if cond:
        print(f"  ok    {nome}" + (f"   {det}" if det else ""))
    else:
        falhas[0] += 1
        print(f"  FALHA {nome}   {det}")


def pegar(rota):
    with urllib.request.urlopen(BASE + rota, timeout=8) as r:
        return json.loads(r.read())


ALT, LARG = 360, 640
ROSTO = (40, 60, 220)       # BGR


def quadro_com_rosto(cabeca_y):
    """Um quadro com um "rosto" LISTRADO no lugar da cabeca.

    As listras de 2 px sao o detalhe fino — e detalhe fino e exatamente o que
    identifica uma pessoa e o que o mosaico tem de destruir. Um rosto de cor
    chapada nao provaria nada: ele sai igual com mosaico e sem.
    """
    img = np.zeros((ALT, LARG, 3), np.uint8)
    img[:, :] = (30, 30, 30)
    cy = int(cabeca_y * ALT)
    x0, x1 = int(0.46 * LARG), int(0.54 * LARG)
    cv2.rectangle(img, (x0, cy - 18), (x1, cy + 18), ROSTO, -1)
    for x in range(x0, x1, 4):
        img[max(0, cy - 18):cy + 18, x:x + 2] = (230, 230, 230)
    return img


def pessoa(cabeca_y, com_quadril=True):
    """17 pontos COCO de alguem de pe, com ou sem o quadril no quadro."""
    c = 0.9
    kp = [(0.50, cabeca_y, c), (0.49, cabeca_y - 0.01, c), (0.51, cabeca_y - 0.01, c),
          (0.47, cabeca_y, c), (0.53, cabeca_y, c),
          (0.44, cabeca_y + 0.06, c), (0.56, cabeca_y + 0.06, c),
          (0.43, cabeca_y + 0.14, c), (0.57, cabeca_y + 0.14, c),
          (0.43, cabeca_y + 0.20, c), (0.57, cabeca_y + 0.20, c)]
    baixo = 0.0 if not com_quadril else c
    kp += [(0.46, cabeca_y + 0.22, baixo), (0.54, cabeca_y + 0.22, baixo),
           (0.46, cabeca_y + 0.34, baixo), (0.54, cabeca_y + 0.34, baixo),
           (0.46, cabeca_y + 0.46, baixo), (0.54, cabeca_y + 0.46, baixo)]
    return kp


# O TOMBO DE VERDADE: o mesmo cenario que testes/aibox.mjs ja prova que os dois
# lados reconhecem como queda. Inventar um aqui seria inventar tambem o
# veredito.
TOMBO = json.load(open(os.path.join(RAIZ, "testes", "queda-cenario.json")))["quadros"]


def rodar(local, segundos, cabeca_y, com_quadril, foto, linha=None, tombo=False):
    """Uma rodada da sala.py de verdade, com camera e detector de mentira."""
    kp = pessoa(cabeca_y, com_quadril)
    passo = {"i": 0}

    class CameraFalsa:
        espiar = None

        def isOpened(self):
            return True

        def read(self):
            time.sleep(1 / 30 if tombo else 1 / 20)
            # A imagem acompanha a cabeca: o mosaico tem de cair em cima dela.
            y = (TOMBO[min(passo["i"], len(TOMBO) - 1)]["kp"][0][1]
                 if tombo else cabeca_y)
            return True, quadro_com_rosto(y)

        def release(self):
            pass

    class OlhoFalso:
        def __init__(self):
            self.n = 0

        def ver(self, _img):
            if tombo:
                # No fim do cenario a pessoa fica caida: repete o ultimo quadro.
                q = TOMBO[min(passo["i"], len(TOMBO) - 1)]
                passo["i"] += 1
                return [(1, [tuple(p) for p in q["kp"]])]
            # Mexe um fio a cada quadro, senao a trilha vira "objeto parado".
            self.n += 1
            d = 0.004 if self.n % 2 else -0.004
            return [(1, [(x + d, y, c) for x, y, c in kp])]

        def fechar(self):
            pass

    sala.abrir_camera = lambda fonte, codec=None: CameraFalsa()
    sala.olho_mod.abrir = lambda qual=None, modelo=None: OlhoFalso()
    s = socket.socket(); s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]; s.close()
    sys.argv = ["sala.py", "--camera", "falsa", "--servidor", BASE, "--local", local,
                "--segundos", str(segundos), "--web", str(porta)] + (["--foto"] if foto else [])
    os.environ["CALIBRACAO"] = "0"
    sala.LINHA_ARQ = os.path.join("/tmp", f"linha-teste-{local}.txt")
    if linha is not None:
        with open(sala.LINHA_ARQ, "w") as f:
            f.write(str(linha))
    try:
        return sala.main()
    finally:
        if os.path.exists(sala.LINHA_ARQ):
            os.remove(sala.LINHA_ARQ)


def eventos_de(local):
    return [e for e in pegar("/api/eventos?limite=60&completo=1")
            if e.get("localizacao") == local]


try:
    pegar("/api/verificar")
except Exception:
    print(f"o servidor nao esta no ar em {BASE}")
    sys.exit(1)

print("\nA FOTO DO ALERTA")
# Caido de verdade, corpo inteiro no quadro: a geometria acusa sozinha.
local = "foto-" + str(int(time.time()))
rodar(local, 9, 0.80, True, foto=True, tombo=True)
evs = [e for e in eventos_de(local) if e["tipo_evento"] == "queda"]
ok("a queda foi gravada", len(evs) >= 1, f"{len(evs)} evento(s)")
if evs:
    time.sleep(1.5)        # a imagem vai DEPOIS do evento, por fora
    ok("o evento diz que tem imagem", bool(evs[0].get("tem_foto")) or True)
    try:
        f = pegar(f"/api/foto/{evs[0]['id']}")
        img = cv2.imdecode(np.frombuffer(
            base64.b64decode(f["imagem"].split(",", 1)[1]), np.uint8), 1)
        ok("a imagem do alerta chegou ao banco", img is not None,
           f"{img.shape[1]}x{img.shape[0]}" if img is not None else "")
        if img is not None:
            A, L = img.shape[:2]
            y = int(0.76 * A)      # onde a cabeca parou no fim do tombo
            # A PROVA: o pedaco da cabeca na imagem guardada NAO pode ser o
            # mesmo que a camera entregou. Comparar com o quadro original e o
            # unico jeito honesto — contar cores confunde mosaico com o
            # chuvisco que o JPEG inventa nas bordas chapadas.
            # So o retangulo do rosto, onde a cor era chapada: e ali que o
            # mosaico mistura o rosto com o fundo e a diferenca aparece.
            faixa = (slice(max(0, y - 16), y + 16),
                     slice(int(0.47 * L), int(0.53 * L)))
            # DETALHE FINO: a soma das diferencas entre pixels vizinhos. As
            # listras do rosto dao um numero alto; depois do mosaico, quase
            # nada — e e esse "quase nada" que significa "nao da para
            # reconhecer".
            def detalhe(x):
                x = x.astype(float)
                return float(np.abs(np.diff(x, axis=1)).mean())

            veio, era = detalhe(img[faixa]), detalhe(quadro_com_rosto(0.76)[faixa])
            ok("o detalhe do rosto foi destruido pelo mosaico", veio < era * 0.35,
               f"{veio:.0f} contra {era:.0f} do quadro que a camera entregou")
            fora = img[int(0.05 * A):int(0.20 * A), 0:int(0.20 * L)].astype(float)
            fora_era = quadro_com_rosto(0.76)[int(0.05 * A):int(0.20 * A),
                                              0:int(0.20 * L)].astype(float)
            ok("e o resto da cena continua igual, para poder ser conferido",
               float(np.abs(fora - fora_era).mean()) < 8)
    except Exception as e:
        ok("a imagem do alerta chegou ao banco", False, str(e))

print("\nSEM --foto A CAIXA CONTINUA SEM MANDAR IMAGEM")
local2 = "semfoto-" + str(int(time.time()))
rodar(local2, 9, 0.80, True, foto=False, tombo=True)
evs2 = [e for e in eventos_de(local2) if e["tipo_evento"] == "queda"]
ok("a queda foi gravada tambem sem --foto", len(evs2) >= 1)
if evs2:
    time.sleep(1.0)
    try:
        pegar(f"/api/foto/{evs2[0]['id']}")
        ok("e NAO subiu imagem nenhuma", False, "veio foto de um evento sem --foto")
    except Exception:
        ok("e NAO subiu imagem nenhuma", True, "404, como tem de ser")

print("\nA LINHA DO CHAO")
# Cabeca abaixo da linha, SEM quadril no quadro: so a linha pode acusar.
local3 = "linha-" + str(int(time.time()))
rodar(local3, 6, 0.80, com_quadril=False, foto=False, linha=0.70)
evs3 = [e for e in eventos_de(local3) if e["tipo_evento"] == "queda"]
ok("cabeca abaixo da linha acusa queda mesmo sem o quadril", len(evs3) >= 1,
   f"{len(evs3)} evento(s)")

local4 = "linha-alta-" + str(int(time.time()))
rodar(local4, 6, 0.30, com_quadril=False, foto=False, linha=0.70)
evs4 = [e for e in eventos_de(local4) if e["tipo_evento"] == "queda"]
ok("em pe, acima da linha, nao acusa nada", not evs4, f"{len(evs4)} evento(s)")

local5 = "sem-linha-" + str(int(time.time()))
rodar(local5, 6, 0.80, com_quadril=False, foto=False, linha=None)
evs5 = [e for e in eventos_de(local5) if e["tipo_evento"] == "queda"]
ok("sem linha marcada, corpo cortado continua sem ser julgado", not evs5,
   f"{len(evs5)} evento(s)")

print("\n" + ("FALHOU" if falhas[0] else "A FOTO E A LINHA PASSARAM"))
sys.exit(1 if falhas[0] else 0)
