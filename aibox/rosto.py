"""Reconhecimento facial na AIBOX, sem tirar quadros da analise de queda.

O MOTOR NAO E NOVO. Ele mora em `daten/` (EduVision) desde antes: YuNet acha o
rosto e cinco pontos, SFace alinha por esses pontos e devolve 128 numeros. Sao
modelos pequenos em ONNX, feitos para CPU ARM — o AIBOX nao tem GPU CUDA. Este
arquivo e a cola entre aquele motor e o laco da sala.

DUAS DECISOES QUE VALEM A PENA ENTENDER:

1. RODA EM OUTRA THREAD, e o laco principal nunca espera por ele. Rosto custa
   dezenas de milissegundos mais uma ida ao servidor pela rede; pago dentro do
   laco, isso seria subtraido direto dos 8,7 quadros por segundo que a deteccao
   de queda tem. Aqui o laco entrega um quadro e segue; quando a resposta chega,
   o nome aparece.

2. NAO OLHA TODO QUADRO. Uma pessoa nao troca de cara entre um quadro e outro:
   olhar a cada poucos segundos da o mesmo resultado por uma fracao do custo.
   Quem ja tem nome e reconferido ainda mais devagar.

O QUE ELE NAO FAZ: comparar. Os 128 numeros vao para o servidor, que compara
contra o cadastro girado pela chave e devolve um nome. A caixa nunca tem o
cadastro na mao — se alguem levar a caixa embora, nao leva rosto de ninguem.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cada quanto tempo olhar um rosto novo, e cada quanto reconferir quem ja tem
# nome. Reconferir existe porque duas pessoas que se cruzam podem trocar de
# trilha, e um nome errado que nunca se corrige e pior que nenhum nome.
ESPERA = float(os.environ.get("ROSTO_ESPERA", "2.0"))
RECONFERIR = float(os.environ.get("ROSTO_RECONFERIR", "10.0"))


class Rosto:
    """Nomeia as trilhas. Falha em silencio para nao derrubar a analise."""

    def __init__(self, base, espera=ESPERA):
        self.base = base.rstrip("/")
        self.espera = espera
        self.nomes = {}           # id da trilha -> (nome, quando)
        self.vistos = 0
        self.reconhecidos = 0
        self.erro = None

        sys.path.insert(0, RAIZ)
        from daten.app.recognizer import FaceEngine
        self.motor = FaceEngine()

        self._pendente = None     # (imagem, [(id, x, y, w, h)])
        self._trava = threading.Lock()
        self.vivo = True
        self._t = threading.Thread(target=self._laco, daemon=True)
        self._t.start()

    # -- lado do laco principal: entrega e segue ----------------------------
    def ver(self, img, trilhas):
        """Oferece um quadro. Se o motor ainda esta ocupado, o quadro e
        descartado — trabalhar no quadro de tres segundos atras nao ajuda."""
        with self._trava:
            if self._pendente is not None:
                return
            # A caixa da trilha vem NORMALIZADA (0 a 1), porque e assim que a
            # geometria do projeto inteiro trabalha — a mesma conta vale para
            # qualquer resolucao. O YuNet devolve pixel, entao a conversao
            # acontece aqui, uma vez, e nao dentro do laco de comparacao.
            alt, larg = img.shape[:2]
            caixas = []
            for t in trilhas:
                c = getattr(t, "caixa", None)
                if not c:
                    continue
                caixas.append((t.id, c[0] * larg, c[1] * alt,
                               (c[2] - c[0]) * larg, (c[3] - c[1]) * alt))
            self._pendente = (img.copy(), caixas)

    def nome_de(self, ident):
        n = self.nomes.get(ident)
        return n[0] if n else None

    def fechar(self):
        self.vivo = False

    # -- lado da thread -----------------------------------------------------
    def _laco(self):
        proximo = 0.0
        while self.vivo:
            if time.monotonic() < proximo:
                time.sleep(0.05)
                continue
            with self._trava:
                tarefa, self._pendente = self._pendente, None
            if tarefa is None:
                time.sleep(0.05)
                continue
            proximo = time.monotonic() + self.espera
            try:
                self._trabalhar(*tarefa)
            except Exception as e:
                self.erro = str(e)

    def _trabalhar(self, img, caixas):
        linhas = self.motor.detect(img)
        if len(linhas) == 0:
            return
        agora = time.monotonic()
        for linha in linhas:
            x, y, w, h = (float(linha[0]), float(linha[1]),
                          float(linha[2]), float(linha[3]))
            cx, cy = x + w / 2.0, y + h / 2.0

            # EM QUAL CORPO ESTE ROSTO ESTA? O menor que contem o centro do
            # rosto, para o nome nao grudar em quem esta atras. Mesma regra do
            # navegador, de proposito: duas respostas diferentes para a mesma
            # cena seriam impossiveis de explicar na banca.
            alvo, area = None, float("inf")
            for ident, bx, by, bw, bh in caixas:
                if cx < bx or cx > bx + bw or cy < by or cy > by + bh:
                    continue
                if bw * bh < area:
                    alvo, area = ident, bw * bh
            if alvo is None:
                continue

            # Quem ja tem nome so e reconferido de vez em quando.
            tinha = self.nomes.get(alvo)
            if tinha and agora - tinha[1] < RECONFERIR:
                continue

            self.vistos += 1
            vetor = self.motor.embedding(img, linha)
            nome = self._perguntar([float(v) for v in vetor])
            if nome:
                if not tinha or tinha[0] != nome:
                    self.reconhecidos += 1
                self.nomes[alvo] = (nome, agora)

    def _perguntar(self, vetor):
        """Quem compara e o servidor. A caixa nunca tem o cadastro na mao."""
        pedido = urllib.request.Request(
            f"{self.base}/api/reconhecer",
            data=json.dumps({"descritor": vetor, "tipo": "sface"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(pedido, timeout=4) as r:
                return json.loads(r.read().decode("utf-8")).get("nome")
        except urllib.error.HTTPError as e:
            self.erro = f"servidor respondeu {e.code}"
        except Exception as e:
            self.erro = str(e)
        return None
