"""Entrega dos alertas da AIBOX ao servidor, sem nunca travar a analise.

O PROBLEMA QUE ISTO RESOLVE. O envio morava DENTRO do laco da analise: cada
alerta esperava ate 4 s pela resposta do PC, e cada lote de calibracao ate 6 s,
a cada 15 s. Com o PC fora do ar — servidor reiniciando, o PC no meio da danca
do DHCP para o `git pull`, o firewall do Windows descartando pacote calado — a
caixa ficava PARADA esperando, sem olhar a camera. E o alerta que nao chegava
era contado e jogado fora.

AGORA: o laco entrega o alerta numa fila e segue no mesmo instante. Uma thread
separada envia, e se o servidor nao responde, GUARDA e tenta de novo, com espera
crescente. Nenhum alerta se perde porque a rede piscou.

O RISCO QUE ISSO CRIA, E COMO ELE E FECHADO. Reenviar pode duplicar: o servidor
grava, a resposta se perde no caminho, a caixa acha que falhou e manda de novo.
Na cadeia de hash isso seria uma queda que nao aconteceu — e linha de cadeia nao
se apaga. Por isso cada alerta nasce com uma CHAVE unica, e o servidor que ja viu
a chave devolve o evento original em vez de gravar outro.

O HORARIO. O servidor carimba o momento em que o alerta CHEGOU. Um alerta que
esperou tres minutos na fila levaria o horario errado. A caixa manda junto ha
quantos ms o fato aconteceu, medido no relogio DELA — um intervalo, e nao uma
hora, porque a caixa e o PC nao tem o mesmo relogio, e subtrair um do outro faz
a diferenca entre os relogios parecer atraso.

So biblioteca padrao: isto tem que funcionar justamente quando falta alguma
coisa instalada.
"""
import collections
import json
import threading
import time
import uuid

# Espera entre tentativas: comeca curta (um soluco de rede se resolve em 1 s) e
# dobra ate o teto, para um servidor fora do ar nao levar uma requisicao por
# segundo durante a aula inteira.
ESPERA_INICIAL = 1.0
ESPERA_MAX = 30.0
# Teto da fila. Quinhentos alertas represados e muito mais do que uma aula
# produz; passando disso, o mais velho sai e a conta dos perdidos sobe — memoria
# de uma caixa nao e infinita.
FILA_MAX = 500


class Fala:
    """Fala com o servidor. O laco entrega e segue; esta thread e quem espera."""

    def __init__(self, base, camera, post=None):
        self.base = base.rstrip("/")
        self.camera = camera
        self._post_fn = post or self._post_padrao
        try:
            import requests
            self.req = requests
        except ImportError:
            # `requests` e o caminho bom, mas NAO E GARANTIDO no venv da caixa.
            self.req = None

        self.enviados = 0       # chegaram ao servidor
        self.atrasados = 0      # chegaram, mas depois de pelo menos uma falha
        self.repetidos = 0      # o servidor ja tinha: reenvio que nao duplicou
        self.falhas = 0         # recusados de vez, ou descartados por fila cheia
        self.calib_recusada = False
        self.ultimo_ms = None   # do quadro ao registro, no ultimo alerta
        self.ultimo_erro = None

        self._fila = collections.deque()
        self._trava = threading.Lock()
        self._acorda = threading.Event()
        self._aberta = True
        self._t = threading.Thread(target=self._laco, name="entrega", daemon=True)
        self._t.start()

    # ------------------------------------------------------------------ laco
    @property
    def pendentes(self):
        with self._trava:
            return sum(1 for i in self._fila if i["tipo"] == "evento")

    def evento(self, tipo, corpo, quem=None, poses=None, t_quadro=None):
        """Entrega um alerta. Volta na hora; quem espera a rede e a thread."""
        agora = time.monotonic()
        dados = dict(aluno_id=(quem or f"corpo-{corpo}")[:50], tipo_evento=tipo,
                     localizacao=self.camera, chave=uuid.uuid4().hex)
        if poses:
            dados["poses"] = poses
        self._por(dict(tipo="evento", rota="/api/evento", dados=dados,
                       criado=agora, t_quadro=t_quadro or agora, tentativas=0))
        return True

    def calibracao(self, amostras):
        """Lote de medicao. Descartavel: se o servidor nao responde, NAO fica
        na fila atrapalhando os alertas — perder um lote de calibracao nao
        custa nada que importe."""
        if self.calib_recusada or not amostras:
            return
        self._por(dict(tipo="calib", rota="/api/calibracao",
                       dados=dict(camera=self.camera, amostras=amostras),
                       criado=time.monotonic(), t_quadro=None, tentativas=0))

    def fechar(self, prazo=5.0):
        """Tenta esvaziar a fila antes de sair. Devolve quantos alertas ficaram
        sem entregar — e isso vai para a tela, nao para o silencio."""
        self._aberta = False
        self._acorda.set()
        self._t.join(timeout=prazo)
        return self.pendentes

    # ------------------------------------------------------------- por dentro
    def _por(self, item):
        with self._trava:
            if len(self._fila) >= FILA_MAX:
                velho = self._fila.popleft()
                if velho["tipo"] == "evento":
                    self.falhas += 1
                    self.ultimo_erro = "fila cheia: o alerta mais velho foi descartado"
            self._fila.append(item)
        self._acorda.set()

    def _laco(self):
        espera = ESPERA_INICIAL
        while True:
            with self._trava:
                item = self._fila[0] if self._fila else None
            if item is None:
                if not self._aberta:
                    return
                self._acorda.wait(timeout=1.0)
                self._acorda.clear()
                continue

            corpo = dict(item["dados"])
            if item["tipo"] == "evento":
                # Medido NA HORA DE MANDAR, e nao na hora de enfileirar: e isso
                # que faz um alerta represado dizer a verdade sobre quando foi.
                corpo["ocorreu_ha_ms"] = int((time.monotonic() - item["criado"]) * 1000)
            try:
                codigo, resposta = self._post_fn(self.base + item["rota"], corpo, 6)
            except Exception as e:           # rede fora, recusa, prazo
                codigo, resposta = 0, None
                self.ultimo_erro = str(e)

            if 200 <= codigo < 300:
                self._tirar(item)
                espera = ESPERA_INICIAL
                if item["tipo"] == "evento":
                    self.enviados += 1
                    self.ultimo_ms = (time.monotonic() - item["t_quadro"]) * 1000
                    if isinstance(resposta, dict) and resposta.get("repetido"):
                        self.repetidos += 1
                    if item["tentativas"]:
                        self.atrasados += 1
                        print(f"[aibox] alerta entregue depois de "
                              f"{item['tentativas']} tentativa(s), "
                              f"{corpo['ocorreu_ha_ms'] / 1000:.0f} s atrasado",
                              flush=True)
                continue

            if 400 <= codigo < 500:
                # RECUSA NAO SE REPETE. Mandar de novo o que o servidor disse que
                # nao aceita so gasta rede — e prende a fila atras dele.
                self._tirar(item)
                if item["tipo"] == "calib" and codigo == 403:
                    self.calib_recusada = True
                    print("[aibox] o servidor esta com CALIBRACAO=0; parei de medir",
                          flush=True)
                elif item["tipo"] == "evento":
                    self.falhas += 1
                    self.ultimo_erro = f"servidor recusou ({codigo}): {str(resposta)[:120]}"
                    print(f"[aibox] alerta RECUSADO pelo servidor ({codigo}): "
                          f"{str(resposta)[:120]}", flush=True)
                continue

            # Rede fora ou servidor com defeito (5xx): o alerta FICA.
            if item["tipo"] == "calib":
                self._tirar(item)
                continue
            item["tentativas"] += 1
            if item["tentativas"] == 1:
                print(f"[aibox] servidor nao respondeu; o alerta ficou guardado "
                      f"e sera reenviado ({self.ultimo_erro or codigo})", flush=True)
            if not self._aberta and item["tentativas"] >= 2:
                # Encerrando: duas tentativas e chega. O que sobrar e contado.
                return
            self._acorda.wait(timeout=espera)
            self._acorda.clear()
            espera = min(espera * 2, ESPERA_MAX)

    def _tirar(self, item):
        with self._trava:
            if self._fila and self._fila[0] is item:
                self._fila.popleft()

    def _post_padrao(self, alvo, corpo, espera):
        """Devolve (codigo, corpo da resposta). 0 = nem falou com o servidor."""
        if self.req is not None:
            r = self.req.post(alvo, timeout=espera, json=corpo)
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, r.text
        import urllib.error
        import urllib.request
        pedido = urllib.request.Request(
            alvo, data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(pedido, timeout=espera) as r:
                bruto = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(bruto)
                except ValueError:
                    return r.status, bruto
        except urllib.error.HTTPError as e:
            # urllib LEVANTA em 4xx/5xx; requests devolve o codigo. Sem isto os
            # dois caminhos se comportariam diferente.
            return e.code, e.read().decode("utf-8", "replace")
