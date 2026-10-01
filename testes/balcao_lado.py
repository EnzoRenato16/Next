"""O balcao de cadastro da caixa — roda pelo testes/balcao.mjs.

Uso: python3 testes/balcao_lado.py [base-do-servidor]
     python3 testes/balcao_lado.py --servir PORTA BASE   (para a tela, no .mjs)

O motor de verdade (YuNet + SFace) precisa de um rosto de verdade na frente da
camera, e isso nao se testa com codigo. O que se testa aqui e a cola: quando o
balcao colhe, quando espera, o que manda para o servidor, e quando desliga a
camera. Camera e motor sao falsos, e mandam o que o teste quiser.
"""
import json
import os
import sys
import time
import urllib.request

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox import balcao  # noqa: E402

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


class CameraFalsa:
    """Um quadro novo a cada leitura, ate ser fechada."""

    abertas = 0

    def __init__(self, abre=True):
        self.aberta = abre
        if abre:
            CameraFalsa.abertas += 1

    def isOpened(self):
        return self.aberta

    def read(self):
        if not self.aberta:
            return False, None
        time.sleep(0.005)
        return True, np.full((360, 640, 3), 90, np.uint8)

    def release(self):
        if self.aberta:
            CameraFalsa.abertas -= 1
        self.aberta = False


class MotorFalso:
    """Devolve quantos rostos o teste mandar, do tamanho que ele mandar."""

    def __init__(self):
        self.rostos = 1
        self.altura = 120          # pixels, num quadro de 360: 33%
        self.embeddings = 0

    def detect(self, img, full_res=False):
        linhas = [[200 + 150 * i, 80, 100, self.altura] + [0.0] * 10 + [0.95]
                  for i in range(self.rostos)]
        return np.array(linhas, dtype=np.float32).reshape(-1, 15)

    def embedding(self, img, linha):
        self.embeddings += 1
        return np.random.default_rng(self.embeddings).normal(size=128).astype(np.float32)


def esperar(cond, prazo=3.0):
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def balcao_de_teste(motor, mandados, porta=0, abre=True, **kw):
    return balcao.Balcao(
        "rtsp://falsa", "http://x", porta,
        motor=lambda: motor, abrir=lambda url: CameraFalsa(abre),
        mandar=lambda base, nome, vetores: mandados.append((nome, vetores))
        or {"nome": nome, "amostras": len(vetores), "tipo": "sface",
            "vence": "2027-10-01 00:00:00"},
        intervalo=0.05, desliga=kw.pop("desliga", 0.4), previa_fps=200, **kw)


def servir(porta, base):
    """O balcao de verdade, com camera e motor falsos, mandando para um
    servidor de verdade. E o que a tela do PC encontra no teste da tela."""
    motor = MotorFalso()
    b = balcao.Balcao("rtsp://falsa", base, porta, motor=lambda: motor,
                      abrir=lambda url: CameraFalsa(), intervalo=0.05,
                      previa_fps=30)
    print("pronto", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        b.fechar()


if len(sys.argv) > 1 and sys.argv[1] == "--servir":
    servir(int(sys.argv[2]), sys.argv[3])
    sys.exit(0)

print("== a camera so abre quando alguem pede ==")
m, mandados = MotorFalso(), []
b = balcao_de_teste(m, mandados)
time.sleep(0.2)
ok("ninguem pediu: camera fechada", CameraFalsa.abertas == 0
   and b.ver_estado()["fase"] == "desligado")
b.ligar()
ok("a tela pediu: camera aberta e imagem saindo",
   esperar(lambda: b.jpeg is not None) and CameraFalsa.abertas == 1)
ok("e a imagem e um JPEG", b.jpeg is not None and b.jpeg[:2] == b"\xff\xd8")
ok("um rosto perto: a dica manda escrever o nome",
   esperar(lambda: "Escreva o nome" in b.ver_estado()["mensagem"]),
   b.ver_estado()["mensagem"])
ok("ninguem olhando por DESLIGA_S: a camera fecha sozinha",
   esperar(lambda: CameraFalsa.abertas == 0 and b.ver_estado()["fase"] == "desligado"),
   b.ver_estado()["fase"])

print("\n== o cadastro ==")
codigo, _ = b.cadastrar("")
ok("nome vazio e recusado", codigo == 400)
codigo, _ = b.cadastrar("x" * 81)
ok("nome com mais de 80 letras e recusado", codigo == 400)
m.rostos = 2
codigo, _ = b.cadastrar("Enzo Renato")
ok("com nome: comeca a colher, e liga a camera sozinho",
   codigo == 200 and b.ver_estado()["fase"] == "colhendo")
codigo2, _ = b.cadastrar("Outra Pessoa")
ok("um cadastro por vez: o segundo pedido e recusado", codigo2 == 409)
time.sleep(0.3)
ok("DOIS rostos: espera, nao escolhe o maior",
   b.ver_estado()["amostras"] == 0 and "2 rostos" in b.ver_estado()["mensagem"],
   b.ver_estado()["mensagem"])
m.rostos, m.altura = 1, 30          # 30 de 360 = 8%
time.sleep(0.3)
ok("rosto pequeno demais: pede para chegar perto, nao colhe",
   b.ver_estado()["amostras"] == 0 and "Chegue mais perto" in b.ver_estado()["mensagem"],
   b.ver_estado()["mensagem"])
m.altura = 120
ok("um rosto perto: colhe as 6 e grava",
   esperar(lambda: b.ver_estado()["fase"] == "pronto"), b.ver_estado()["mensagem"])
ok("o servidor recebeu UM cadastro, com o nome certo",
   len(mandados) == 1 and mandados[0][0] == "Enzo Renato")
ok("com 6 amostras de 128 numeros",
   mandados and len(mandados[0][1]) == 6 and all(len(v) == 128 for v in mandados[0][1]))
ok("amostras espacadas no tempo, nao seis copias do mesmo instante",
   m.embeddings == 6, f"{m.embeddings} embeddings")
ok("e a tela fica sabendo", "cadastrado" in b.ver_estado()["mensagem"])

print("\n== quando da errado ==")
m2, mandados2 = MotorFalso(), []
b2 = balcao_de_teste(m2, mandados2)
b2._mandar = lambda base, nome, vetores: {"erro": "403 Quem pode: 127.0.0.1"}
b2.cadastrar("Fulano")
ok("servidor recusou: a tela le o motivo",
   esperar(lambda: b2.ver_estado()["fase"] == "erro")
   and "403" in b2.ver_estado()["mensagem"], b2.ver_estado()["mensagem"])
b2.fechar()

b3 = balcao_de_teste(MotorFalso(), [], abre=False)
b3.ligar()
ok("camera que nao abre: erro dito, com o conserto",
   esperar(lambda: b3.ver_estado()["fase"] == "erro")
   and "CAMERA_CADASTRO" in b3.ver_estado()["mensagem"], b3.ver_estado()["mensagem"])
b3.fechar()

def sem_modelo():
    raise FileNotFoundError("models")
b4 = balcao.Balcao("rtsp://falsa", "http://x", 0, motor=sem_modelo,
                   abrir=lambda url: CameraFalsa())
b4.ligar()
ok("sem os modelos de rosto: manda rodar pc modelos",
   esperar(lambda: b4.ver_estado()["fase"] == "erro")
   and "pc modelos" in b4.ver_estado()["mensagem"], b4.ver_estado()["mensagem"])
b4.fechar()
b.fechar()

print("\n== por HTTP, como a tela do PC fala ==")
porta = 8796
m5, mandados5 = MotorFalso(), []
b5 = balcao_de_teste(m5, mandados5, porta=porta, desliga=5)
B = f"http://127.0.0.1:{porta}"
r = urllib.request.urlopen(B + "/estado", timeout=3)
ok("/estado responde, e aceita pedido de outra maquina (CORS)",
   r.status == 200 and r.headers.get("Access-Control-Allow-Origin") == "*")
req = urllib.request.Request(B + "/cadastrar", method="OPTIONS")
r = urllib.request.urlopen(req, timeout=3)
ok("a pergunta previa do navegador (OPTIONS) e aceita",
   r.status == 204 and "POST" in (r.headers.get("Access-Control-Allow-Methods") or ""))
r = urllib.request.urlopen(B + "/video", timeout=3)
pedaco = r.read(4000)
ok("/video entrega MJPEG", b"--quadro" in pedaco and b"\xff\xd8" in pedaco,
   r.headers.get("Content-Type"))
r.close()
req = urllib.request.Request(B + "/cadastrar", data=json.dumps({"nome": "Via HTTP"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
r = urllib.request.urlopen(req, timeout=3)
ok("POST /cadastrar comeca a colher", json.loads(r.read())["fase"] == "colhendo")
ok("e grava", esperar(lambda: b5.ver_estado()["fase"] == "pronto"))
try:
    req = urllib.request.Request(B + "/cadastrar", data=b'{"nome": ""}',
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=3)
    recusou = False
except urllib.error.HTTPError as e:
    recusou = e.code == 400
ok("nome vazio por HTTP: 400", recusou)
b5.fechar()

if len(sys.argv) > 1:
    # De verdade, contra o servidor de teste: o cadastro chega como tipo sface.
    base = sys.argv[1]
    b6 = balcao.Balcao("rtsp://falsa", base, 0, motor=lambda: MotorFalso(),
                       abrir=lambda url: CameraFalsa(), intervalo=0.05, previa_fps=200)
    b6.cadastrar("Teste Balcao Caixa")
    ok("contra o servidor de verdade: gravou",
       esperar(lambda: b6.ver_estado()["fase"] == "pronto", 5), b6.ver_estado()["mensagem"])
    lista = json.loads(urllib.request.urlopen(base + "/api/cadastros", timeout=3).read())
    fichas = [c for c in lista["cadastros"] if c["nome"] == "Teste Balcao Caixa"]
    ok("e o servidor guardou como sface, o motor que a caixa le",
       fichas and fichas[0]["tipo"] == "sface", str(fichas))
    b6.fechar()

print("\nRESULTADO " + ("ok" if not falhas else f"{falhas} falha(s)"))
sys.exit(1 if falhas else 0)
