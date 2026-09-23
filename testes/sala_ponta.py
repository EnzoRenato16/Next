"""A sala.py INTEIRA, de ponta a ponta — roda pelo testes/sala-ponta.mjs.

Os testes das pecas provam cada peca. Este prova o LACO: a camera entrega, o
detector ve, a trilha guarda os pontos, a rede reconhece a queda, a fila entrega
com o corpo junto, o servidor grava — tudo com o codigo que vai para a caixa.

So a camera e o detector sao de mentira: a camera entrega quadros pretos no
RITMO do cenario (senao a taxa de quadros medida seria absurda e a rede nao
reconheceria nada), e o detector devolve os 17 pontos do mesmo tombo que o
testes/aibox.mjs ja prova que os dois lados reconhecem como queda.
"""
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

from aibox import sala  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
LOCAL = "sala-ponta-" + str(int(time.time()))
cen = json.load(open(os.path.join(RAIZ, "testes", "queda-cenario.json")))
quadros = cen["quadros"]
ALT = 360
LARG = round(ALT * cen["aspecto"])
preto = np.zeros((ALT, LARG, 3), np.uint8)
servido = {"i": -1}


class CameraFalsa:
    def __init__(self):
        self.t0 = None
        self.lidos = self.perdidos = 0
        self.espiar = None
        self.i = 0

    def isOpened(self):
        return True

    def read(self):
        if self.t0 is None:
            self.t0 = time.monotonic()
        if self.i >= len(quadros):
            time.sleep(0.01)
            return None, None          # acabou o cenario: "sem quadro novo"
        alvo = self.t0 + (quadros[self.i]["t"] - quadros[0]["t"]) / 1000
        espera = alvo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        servido["i"] = self.i
        self.i += 1
        self.lidos += 1
        if self.espiar:
            self.espiar(preto)
        return True, preto

    def release(self):
        pass


class OlhoFalso:
    def ver(self, img):
        return [(1, [tuple(p) for p in quadros[servido["i"]]["kp"]])]

    def fechar(self):
        pass


sala.abrir_camera = lambda fonte: CameraFalsa()
sala.olho_mod.abrir = lambda qual=None, modelo=None: OlhoFalso()

s = socket.socket(); s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]; s.close()
sys.argv = ["sala.py", "--camera", "falsa", "--servidor", BASE, "--local", LOCAL,
            "--segundos", "6", "--web", str(porta), "--fluido"]
os.environ["CALIBRACAO"] = "0"

# Um "navegador" olhando a tela ao vivo durante a rodada, para o pintor trabalhar.
estado = {}


def assistir():
    time.sleep(1.0)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/video", timeout=8) as r:
            fim = time.monotonic() + 3.5
            while time.monotonic() < fim:
                r.read(4096)
    except Exception:
        pass
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/estado", timeout=3) as r:
            estado.update(json.loads(r.read()))
    except Exception:
        pass


threading.Thread(target=assistir, daemon=True).start()
codigo = sala.main()
print(json.dumps({"saida": codigo, "local": LOCAL, "estado": estado}))
