"""Modo arena: quem esta autorizado e quem nao esta, tudo dentro da AIBOX.

  bash aibox/arena.sh                       (o jeito do dia: confere e roda)
  $P aibox/arena.py --camera rtsp://...     (direto)
  $P aibox/arena.py --camera teste.mp4      (ensaio com video gravado)

O QUE A ARENA DO NEXT COBRA (guia oficial, 24/10/2026): em ate cinco minutos,
com o setup incluido, reconhecer as pessoas cadastradas e apontar as duas que
nao sao, em qualquer ordem e posicao, sem operador escolhendo resultado, e no
fim mostrar quantos autorizados foram identificados, quantos alertas de
desconhecido houve, como estao as cameras e a latencia. O notebook so pode ser
terminal e tela; o processamento e aqui.

POR ISSO ESTE MODO E SO ROSTO. Sem o YOLO de pose, que a sala usa para queda,
a CPU inteira fica para o rosto em resolucao cheia, que e o que decide a prova
(rosto pequeno nao se reconhece, e nenhum modelo recupera pixel que nao
existe). A analise de queda continua sendo o sala.py, que e o que vai para o
estande.

COMO DECIDE, e por que nao num quadro so:

1. YuNet acha os rostos; um rastreador simples cola cada rosto no rosto do
   quadro anterior (mesma pessoa andando).
2. So rosto BOM vira leitura: grande o bastante, de pe, quase de frente e com
   nota alta do detector. Rosto de lado nao e prova de nada.
3. Cada leitura compara os 128 numeros do SFace com a galeria inteira.
4. A trilha so vira AUTORIZADO depois de MINIMO leituras com media acima do
   LIMIAR, folga sobre o segundo colocado e a maioria dos votos no mesmo nome.
   So vira DESCONHECIDO depois de MINIMO_DESC leituras com a media LONGE de
   todo mundo. No meio disso fica ANALISANDO, e a tela diz isso.
5. O mesmo desconhecido que sai e volta (trilha nova) nao vira um segundo
   alerta: o rosto dele e comparado com os desconhecidos ja vistos.

O erro mais caro e chamar de autorizado quem nao e (o "meliante" da prova).
Por isso autorizado exige folga e votos, e na duvida a trilha fica analisando.
"""
import argparse
import json
import os
import signal
import sys
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox import galeria  # noqa: E402


def _num(nome, padrao):
    return float(os.environ.get(nome, padrao))


# Limiares padrao de cada motor (cosseno, MAIOR = mais parecido). Cada motor
# tem a sua escala, e por isso a sua variavel no .env: ARENA_LIMIAR vale so
# para o SFace, ARENA_LIMIAR_ARCFACE so para o ArcFace. Um limiar calibrado
# num motor e errado no outro, e trocar de galeria nao pode carregar junto.
#   sface: 0,363 e o valor da OpenCV para rosto bom. No laboratorio (20/10) um
#     estranho chegou a 0,40 contra a galeria do grupo: calibre (0,45 / 0,38
#     separou o Enzo).
#   arcface: o mesmo estranho chegou a 0,24; no LFW, o estranho mais parecido
#     de 2.800 deu 0,34 e o dono no pior momento (5%), 0,36.
PADROES = {"sface": ("0.36", "0.26"), "arcface": ("0.34", "0.26")}
# Quanto a media de uma trilha desconhecida precisa lembrar um desconhecido ja
# visto para ser a MESMA pessoa voltando. No LFW o ArcFace da 0,61 ou mais para
# a mesma pessoa e no maximo 0,32 para pessoas diferentes; mas na camera HAIZ
# (20/10) tres estranhos viraram UM alerta com 0,45: do alto, com a mesma luz e
# o mesmo angulo, rostos diferentes ficam mais parecidos. ARENA_MESMO_DESC vale
# so para o SFace; ARENA_MESMO_DESC_ARCFACE so para o ArcFace.
MESMO_PADRAO = {"sface": "0.45", "arcface": "0.60"}
MOTOR = "sface"


def configurar(motor="sface"):
    """Le os limiares do ambiente. Roda no import e DE NOVO no main, depois do
    carregar_env e de saber o motor da galeria: sem a segunda vez, o
    ARENA_LIMIAR escrito no .env da caixa era ignorado calado, e a calibracao
    do laboratorio nao valia nada."""
    global LIMIAR, LIMIAR_BAIXO, MARGEM, MINIMO, MINIMO_DESC, MAXIMO
    global MESMO_DESCONHECIDO, ROSTO_MIN, NOTA_MIN, FRENTE, TOPK, MOTOR
    MOTOR = motor
    sufixo = "" if motor == "sface" else "_" + motor.upper()
    alto, baixo = PADROES[motor]
    LIMIAR = _num("ARENA_LIMIAR" + sufixo, alto)           # para dizer QUEM e
    LIMIAR_BAIXO = _num("ARENA_LIMIAR_BAIXO" + sufixo, baixo)  # abaixo: ninguem
    MARGEM = _num("ARENA_MARGEM", "0.05")           # folga sobre o segundo nome
    MINIMO = int(_num("ARENA_MINIMO", "3"))         # leituras para autorizar
    MINIMO_DESC = int(_num("ARENA_MINIMO_DESC", "5"))  # para chamar de desconhecido
    MAXIMO = int(_num("ARENA_MAXIMO", "14"))        # depois disso, decide de vez
    MESMO_DESCONHECIDO = _num("ARENA_MESMO_DESC" + sufixo, MESMO_PADRAO[motor])
    ROSTO_MIN = _num("ARENA_ROSTO_MIN", "32")       # px de largura, no quadro cheio
    NOTA_MIN = _num("ARENA_NOTA_MIN", "0.80")       # nota do YuNet
    # Quanto o rosto pode estar virado: desvio do nariz ate o meio dos olhos,
    # dividido pela distancia entre os olhos. Era 0,35 e barrava quem estava
    # perto da camera mas olhando de lado (HAIZ, 20/10). Medido na HAIZ com o
    # Samuel girando a cabeca e a sala cheia de estranhos: de 0,55 a 0,70, o
    # Samuel deu no minimo 0,41 (17 leituras) e estranho no maximo 0,19. De
    # 0,70 a 0,85 o estranho continua baixo, mas o DONO cai para 0,15 a 0,27
    # em um quarto das leituras: leitura assim so serviria para dar alerta
    # errado contra o proprio autorizado. Por isso para em 0,70.
    FRENTE = _num("ARENA_FRENTE", "0.70")
    # A nota de cada pessoa e a media das TOPK fotos mais parecidas dela (1 =
    # so a melhor). Estranho costuma acertar UMA foto por sorte, e o dono se
    # parece com varias: no laboratorio (20/10), um estranho chegou a 0,40
    # contra a melhor foto, acima do limiar de 0,36.
    TOPK = max(1, int(_num("ARENA_TOPK", "1")))


configurar()
JANELA = 8                                      # media das ultimas leituras
PERDIDA_S = 3.0          # trilha sem rosto ha mais que isso deixa a tela
TAMANHO_MAX = 1.6        # rosto que muda mais que isso de largura: outra trilha
SEM_IMAGEM_S = 3.0       # camera sem quadro ha mais que isso: "sem imagem"
# Reabrir camera e uma tentativa a cada 30 s, nunca em laco: a Intelbras
# bloqueia o IP depois de tentativas seguidas (armadilha 5 do CLAUDE.md).
# Sem resposta, a espera dobra a cada tentativa, ate 5 min: insistir de 30 em
# 30 s mantem o bloqueio de pe.
REABRIR_S = 30.0
MARCA_MAX_S = 0.8        # video fluido: caixa mais velha que isso nao e desenhada
REABRIR_MAX_S = 300.0


# --------------------------------------------------------------- qualidade
def de_pe(l):
    """Olhos lado a lado e acima do nariz (colunas do YuNet: 4-5 olho direito,
    6-7 olho esquerdo, 8-9 nariz)."""
    dx, dy = abs(l[6] - l[4]), abs(l[7] - l[5])
    return dx > dy and (l[5] + l[7]) / 2 < l[9]


def virado(l):
    """Desvio do nariz ate o meio dos olhos, em entre-olhos (0 = de frente)."""
    entre = abs(l[6] - l[4])
    return 9.0 if entre < 1 else float(abs(l[8] - (l[4] + l[6]) / 2) / entre)


def de_frente(l, folga=None):
    """Nariz perto do meio dos olhos. Rosto virado poe o nariz quase em cima
    de um olho, e o vetor de rosto de lado nao se parece com o de frente."""
    return virado(l) <= (FRENTE if folga is None else folga)


def leitura_boa(l):
    if float(l[14]) < NOTA_MIN:
        return False, "nota baixa"
    if float(l[2]) < ROSTO_MIN:
        return False, "rosto pequeno"
    if not de_pe(l):
        return False, "torto"
    if not de_frente(l):
        return False, "de lado"
    return True, ""


# ----------------------------------------------------------------- o juiz
class Trilha:
    def __init__(self, ident, camera):
        self.id = ident
        self.camera = camera
        self.notas = []         # por leitura: vetor com a nota de cada pessoa
        self.vetores = []       # os rostos lidos (para juntar desconhecidos)
        self.n = 0
        self.estado = "analisando"
        self.nome = None
        self.nota = 0.0
        self.numero = None      # numero do desconhecido
        self.visto = -1e9       # ultima vez na tela (segundos desde o inicio)
        self.comeco = None      # primeira vez na tela
        self.motivo = ""        # por que a ultima leitura nao valeu


class Juiz:
    """Decide por trilha, e nao por quadro. Nao sabe nada de camera nem de
    tela: recebe vetores, devolve eventos. E isso que deixa testar a decisao
    sem rosto de verdade (testes/arena_juiz.py)."""

    def __init__(self, nomes, M, dono):
        self.nomes, self.M, self.dono = list(nomes), M, np.asarray(dono, int)
        self._linhas = [np.where(self.dono == i)[0] for i in range(len(self.nomes))]
        self.trilhas = {}
        self.grupos = []        # desconhecidos: {"numero", "soma", "n"}
        # Quem ja foi identificado alguma vez. O placar conta daqui, e nao so da
        # trilha de agora: se a trilha recomecar (ver _outro_rosto), a
        # pessoa ja identificada nao some do placar.
        self.identificados = set()
        self.eventos = []

    def trilha(self, ident, camera=0):
        t = self.trilhas.get(ident)
        if t is None:
            t = self.trilhas[ident] = Trilha(ident, camera)
        return t

    def _por_pessoa(self, v):
        nota = np.full(len(self.nomes), -1.0, np.float32)
        if not len(self.M):
            return nota
        s = self.M @ v
        if TOPK == 1:
            np.maximum.at(nota, self.dono, s)
            return nota
        for i, idx in enumerate(self._linhas):
            if len(idx):
                melhores = np.sort(s[idx])[-TOPK:]
                nota[i] = float(melhores.mean())
        return nota

    def ler(self, ident, v, agora=0.0, camera=0):
        """Uma leitura boa de rosto, ja como vetor de 128. Devolve os eventos
        que ela causou (lista vazia quase sempre)."""
        v = np.asarray(v, np.float32)
        v = v / (np.linalg.norm(v) + 1e-9)
        t = self.trilha(ident, camera)
        t.notas.append(self._por_pessoa(v))
        t.vetores.append(v)
        t.notas, t.vetores = t.notas[-JANELA:], t.vetores[-JANELA:]
        t.n += 1
        t.visto = max(t.visto, agora)
        if t.comeco is None:
            t.comeco = agora

        return self._decidir(t, agora)

    def _decidir(self, t, agora):
        if not self.nomes:
            media, melhor, segundo, votos = None, -1.0, -1.0, 0.0
        else:
            media = np.mean(t.notas, axis=0)
            ordem = np.argsort(media)[::-1]
            i = int(ordem[0])
            melhor = float(media[i])
            segundo = float(media[ordem[1]]) if len(ordem) > 1 else -1.0
            votos = float(np.mean([int(np.argmax(x)) == i and x[i] >= LIMIAR_BAIXO
                                   for x in t.notas]))
        quem = self.nomes[i] if self.nomes else None

        autoriza = (melhor >= LIMIAR and melhor - segundo >= MARGEM
                    and votos >= 0.5)
        if t.estado == "autorizado" and self._outro_rosto(t):
            # O RASTREADOR PASSOU A TRILHA PARA OUTRA PESSOA. Ele cola o rosto
            # no mais proximo do quadro anterior, e duas pessoas que se cruzam
            # podem trocar de trilha. Sem isto, quem herdasse a trilha de um
            # autorizado ficava com o nome dele ate o fim, e nenhum alerta
            # tocava: o erro mais caro da prova. A trilha recomeca do zero, e
            # quem ja foi identificado continua no placar.
            ev = [dict(tipo="troca", nome=t.nome, trilha=t.id, quando=agora)]
            t.estado, t.nome, t.nota, t.n = "analisando", None, 0.0, 0
            t.notas, t.vetores = [], []
            self.eventos.extend(ev)
            return ev
        if t.n >= MINIMO and autoriza:
            novo = ("autorizado", quem)
        elif t.n >= MINIMO_DESC and melhor < LIMIAR_BAIXO:
            novo = ("desconhecido", None)
        elif t.n >= MAXIMO:
            # Tempo de sobra e ainda na duvida: quem nao chegou a ser
            # reconhecido com folga NAO e tratado como autorizado. Se for um
            # autorizado com rosto ruim, ele sai da conta de alertas quando for
            # reconhecido (era_desconhecido).
            novo = ("autorizado", quem) if autoriza else ("desconhecido", None)
        else:
            return []

        ev = []
        if novo[0] == "autorizado":
            if t.estado != "autorizado" or t.nome != novo[1]:
                antes = (t.estado, t.numero)
                t.estado, t.nome, t.numero = "autorizado", novo[1], None
                self.identificados.add(t.nome)
                ev.append(dict(tipo="autorizado", nome=t.nome,
                               nota=round(melhor, 3), trilha=t.id, quando=agora,
                               era_desconhecido=antes[1] if antes[0] == "desconhecido" else None))
            t.nota = melhor
        elif t.estado == "analisando":
            # UMA VEZ DESCONHECIDO, SO VOLTA SE FOR RECONHECIDO. Autorizado
            # nao vira desconhecido por ter virado o rosto um instante.
            t.estado, t.nome, t.nota = "desconhecido", None, melhor
            numero, novo_alerta, parecido, com = self._agrupar(t, agora)
            t.numero = numero
            if novo_alerta:
                ev.append(dict(tipo="desconhecido", numero=numero,
                               nota=round(melhor, 3), trilha=t.id, quando=agora,
                               parecido=parecido, com=com))
            else:
                ev.append(dict(tipo="juntou", numero=numero, trilha=t.id,
                               quando=agora, parecido=parecido))
        self.eventos.extend(ev)
        return ev

    def _outro_rosto(self, t):
        """A trilha autorizada tem a janela inteira de leituras boas em que o
        nome dela nunca ganhou e ficou abaixo do LIMIAR_BAIXO? Leitura ruim da
        mesma pessoa nao chega aqui: o portao de qualidade (nota, tamanho, de
        frente) ja tirou, e rosto bom da mesma pessoa nao fica tanto tempo tao
        longe do cadastro dela."""
        if len(t.notas) < JANELA:
            return False
        i = self.nomes.index(t.nome)
        return all(x[i] < LIMIAR_BAIXO or int(np.argmax(x)) != i for x in t.notas) \
            and float(np.mean([x[i] for x in t.notas])) < LIMIAR_BAIXO

    def _agrupar(self, t, agora):
        """Este desconhecido ja foi visto (outra trilha, mesma pessoa)?
        Devolve (numero, alerta_novo, nota_do_mais_parecido, numero_dele).

        Grupo com uma trilha que ainda era vista DEPOIS que esta comecou nao
        entra na conta: as duas estiveram no mesmo quadro, sao duas pessoas
        (na HAIZ, tres estranhos viraram um alerta). Trilha que acabou antes
        desta comecar pode ser a mesma pessoa: quem anda rapido e perdido
        pelo rastreador e volta com outro numero no quadro seguinte. Uma
        janela de 1,5 s no lugar disto dava dois alertas para essa pessoa."""
        m = np.mean(t.vetores, axis=0)
        m = m / (np.linalg.norm(m) + 1e-9)
        melhor, alvo = -1.0, None
        for g in self.grupos:
            comeco = t.comeco if t.comeco is not None else agora
            if any(tid != t.id and self.trilhas[tid].visto >= comeco
                   for tid in g["trilhas"]):
                continue
            c = g["soma"] / (np.linalg.norm(g["soma"]) + 1e-9)
            s = float(c @ m)
            if s > melhor:
                melhor, alvo = s, g
        com = alvo["numero"] if alvo is not None else None
        if alvo is not None and melhor >= MESMO_DESCONHECIDO:
            alvo["soma"] = alvo["soma"] + m
            alvo["trilhas"].append(t.id)
            return alvo["numero"], False, round(melhor, 3), com
        g = {"numero": len(self.grupos) + 1, "soma": m.copy(), "trilhas": [t.id]}
        self.grupos.append(g)
        return g["numero"], True, round(melhor, 3) if alvo is not None else None, com

    def resumo(self):
        """O placar de agora. Contado pelo ESTADO de cada trilha, e nao pelos
        eventos: um desconhecido que depois foi reconhecido sai da conta."""
        autorizados = sorted(self.identificados)
        desconhecidos = sorted({t.numero for t in self.trilhas.values()
                                if t.estado == "desconhecido"})
        return dict(autorizados=autorizados, total_autorizados=len(self.nomes),
                    desconhecidos=desconhecidos)


# ------------------------------------------------------------- rastreador
class Rastreador:
    """Cola o rosto deste quadro no rosto mais proximo do quadro anterior.

    Simples de proposito: a arena tem poucas pessoas, andando devagar. Um
    rastreador mais esperto aqui so traria mais coisa para dar errado no dia.
    Se ele errar e partir uma pessoa em duas trilhas, o juiz junta os
    desconhecidos pelo rosto, e o autorizado aparece pelo nome do mesmo jeito."""

    def __init__(self, prefixo):
        self.prefixo = prefixo
        self.vivas = {}         # id -> (cx, cy, largura, visto)
        self.proximo = 1

    def associar(self, caixas, agora):
        livres = {k: v for k, v in self.vivas.items() if agora - v[3] <= PERDIDA_S}
        ids = []
        for (x, y, w, h) in caixas:
            cx, cy = x + w / 2, y + h / 2
            alvo, perto = None, float("inf")
            for k, (px, py, pw, _) in livres.items():
                # ROSTO QUE TRIPLICA DE TAMANHO E OUTRA PESSOA. Na HAIZ (20/10,
                # sala cheia), um estranho de 54 px ao fundo sumiu e o Samuel
                # entrou na frente, no mesmo ponto da imagem, com 179 px: o raio
                # (que cresce com o rosto maior) pegou, o Samuel herdou a trilha
                # do estranho, e o alerta dele sumiu do placar ("era o
                # desconhecido #5"). Entre um quadro e outro o rosto nao muda
                # tanto; quem chega perto de verdade so ganha trilha nova.
                if max(w, pw) > TAMANHO_MAX * min(w, pw):
                    continue
                d = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5
                if d < max(w, pw) * 1.2 and d < perto:
                    alvo, perto = k, d
            if alvo is None:
                alvo = f"{self.prefixo}-{self.proximo}"
                self.proximo += 1
            else:
                livres.pop(alvo)
            self.vivas[alvo] = (cx, cy, w, agora)
            ids.append(alvo)
        self.vivas = {k: v for k, v in self.vivas.items() if agora - v[3] <= 30}
        return ids


# ---------------------------------------------------------------- cameras
class Camera:
    def __init__(self, indice, fonte, largura, altura, fps):
        self.indice, self.fonte = indice, fonte
        self.largura, self.altura, self.fps = largura, altura, fps
        self.arquivo = not str(fonte).startswith("rtsp") and not str(fonte).isdigit()
        self.cap = None
        self.ultimo = 0.0
        self.aberta_em = 0.0
        self.acabou = False
        self.quadros = 0
        self.espera = REABRIR_S
        self.rast = Rastreador(f"c{indice}")
        self.abrir()

    def abrir(self):
        self.aberta_em = time.monotonic()
        if str(self.fonte).startswith("rtsp"):
            from aibox.gstcam import Gst
            self.cap = Gst(self.fonte, self.largura, self.altura, self.fps, bordas=True)
        else:
            import cv2
            f = int(self.fonte) if str(self.fonte).isdigit() else self.fonte
            self.cap = cv2.VideoCapture(f)

    def ler(self):
        """(quadro ou None). Arquivo que acabou marca `acabou`."""
        ok, q = self.cap.read()
        if ok is None:
            return None
        if not ok:
            if self.arquivo:
                self.acabou = True
            return None
        self.ultimo = time.monotonic()
        self.espera = REABRIR_S
        self.quadros += 1
        return q

    def estado(self, agora):
        if self.acabou:
            return "fim do video"
        if agora - max(self.ultimo, self.aberta_em) > SEM_IMAGEM_S:
            return "sem imagem"
        return "ok" if self.ultimo else "abrindo"

    def talvez_reabrir(self, agora):
        if self.arquivo or self.acabou:
            return
        if agora - max(self.ultimo, self.aberta_em) > self.espera:
            print(f"[arena] camera {self.indice} sem imagem ha {self.espera:.0f} s; "
                  "reabrindo (uma tentativa). Se o terminal mostrou 403, a camera "
                  "bloqueou o IP: Ctrl+C e nao tente nada por uns 30 min", flush=True)
            self.espera = min(self.espera * 2, REABRIR_MAX_S)
            try:
                self.cap.release()
            except Exception:
                pass
            self.abrir()

    def fechar(self):
        try:
            self.cap.release()
        except Exception:
            pass


# ------------------------------------------------- cadastro pelo botao
class Coleta:
    """O botao "Cadastrar" da pagina, SO no modo preparo (--preparo).

    A regra da prova proibe cadastro e ajuste na hora: sem --preparo a rota
    nem existe. No laboratorio ele faz o mesmo que o cadastrar.py
    --acrescentar, pela camera da arena, sem colar comando comprido.

    A HAIZ ve a sala inteira, e o cadastrar.py para em "mais de um rosto" o
    tempo todo. Aqui vale o MAIOR rosto, e so se ele estiver perto (largura
    >= ROSTO_MIN_PX) e bem maior que o segundo (FOLGA_TAMANHO): quem esta na
    frente da camera, e nao quem passa ao fundo. E o mesmo filtro do
    cadastrar.py fica no fim: amostra que nao se parece com o que a pessoa
    ja tem na galeria fica de fora."""

    AMOSTRAS = 6
    INTERVALO_S = 1.5
    PRAZO_S = 60.0
    ROSTO_MIN_PX = 90
    FOLGA_TAMANHO = 1.5

    def __init__(self, nome, agora):
        self.nome, self.inicio = nome, agora
        self.vetores, self.proxima = [], 0.0
        self.msg = "olhe para a camera, a 1 ou 2 m"

    def ver(self, rostos, agora):
        """rostos: [(largura, vetor ou None)] de todos os rostos do quadro;
        None = leitura ruim (de lado, borrado). Devolve "pronto", "prazo" ou
        None (continua)."""
        if agora - self.inicio > self.PRAZO_S:
            self.msg = f"{self.PRAZO_S:.0f} s sem completar; tente de novo"
            return "prazo"
        if agora < self.proxima:
            return None
        if not rostos:
            self.msg = "nenhum rosto na imagem"
            return None
        rs = sorted(rostos, key=lambda r: -r[0])
        w, v = rs[0]
        if len(rs) > 1 and w < self.FOLGA_TAMANHO * rs[1][0]:
            self.msg = "outro rosto do mesmo tamanho: fique sozinho mais perto"
            return None
        if w < self.ROSTO_MIN_PX:
            self.msg = f"chegue mais perto ({w:.0f} px de {self.ROSTO_MIN_PX})"
            return None
        if v is None:
            self.msg = "rosto de lado ou borrado: olhe para a camera"
            return None
        self.vetores.append([float(x) for x in v])
        self.proxima = agora + self.INTERVALO_S
        self.msg = f"amostra {len(self.vetores)} de {self.AMOSTRAS}: mexa a cabeca devagar"
        return "pronto" if len(self.vetores) >= self.AMOSTRAS else None


def gravar_coleta(coleta, caminho, motor):
    """(ok, mensagem). O mesmo criterio do cadastrar.py --acrescentar."""
    from aibox.cadastrar_fotos import DESTOA, unitario
    antes = galeria.ler(caminho)["pessoas"].get(coleta.nome, [])
    if not antes:
        return False, f"{coleta.nome} nao esta na galeria; o botao so completa quem ja esta"
    centro = unitario(np.mean([unitario(np.array(v)) for v in antes], axis=0))
    notas = [float(unitario(np.array(v)) @ centro) for v in coleta.vetores]
    bons = [v for v, n in zip(coleta.vetores, notas) if n >= DESTOA]
    fora = len(coleta.vetores) - len(bons)
    if len(bons) < 3:
        return False, (f"so {len(bons)} amostra(s) parecidas com {coleta.nome} "
                       f"(notas {', '.join(f'{n:.2f}' for n in notas)}): outra pessoa "
                       "na frente da camera? Nada gravado")
    total = galeria.gravar(coleta.nome, bons, True, caminho, motor=motor)
    return True, (f"{coleta.nome}: {total} amostras na galeria"
                  + (f" ({fora} ficaram de fora: nao pareciam com {coleta.nome})" if fora else ""))


# ---------------------------------------------------------- video fluido
class VideoFluido:
    """O VIDEO DA PAGINA no ritmo da camera, pelo fluxo SECUNDARIO dela.

    A analise le o fluxo principal (2880x1620 na HAIZ) e faz 2 a 6 leituras
    por segundo: e o que a CPU da caixa aguenta com rosto em resolucao cheia.
    A pagina mostrava so os quadros analisados, e 2 quadros por segundo
    parece sistema travado, mesmo decidindo em 1 s. Aqui o video vem de
    outra conexao, a do fluxo leve da camera (CAMERA_ARENA_VIDEO), que custa
    pouco para decodificar, e as caixas desenhadas sao as da ULTIMA analise.
    A identificacao nao muda nada: continua no fluxo principal.

    O video NAO serve para reconhecer, so para olhar: por isso aqui pode
    esticar (bordas=False), e as caixas sao reescaladas pela proporcao."""

    def __init__(self, fonte, larg_analise, alt_analise, tela, larg=960, alt=540, fps=25):
        self.fonte, self.tela = fonte, tela
        self.larg, self.alt, self.fps = larg, alt, fps
        self.sx, self.sy = larg / larg_analise, alt / alt_analise
        self.marcas = []            # [((x, y, w, h), cor, texto)] na escala da analise
        self.marcado = 0.0          # quando a ultima analise mandou as marcas
        self.vistos = []            # instantes dos quadros mostrados (para o qps)
        self.ultimo = 0.0
        self.aberta_em = 0.0
        self.espera = REABRIR_S
        self.vivo = True
        self._abrir()
        threading.Thread(target=self._rodar, daemon=True).start()

    def _abrir(self):
        self.aberta_em = time.monotonic()
        self.arquivo = not str(self.fonte).startswith("rtsp")
        if self.arquivo:
            import cv2
            f = int(self.fonte) if str(self.fonte).isdigit() else self.fonte
            self.cap = cv2.VideoCapture(f)
        else:
            from aibox.gstcam import Gst
            # O codec do fluxo leve pode ser outro: na HAIZ o principal e H.264
            # e o leve (704x480) e H.265. CAMERA_ARENA_VIDEO_CODEC=h265.
            self.cap = Gst(self.fonte, self.larg, self.alt, self.fps, bordas=False,
                           codec=os.environ.get("CAMERA_ARENA_VIDEO_CODEC") or None,
                           sem_corrompido=True)

    def marcar(self, marcas):
        self.marcas, self.marcado = marcas, time.monotonic()

    def ao_vivo(self, agora):
        """Chegou quadro do fluxo leve nos ultimos 2 s? Se nao, a pagina volta
        a mostrar os quadros analisados: na HAIZ (21/10) o stream=1 nao abriu
        e a pagina ficou PRETA, com a identificacao rodando por tras."""
        return agora - self.ultimo <= 2.0

    def qps(self, agora):
        self.vistos = [x for x in self.vistos if agora - x <= 5]
        return len(self.vistos) / 5.0

    def _rodar(self):
        import cv2
        while self.vivo:
            ok, q = self.cap.read()
            agora = time.monotonic()
            if not ok:
                if (ok is False and not self.arquivo
                        and agora - max(self.ultimo, self.aberta_em) > self.espera):
                    # Uma tentativa por vez, com espera crescente: camera
                    # bloqueia quem insiste (armadilha 5).
                    self.espera = min(self.espera * 2, REABRIR_MAX_S)
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                    self._abrir()
                time.sleep(0.01)
                continue
            self.ultimo, self.espera = agora, REABRIR_S
            if self.arquivo:
                time.sleep(1.0 / self.fps)
                if q.shape[1] != self.larg or q.shape[0] != self.alt:
                    q = cv2.resize(q, (self.larg, self.alt))
            if not self.tela.clientes:
                continue
            q = q.copy()                # o quadro do cano e so leitura
            # CAIXA VELHA SOME. A caixa e da ultima analise, 0,15 a 0,4 s
            # atras do video. Se a analise atrasar mais que isso, quem andou
            # sai de dentro da caixa, e um nome flutuando sobre outra pessoa e
            # pior que nenhuma caixa.
            marcas = self.marcas if agora - self.marcado <= MARCA_MAX_S else []
            for (x, y, w, h), cor, txt in marcas:
                p1 = (int(x * self.sx), int(y * self.sy))
                p2 = (int((x + w) * self.sx), int((y + h) * self.sy))
                cv2.rectangle(q, p1, p2, cor, 2 if txt else 1)
                if txt:
                    cv2.putText(q, txt, (p1[0], max(16, p1[1] - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 2, cv2.LINE_AA)
            ok, buf = cv2.imencode(".jpg", q, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                self.tela.publicar_jpeg(buf.tobytes())
                self.vistos.append(agora)

    def fechar(self):
        self.vivo = False
        try:
            self.cap.release()
        except Exception:
            pass


# ------------------------------------------------------------------ tela
def ascii(s):
    """O putText do OpenCV nao desenha acento; a pagina desenha (vem no JSON)."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


VERDE, RUBI, AMBAR, BRANCO = (95, 191, 95), (70, 70, 235), (40, 190, 235), (240, 240, 240)
CINZA = (150, 150, 150)


def rotulo(juiz, ident, motivo):
    t = juiz.trilhas.get(ident)
    if t is not None and t.estado == "autorizado":
        return VERDE, f"AUTORIZADO: {ascii(t.nome)} ({t.nota:.2f})"
    if t is not None and t.estado == "desconhecido":
        return RUBI, f"DESCONHECIDO #{t.numero}"
    n = t.n if t else 0
    if motivo == "rosto pequeno" and n == 0:
        # LONGE DEMAIS PARA LER, e nao entra na conta. Com a Intelbras do alto
        # (21/10) o fundo da sala virou uma pilha de "analisando 0/3 (rosto
        # pequeno)" amarelos. Chamar de desconhecido seria pior: na arena o
        # fundo e a PLATEIA, e cada pessoa dela viraria um alerta.
        return CINZA, ""
    return AMBAR, f"analisando {n}/{MINIMO}" + (f" ({motivo})" if motivo else "")


def desenhar(cv2, img, juiz, vistos, largura_tela):
    escala = min(1.0, largura_tela / img.shape[1])
    tela = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA) \
        if escala < 1 else img.copy()
    for ident, (x, y, w, h), motivo in vistos:
        cor, txt = rotulo(juiz, ident, motivo)
        p1 = (int(x * escala), int(y * escala))
        p2 = (int((x + w) * escala), int((y + h) * escala))
        cv2.rectangle(tela, p1, p2, cor, 2 if txt else 1)
        if txt:
            cv2.putText(tela, txt, (p1[0], max(16, p1[1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor, 2, cv2.LINE_AA)
    return tela


PAGINA = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auditix IA na arena</title><style>
:root{color-scheme:dark;--verde:#5FBFA0;--rubi:#E8707F;--ambar:#E5C07B;
      --fundo:#0C1512;--caixa:#16302A;--linha:#2C5A4C;--texto:#E3F2EC;--fraco:#8FB3A7}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--texto);
     font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;padding:14px 18px;
       border-bottom:1px solid var(--linha)}
h1{margin:0;font-size:21px}h1 i{font-style:normal;color:var(--verde)}
.sub{color:var(--fraco);font-size:12px;letter-spacing:.14em;text-transform:uppercase}
main{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:16px;padding:16px}
@media (max-width:900px){main{grid-template-columns:1fr}}
.palco{background:#000;border:1px solid var(--linha);border-radius:12px;overflow:hidden;line-height:0}
.palco img{width:100%;height:auto}
.n{background:var(--caixa);border:1px solid var(--linha);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.n b{display:block;font-size:40px;line-height:1.1;font-variant-numeric:tabular-nums}
.n span{color:var(--fraco);font-size:12px;letter-spacing:.1em;text-transform:uppercase}
#aut b{color:var(--verde)} #desc b{color:var(--rubi)}
.nomes{margin-top:6px;font-size:14px}
.cam{display:flex;justify-content:space-between;font-size:14px}
.ok{color:var(--verde)} .mal{color:var(--rubi)}
ol{margin:6px 0 0;padding-left:20px;font-size:13.5px;color:var(--fraco)}
.morto{opacity:.4}
</style>
<header><h1>Audit<i>ix</i> IA</h1><span class="sub">arena · identificação na AI BOX</span>
<span class="sub" id="tempo"></span></header>
<main>
  <div class="palco"><img src="/video" alt="imagem ao vivo das câmeras"></div>
  <aside>
    <div class="n" id="aut"><b id="nAut">--</b><span>autorizados identificados</span>
      <div class="nomes" id="nomes"></div></div>
    <div class="n" id="desc"><b id="nDesc">--</b><span>alertas de desconhecido</span></div>
    <div class="n"><span>câmeras</span><div id="cams"></div></div>
    <div class="n"><span>desempenho</span><div class="cam"><span>análise</span><b id="qps" style="font-size:15px">--</b></div>
      <div class="cam" id="linhaVideo" hidden><span>vídeo</span><b id="vqps" style="font-size:15px">--</b></div>
      <div class="cam"><span>tempo por quadro</span><b id="ms" style="font-size:15px">--</b></div></div>
    <div class="n" id="cad" hidden><span>cadastro (modo preparo)</span>
      <div style="display:flex;gap:8px;margin-top:8px"><select id="cadNome" style="flex:1"></select>
      <button id="cadBotao" type="button">Cadastrar</button></div>
      <div id="cadMsg" class="nomes" style="color:var(--fraco)"></div></div>
    <div class="n"><span>últimos eventos</span><ol id="ev"></ol></div>
  </aside>
</main>
<script>
const $ = i => document.getElementById(i);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
setInterval(async () => {
  try{
    const e = await (await fetch('/estado')).json();
    $('nAut').textContent = e.autorizados.length + ' de ' + e.total_autorizados;
    $('nomes').innerHTML = e.autorizados.map(esc).join('<br>') || '—';
    $('nDesc').textContent = e.desconhecidos.length;
    $('cams').innerHTML = e.cameras.map(c => '<div class="cam"><span>câmera ' + c.indice +
      '</span><b class="' + (c.estado === 'ok' ? 'ok' : 'mal') + '" style="font-size:15px">' +
      esc(c.estado) + ' · ' + c.qps.toFixed(1) + '/s</b></div>').join('');
    $('qps').textContent = e.qps.toFixed(1) + ' leituras/s';
    if (e.video_qps != null) {
      $('linhaVideo').hidden = false;
      $('vqps').textContent = e.video_qps.toFixed(1) + ' quadros/s';
    }
    $('ms').textContent = Math.round(e.ms) + ' ms';
    $('tempo').textContent = e.tempo;
    $('ev').innerHTML = e.eventos.map(x => '<li>' + esc(x) + '</li>').join('');
    if (e.cadastro) {
      $('cad').hidden = false;
      const sel = $('cadNome');
      if (sel.options.length !== e.cadastro.nomes.length)
        sel.innerHTML = e.cadastro.nomes.map(n => '<option>' + esc(n) + '</option>').join('');
      $('cadBotao').disabled = e.cadastro.ativo;
      $('cadMsg').textContent = e.cadastro.msg || '';
    }
    document.body.classList.remove('morto');
  }catch(_){ document.body.classList.add('morto'); }
}, 700);
$('cadBotao').addEventListener('click', async () => {
  $('cadBotao').disabled = true;
  $('cadMsg').textContent = 'começando…';
  try {
    await fetch('/cadastrar', {method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify({nome: $('cadNome').value})});
  } catch (_) { $('cadMsg').textContent = 'a caixa não respondeu'; }
});
</script>
""".encode("utf-8")


class Tela:
    """MJPEG + JSON, servidos pela caixa. O mesmo jeito do aibox/vivo.py."""

    def __init__(self, porta, preparo=False):
        self.jpeg, self.estado, self.clientes = None, {}, 0
        self.preparo, self.pedido = preparo, None
        self._trava = threading.Lock()
        tela = self

        class Mao(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_POST(self):
                # SO NO MODO PREPARO. Na prova (sem --preparo) cadastrar na
                # hora e proibido, e a rota responde 403.
                if not self.path.startswith("/cadastrar") or not tela.preparo:
                    corpo, cod = b'{"erro": "cadastro so no modo preparo"}', 403
                else:
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                        nome = str(json.loads(self.rfile.read(n) or b"{}").get("nome", "")).strip()
                    except Exception:
                        nome = ""
                    if nome:
                        tela.pedido = nome
                        corpo, cod = b'{"ok": true}', 200
                    else:
                        corpo, cod = b'{"erro": "falta o nome"}', 400
                self.send_response(cod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def do_GET(self):
                if self.path.startswith("/video"):
                    return self._video()
                if self.path.startswith("/estado"):
                    with tela._trava:
                        corpo = json.dumps(tela.estado).encode()
                    tipo = "application/json"
                else:
                    corpo, tipo = PAGINA, "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(corpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(corpo)

            def _video(self):
                self.protocol_version = "HTTP/1.0"
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                tela.clientes += 1
                ultimo = None
                try:
                    while True:
                        q = tela.jpeg
                        if q is None or q is ultimo:
                            time.sleep(0.02)
                            continue
                        ultimo = q
                        self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\n"
                                         b"Content-Length: " + str(len(q)).encode() +
                                         b"\r\n\r\n" + q + b"\r\n")
                except Exception:
                    pass
                finally:
                    tela.clientes = max(0, tela.clientes - 1)

        self._srv = ThreadingHTTPServer(("0.0.0.0", porta), Mao)
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def publicar_jpeg(self, jpeg):
        with self._trava:
            self.jpeg = jpeg

    def publicar(self, estado, jpeg=None):
        with self._trava:
            self.estado = estado
            if jpeg is not None:
                self.jpeg = jpeg

    def fechar(self):
        try:
            self._srv.shutdown()
        except Exception:
            pass


# ------------------------------------------------------------------ laco
def relogio(s):
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def main():
    from aibox.sala import carregar_env
    carregar_env()
    p = argparse.ArgumentParser(description="Auditix IA, modo arena (so rosto)")
    p.add_argument("--camera", action="append",
                   help="rtsp://..., numero da webcam ou arquivo de video; "
                        "repita para usar duas cameras")
    p.add_argument("--largura", type=int, default=int(_num("ARENA_LARG", "1920")))
    p.add_argument("--altura", type=int, default=int(_num("ARENA_ALT", "1080")))
    p.add_argument("--fps", type=int, default=int(_num("ARENA_FPS", "6")),
                   help="teto de quadros por segundo lidos da camera (0 = sem teto)")
    # 1280 e nao o quadro cheio: na HAIZ (20/10) o tempo por quadro caiu de
    # ~530 para ~300 ms. O rosto continua MEDIDO no quadro cheio (o detector
    # devolve os pontos na escala real), e o menor rosto aceito, 32 px, vira
    # ~21 px na busca, que o YuNet ainda acha.
    p.add_argument("--deteccao", type=int, default=int(_num("ARENA_DETECCAO", "1280")),
                   help="largura em que o YuNet procura rosto (0 = quadro cheio)")
    p.add_argument("--galeria", default=os.environ.get("GALERIA") or galeria.PADRAO)
    p.add_argument("--porta", type=int, default=int(_num("ARENA_PORTA", "8080")))
    p.add_argument("--tela", type=int, default=1280, help="largura da imagem na pagina")
    p.add_argument("--video", default=os.environ.get("CAMERA_ARENA_VIDEO", ""),
                   help="fluxo LEVE da mesma camera, so para o video da pagina "
                        "ficar no ritmo da camera (CAMERA_ARENA_VIDEO no .env)")
    p.add_argument("--segundos", type=float, default=0)
    p.add_argument("--preparo", action="store_true",
                   help="mostra o botao Cadastrar na pagina (so no laboratorio: "
                        "na prova, cadastro na hora e proibido)")
    p.add_argument("--calibrar", action="store_true",
                   help="imprime a nota de cada leitura (para escolher o limiar no local)")
    a = p.parse_args()

    fontes = a.camera or [c for c in (os.environ.get("CAMERA_ARENA"),
                                      os.environ.get("CAMERA_ARENA2")) if c]
    if not fontes:
        print("[arena] nenhuma camera: use --camera ou CAMERA_ARENA no .env")
        return 2

    nomes, M, dono = galeria.matriz(a.galeria)
    if not nomes:
        print(f"[arena] a galeria {a.galeria} esta vazia: ninguem para reconhecer.")
        return 2
    modelo = galeria.motor_de(a.galeria)
    configurar(modelo)

    import cv2
    from daten.app import config as dcfg
    from daten.app.recognizer import FaceEngine
    motor = FaceEngine()
    from aibox.arcface import extrator
    try:
        medir = extrator(modelo, motor)
    except FileNotFoundError as e:
        print(f"[arena] a galeria e do motor {modelo}, mas {e}")
        return 2
    juiz = Juiz(nomes, M, dono)
    cams = [Camera(i + 1, f, a.largura, a.altura, a.fps or None)
            for i, f in enumerate(fontes)]
    try:
        tela = Tela(a.porta, preparo=a.preparo)
    except OSError:
        print(f"[arena] a porta {a.porta} esta ocupada. O servico da sala esta "
              "rodando? Pare com: bash aibox/servico.sh parar  (ou use --porta 8090)")
        for c in cams:
            c.fechar()
        return 2

    fluido = None
    if a.video:
        if len(cams) > 1:
            print("[arena] CAMERA_ARENA_VIDEO e de UMA camera so; com duas, a "
                  "pagina continua mostrando os quadros analisados")
        else:
            fluido = VideoFluido(a.video, a.largura, a.altura, tela)
            print("[arena] video da pagina pelo fluxo leve da camera; a "
                  "identificacao continua no fluxo principal", flush=True)

    print(f"[arena] autorizados na galeria: {', '.join(nomes)}  (motor {modelo})")
    print(f"[arena] limiar {LIMIAR} / {LIMIAR_BAIXO}, margem {MARGEM}, "
          f"{MINIMO} leituras para autorizar, {MINIMO_DESC} para desconhecido, "
          f"nota = media das {TOPK} melhores fotos" if TOPK > 1 else
          f"[arena] limiar {LIMIAR} / {LIMIAR_BAIXO}, margem {MARGEM}, "
          f"{MINIMO} leituras para autorizar, {MINIMO_DESC} para desconhecido")
    print(f"[arena] imagem ao vivo: http://<IP da caixa>:{a.porta}", flush=True)

    parar = threading.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: parar.set())

    inicio = time.monotonic()
    descarte = {}               # trilha -> ultimo aviso de rosto descartado (--calibrar)
    log, tempos, ultimo_status = [], [], 0.0
    qps_cam = {c.indice: [] for c in cams}
    vistos_por_cam = {c.indice: [] for c in cams}
    quadro_tela = {}
    coleta, cadastro_msg = None, ""
    if a.preparo:
        print("[arena] MODO PREPARO: a pagina tem o botao Cadastrar. Na prova, rode "
              "sem --preparo", flush=True)

    while not parar.is_set():
        agora = time.monotonic()
        if a.segundos and agora - inicio >= a.segundos:
            break
        if all(c.acabou for c in cams):
            break
        trabalhou = False
        if tela.pedido and coleta is None:
            nome, tela.pedido = tela.pedido, None
            if nome in juiz.nomes:
                coleta = Coleta(nome, agora)
                print(f"[arena] cadastro pelo botao: {nome}", flush=True)
            else:
                cadastro_msg = f"{nome} nao esta na galeria"
        for cam in cams:
            img = cam.ler()
            if img is None:
                cam.talvez_reabrir(agora)
                continue
            trabalhou = True
            t0 = time.monotonic()
            dcfg.DETECT_WIDTH = a.deteccao or img.shape[1]
            linhas = motor.detect(img)
            caixas = [tuple(float(x) for x in l[:4]) for l in linhas]
            ids = cam.rast.associar(caixas, t0)
            vistos, rostos = [], []
            for l, ident, cx in zip(linhas, ids, caixas):
                t = juiz.trilha(ident, cam.indice)
                t.visto = max(t.visto, t0 - inicio)
                if t.comeco is None:
                    t.comeco = t0 - inicio
                boa, motivo = leitura_boa(l)
                t.motivo = motivo
                # Na calibracao, o rosto descartado tambem aparece (no maximo 1
                # vez por segundo por trilha): e assim que se acha a distancia
                # em que a camera deixa de ler alguem, sem ninguem da galeria.
                if a.calibrar and not boa and t0 - descarte.get(ident, -9) >= 1:
                    descarte[ident] = t0
                    print(f"   {ident} descartado: {motivo} ({float(l[2]):.0f} px,"
                          f" nota {float(l[14]):.2f}, virado {virado(l):.2f}"
                          f" de no maximo {FRENTE:.2f})", flush=True)
                # TODO rosto bom e medido, mesmo de quem ja foi decidido. Medir
                # menos quem ja tem nome foi tentado (20/10) e quebrou a troca
                # de trilha: a pessoa nova que ocupa o lugar herdava o nome
                # (ensaio com video: 4 de 4 virou 1 de 4).
                v = None
                if boa:
                    v = medir(img, l)
                    for ev in juiz.ler(ident, v, t0 - inicio, cam.indice):
                        if ev["tipo"] == "juntou":
                            txt = (f"{relogio(t0 - inicio)} trilha {ev['trilha']}: o mesmo "
                                   f"desconhecido #{ev['numero']} voltou "
                                   f"(parecido {ev['parecido']:.2f}, minimo {MESMO_DESCONHECIDO:.2f})")
                            print(f"[arena] {txt}", flush=True)
                            log.append(txt)
                            continue
                        if ev["tipo"] == "troca":
                            txt = (f"{relogio(t0 - inicio)} trilha {ev['trilha']}: o rosto "
                                   f"deixou de ser {ev['nome']}, analisando de novo")
                            print(f"[arena] {txt}", flush=True)
                            log.append(txt)
                            continue
                        txt = (f"{relogio(t0 - inicio)} AUTORIZADO {ev['nome']} ({ev['nota']:.2f})"
                               + (f", era o desconhecido #{ev['era_desconhecido']}"
                                  if ev.get("era_desconhecido") else "")
                               if ev["tipo"] == "autorizado" else
                               f"{relogio(t0 - inicio)} ALERTA desconhecido #{ev['numero']}"
                               + (f" (o mais parecido era o #{ev['com']}: {ev['parecido']:.2f})"
                                  if ev.get("parecido") is not None else ""))
                        print("[arena] " + txt, flush=True)
                        log.append(txt)
                    if a.calibrar and juiz.trilhas[ident].notas:
                        n = juiz.trilhas[ident].notas[-1]
                        top = sorted(zip(nomes, n), key=lambda x: -x[1])[:2]
                        print(f"   {ident} leitura {juiz.trilhas[ident].n}: "
                              + ", ".join(f"{k} {s:.2f}" for k, s in top)
                              + f" ({float(l[2]):.0f} px, virado {virado(l):.2f})",
                              flush=True)
                vistos.append((ident, cx, motivo))
                rostos.append((float(l[2]), v))
            if coleta is not None and cam.indice == 1:
                fim = coleta.ver(rostos, t0)
                if fim == "pronto":
                    ok, cadastro_msg = gravar_coleta(coleta, a.galeria, modelo)
                    if ok:
                        # A galeria mudou: o juiz recomeca com ela (modo preparo).
                        nomes, M, dono = galeria.matriz(a.galeria)
                        juiz = Juiz(nomes, M, dono)
                    print(f"[arena] cadastro: {cadastro_msg}", flush=True)
                    coleta = None
                elif fim == "prazo":
                    cadastro_msg = f"{coleta.nome}: {coleta.msg}"
                    coleta = None
            ms = (time.monotonic() - t0) * 1000
            tempos.append(ms)
            tempos = tempos[-30:]
            qps_cam[cam.indice].append(time.monotonic())
            vistos_por_cam[cam.indice] = vistos
            if fluido is not None:
                fluido.marcar([(cx, *rotulo(juiz, ident, motivo))
                               for ident, cx, motivo in vistos])
            if (fluido is None or not fluido.ao_vivo(t0)) and tela.clientes:
                quadro_tela[cam.indice] = desenhar(cv2, img, juiz, vistos, a.tela)

        agora = time.monotonic()
        for k in qps_cam:
            qps_cam[k] = [x for x in qps_cam[k] if agora - x <= 5]
        r = juiz.resumo()
        estado = dict(
            autorizados=r["autorizados"], total_autorizados=r["total_autorizados"],
            desconhecidos=r["desconhecidos"],
            cameras=[dict(indice=c.indice, estado=c.estado(agora),
                          qps=len(qps_cam[c.indice]) / 5.0) for c in cams],
            qps=sum(len(v) for v in qps_cam.values()) / 5.0,
            ms=float(np.mean(tempos)) if tempos else 0.0,
            tempo=relogio(agora - inicio), eventos=log[-8:][::-1],
            video_qps=fluido.qps(agora) if fluido is not None else None,
            cadastro=(dict(nomes=juiz.nomes, ativo=coleta is not None,
                           msg=(f"{coleta.nome}: {coleta.msg}" if coleta else cadastro_msg))
                      if a.preparo else None))
        jpeg = None
        if fluido is not None and fluido.ao_vivo(agora):
            quadro_tela.clear()         # a pagina esta no video fluido
        elif trabalhou and tela.clientes and quadro_tela:
            partes = [quadro_tela[k] for k in sorted(quadro_tela)]
            if len(partes) > 1:
                alt = min(x.shape[0] for x in partes)
                partes = [cv2.resize(x, (int(x.shape[1] * alt / x.shape[0]), alt))
                          for x in partes]
            ok, buf = cv2.imencode(".jpg", np.hstack(partes) if len(partes) > 1 else partes[0],
                                   [cv2.IMWRITE_JPEG_QUALITY, 70])
            jpeg = buf.tobytes() if ok else None
        tela.publicar(estado, jpeg)

        if agora - ultimo_status >= 5:
            ultimo_status = agora
            cam_txt = "  ".join(f"cam{c['indice']} {c['estado']} {c['qps']:.1f}/s"
                                for c in estado["cameras"])
            print(f"[arena {estado['tempo']}] autorizados {len(r['autorizados'])}/"
                  f"{r['total_autorizados']} ({', '.join(r['autorizados']) or '-'})"
                  f" | desconhecidos {len(r['desconhecidos'])} | {cam_txt}"
                  f" | {estado['ms']:.0f} ms"
                  + (f" | video {estado['video_qps']:.1f}/s" if fluido is not None else ""),
                  flush=True)
        if not trabalhou:
            time.sleep(0.01)

    # ------------------------------------------------------------- o fim
    agora = time.monotonic()
    r = juiz.resumo()
    resultado = dict(
        quando=time.strftime("%Y-%m-%d %H:%M:%S"),
        duracao_s=round(agora - inicio, 1),
        autorizados_identificados=r["autorizados"],
        total_na_galeria=r["total_autorizados"],
        alertas_de_desconhecido=len(r["desconhecidos"]),
        cameras=[dict(indice=c.indice, estado=c.estado(agora), quadros=c.quadros)
                 for c in cams],
        tempo_medio_por_quadro_ms=round(float(np.mean(tempos)), 1) if tempos else None,
        limiares=dict(motor=MOTOR, limiar=LIMIAR, limiar_baixo=LIMIAR_BAIXO,
                      margem=MARGEM, minimo=MINIMO, minimo_desc=MINIMO_DESC,
                      mesmo_desconhecido=MESMO_DESCONHECIDO,
                      topk=TOPK),
        eventos=log)
    print("\n================ RESULTADO DA ARENA ================")
    print(f"  autorizados identificados: {len(r['autorizados'])} de "
          f"{r['total_autorizados']}  ({', '.join(r['autorizados']) or 'nenhum'})")
    print(f"  alertas de desconhecido:   {len(r['desconhecidos'])}")
    for c in resultado["cameras"]:
        print(f"  camera {c['indice']}: {c['estado']}, {c['quadros']} quadros analisados")
    if tempos:
        print(f"  tempo medio por quadro:    {resultado['tempo_medio_por_quadro_ms']} ms")
    print(f"  duracao:                   {relogio(resultado['duracao_s'])}")
    print("====================================================")
    pasta = os.path.join(RAIZ, "arena", "resultados")
    try:
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, time.strftime("arena-%Y%m%d-%H%M%S.json"))
        with open(arq, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=1)
        print(f"  (salvo em {arq}, sem imagem nenhuma)")
    except OSError as e:
        print(f"  (nao consegui salvar o resultado: {e})")
    for c in cams:
        c.fechar()
    if fluido is not None:
        fluido.fechar()
    tela.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
