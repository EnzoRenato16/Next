"""A caixa diz ao servidor que esta viva — e se esta enxergando.

POR QUE ISTO EXISTE. Sem batimento, se a caixa travasse, a camera caisse ou
alguem tampasse a lente, o painel ficava quieto. E quieto e o que o painel
mostra quando nada acontece: o sistema cego e o sistema tranquilo eram iguais
na tela. Agora a caixa bate a cada BATIDA_S segundos, e o SERVIDOR percebe
quando ela para (a caixa morta nao consegue avisar que morreu).

A batida diz tres coisas sobre a imagem:

    ok          a camera entrega quadro, e o quadro tem detalhe
    sem_imagem  faz SEM_IMAGEM_S que nao chega quadro (cabo, rede, camera)
    tampada     chega quadro, mas liso ha TAMPADA_S: lente coberta, virada
                para a parede, ou sala no escuro total

"TAMPADA" E MEDIDO, NAO ADIVINHADO. `detalhe` e o desvio-padrao do brilho numa
amostra de 1 a cada 8 pixels: uma sala tem moveis, bordas, luz e sombra (numero
alto); uma mao na lente e uma mancha so (numero baixo). O limiar vem do .env
(TAMPADA_LIMIAR) e o numero aparece na tela ao vivo e no painel — ajuste no
local, olhando o valor da sala de verdade, e nao com um chute daqui.

CUSTO. A conta roda UMA vez por segundo, sobre ~3.600 pixels: microssegundos,
dentro do laco, sem copia. O envio roda numa thread propria e nunca espera a
analise, nem a analise espera ele.

So biblioteca padrao e NumPy.
"""
import json
import os
import socket
import threading
import time

BATIDA_S = float(os.environ.get("BATIDA_S", "5"))
SEM_IMAGEM_S = float(os.environ.get("SEM_IMAGEM_S", "10"))
TAMPADA_S = float(os.environ.get("TAMPADA_S", "10"))
TAMPADA_LIMIAR = float(os.environ.get("TAMPADA_LIMIAR", "10"))


def detalhe(img):
    """Quanto o brilho varia na imagem. 0 = uma cor so."""
    amostra = img[::8, ::8]
    if amostra.ndim == 3:
        amostra = amostra.mean(axis=2)
    return float(amostra.std())


class Batimento:
    def __init__(self, base, local, caixa=None, post=None):
        self.base = base.rstrip("/")
        self.local = local
        self.caixa = (caixa or os.environ.get("CAIXA") or socket.gethostname())[:50]
        self._post_fn = post or _post
        self.ultimo_quadro = time.monotonic()   # conta a partir da abertura
        self.valor = None                       # ultimo `detalhe` medido
        self._liso_desde = None
        self._medido = 0.0
        self.fps = None
        self.pendentes = None
        self.batidas = 0
        self.falhas = 0
        self.ultimo_erro = None
        self._parar = threading.Event()
        self._t = threading.Thread(target=self._laco, name="batimento", daemon=True)
        self._t.start()

    # --------------------------------------------------- chamado pelo laco
    def quadro(self, img, agora=None):
        """Um quadro chegou. Mede o detalhe no maximo uma vez por segundo."""
        agora = time.monotonic() if agora is None else agora
        self.ultimo_quadro = agora
        if agora - self._medido < 1.0:
            return
        self._medido = agora
        self.valor = detalhe(img)
        if self.valor < TAMPADA_LIMIAR:
            if self._liso_desde is None:
                self._liso_desde = agora
        else:
            self._liso_desde = None

    def estado(self, agora=None):
        agora = time.monotonic() if agora is None else agora
        if agora - self.ultimo_quadro > SEM_IMAGEM_S:
            return "sem_imagem"
        if self._liso_desde is not None and agora - self._liso_desde >= TAMPADA_S:
            return "tampada"
        return "ok"

    def fechar(self):
        """Encerramento DE PROPOSITO: o servidor registra e nao toca sirene."""
        self._parar.set()
        self._t.join(timeout=1)
        try:
            self._post_fn(self.base + "/api/batimento", self._corpo("parada"), 3)
        except Exception:
            pass

    # ------------------------------------------------------------ por dentro
    def _corpo(self, estado):
        agora = time.monotonic()
        return dict(caixa=self.caixa, local=self.local, estado=estado,
                    intervalo_s=BATIDA_S,
                    detalhe=None if self.valor is None else round(self.valor, 1),
                    quadro_ha_s=round(agora - self.ultimo_quadro, 1),
                    fps=None if self.fps is None else round(self.fps, 1),
                    pendentes=self.pendentes)

    def _laco(self):
        anterior = "ok"
        while not self._parar.is_set():
            est = self.estado()
            if est != anterior:
                # Mudou: diz na tela da caixa tambem, nao so no painel.
                print(f"[aibox] imagem: {est}"
                      + (f" (detalhe {self.valor:.1f}, limiar {TAMPADA_LIMIAR:g})"
                         if est == "tampada" and self.valor is not None else ""),
                      flush=True)
                anterior = est
            try:
                codigo = self._post_fn(self.base + "/api/batimento",
                                       self._corpo(est), 3)
                if 200 <= codigo < 300:
                    self.batidas += 1
                else:
                    self.falhas += 1
                    self.ultimo_erro = f"HTTP {codigo}"
            except Exception as e:
                # Sem reenvio: batida velha nao vale nada, a proxima ja diz o
                # estado de agora. Quem conta o silencio e o servidor.
                self.falhas += 1
                self.ultimo_erro = str(e)
            self._parar.wait(BATIDA_S)


def _post(alvo, corpo, espera):
    import urllib.error
    import urllib.request
    pedido = urllib.request.Request(
        alvo, data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=espera) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
