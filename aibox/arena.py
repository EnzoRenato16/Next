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
    global MESMO_DESCONHECIDO, ROSTO_MIN, NOTA_MIN, FRENTE, TOPK, MOTOR, RECONFERIR_S
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
    # SEGUIR PRIMEIRO, RECONHECER DEPOIS. Quem ja foi decidido (autorizado ou
    # desconhecido) e medido de novo so a cada RECONFERIR_S segundos, e nao a
    # todo quadro: o rastreador segue a pessoa e o nome vai junto. 0 = mede
    # todo rosto bom, como sempre foi. Medir menos foi tentado em 20/10 sem
    # trava e a pessoa nova que ocupava o lugar herdava o nome; as travas
    # estao em Juiz.precisa_medir.
    RECONFERIR_S = max(0.0, _num("ARENA_RECONFERIR_S", "0"))


configurar()
JANELA = 8                                      # media das ultimas leituras
PERDIDA_S = 3.0          # trilha sem rosto ha mais que isso deixa a tela
LACUNA_S = 0.6           # trilha que sumiu mais que isso volta a ser medida
TAMANHO_MAX = 1.6        # rosto que muda mais que isso de largura: outra trilha
SEM_IMAGEM_S = 3.0       # camera sem quadro ha mais que isso: "sem imagem"
# Reabrir camera e uma tentativa a cada 30 s, nunca em laco: a Intelbras
# bloqueia o IP depois de tentativas seguidas (armadilha 5 do CLAUDE.md).
# Sem resposta, a espera dobra a cada tentativa, ate 5 min: insistir de 30 em
# 30 s mantem o bloqueio de pe.
REABRIR_S = 30.0
MARCA_MAX_S = 0.8        # video fluido: caixa mais velha que isso nao e desenhada
REABRIR_MAX_S = 300.0
# TROCAR A CAMERA PELA PAGINA abre uma conexao nova. A Intelbras bloqueia o IP
# (403) depois de conexoes seguidas (armadilha 5 do CLAUDE.md): entre duas
# trocas, no minimo isto.
TROCA_MIN_S = 10.0


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
        self.medido = -1e9      # ultima leitura medida (ARENA_RECONFERIR_S)
        self.suspeita = False   # a ultima leitura discordou da decisao


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
        self.medidos = 0        # rostos bons medidos pelo modelo de rosto
        self.poupados = 0       # rostos bons seguidos sem medir (RECONFERIR_S)

    def precisa_medir(self, ident, agora):
        """Este rosto bom precisa passar pelo modelo de rosto agora? Chamado
        ANTES de atualizar t.visto. Com ARENA_RECONFERIR_S=0, sempre.

        Quem ainda esta "analisando" e sempre medido. Quem ja foi decidido so
        e pulado se nada indicar troca de pessoa na trilha:
        - a trilha sumiu da tela por mais de LACUNA_S (quem volta pode ser
          outra pessoa no mesmo lugar: foi o defeito de 20/10);
        - a ultima leitura discordou da decisao (suspeita): a partir dai mede
          todo quadro, e o _outro_rosto pega a troca como sempre pegou."""
        t = self.trilhas.get(ident)
        if RECONFERIR_S <= 0 or t is None or t.estado == "analisando" or t.suspeita:
            return True
        if agora - t.visto > LACUNA_S:
            return True
        return agora - t.medido >= RECONFERIR_S

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
        t.medido = agora
        self.medidos += 1

        ev = self._decidir(t, agora)
        x = t.notas[-1] if t.notas else None
        if x is None or not self.nomes:
            t.suspeita = False
        elif t.estado == "autorizado":
            # So sai da suspeita com leitura que AUTORIZARIA sozinha (acima
            # do LIMIAR, e o nome dela na frente). Com LIMIAR_BAIXO bastava
            # um estranho parecido acertar 0,27 uma vez para voltar a pular
            # por mais RECONFERIR_S: na simulacao, 16 s com o nome errado.
            i = self.nomes.index(t.nome)
            t.suspeita = not (x[i] >= LIMIAR and int(np.argmax(x)) == i)
        elif t.estado == "desconhecido":
            t.suspeita = bool(float(np.max(x)) >= LIMIAR_BAIXO)
        else:
            t.suspeita = False
        return ev

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
            # O relogio do "tempo ate decidir" tambem recomeca: a pessoa nova
            # nao herda o tempo de quem estava na trilha antes.
            t.comeco = agora
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
        # QUANTO DEMOROU PARA DECIDIR, desde que o rosto apareceu na tela. E a
        # metrica que a banca pediu ("tempo por quadro" nao diz isso: 50 ms por
        # quadro com 14 leituras para decidir sao segundos).
        levou = round(agora - (t.comeco if t.comeco is not None else agora), 2)
        if novo[0] == "autorizado":
            if t.estado != "autorizado" or t.nome != novo[1]:
                antes = (t.estado, t.numero)
                t.estado, t.nome, t.numero = "autorizado", novo[1], None
                self.identificados.add(t.nome)
                ev.append(dict(tipo="autorizado", nome=t.nome,
                               nota=round(melhor, 3), trilha=t.id, quando=agora, levou=levou,
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
                               nota=round(melhor, 3), trilha=t.id, quando=agora, levou=levou,
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
def como_gst(q, largura, altura):
    """O que o cano da caixa faz (gstcam, bordas=True): cabe em largura x
    altura sem esticar, faixa preta centrada no que sobra."""
    import cv2
    h, w = q.shape[:2]
    e = min(largura / w, altura / h)
    nw, nh = int(round(w * e)), int(round(h * e))
    r = cv2.resize(q, (nw, nh), interpolation=cv2.INTER_AREA if e < 1 else cv2.INTER_LINEAR)
    if (nw, nh) == (largura, altura):
        return r
    t = np.zeros((altura, largura, 3), np.uint8)
    y, x = (altura - nh) // 2, (largura - nw) // 2
    t[y:y + nh, x:x + nw] = r
    return t


class Camera:
    def __init__(self, indice, fonte, largura, altura, fps, como_caixa=False, codec=None,
                 ligada=True):
        self.indice, self.fonte = indice, fonte
        # LIGADA = a caixa le e analisa esta camera. Desligada pela pagina, a
        # conexao FECHA: nao decodifica nada e nao gasta CPU.
        self.ligada = ligada
        self.largura, self.altura, self.fps = largura, altura, fps
        # Codec POR camera (CAMERA_ARENA_CODEC / CAMERA_ARENA2_CODEC): a HAIZ
        # manda H.264 e a Intelbras .108 H.265. Um CAM_CODEC so para as duas
        # deixava a segunda em "sem imagem". Vazio = o CAM_CODEC do gstcam.
        self.codec = codec or None
        self.arquivo = not str(fonte).startswith("rtsp") and not str(fonte).isdigit()
        # --como-caixa: video gravado na caixa (aibox/gravar.sh) lido com o
        # MESMO tamanho da prova, um quadro a cada 30/--fps, e no TEMPO do
        # video. Sem isto um .mp4 de 2880x1620 a 30/s e lido inteiro e quadro
        # a quadro: rosto maior e 5x mais leituras que na caixa, e o limiar
        # calibrado no PC nao vale la. O tempo importa porque o juiz e o
        # rastreador contam segundos de relogio: lido mais rapido que a vida
        # real, 3 s de "trilha perdida" virariam 10 s de video.
        self.como_caixa = como_caixa and self.arquivo
        self.pular = 1
        self.passo_s = 0.0      # segundos de video entre dois quadros lidos
        self.proximo = 0.0      # quando (relogio) o proximo quadro e devido
        self.cap = None
        self.ultimo = 0.0
        self.aberta_em = 0.0
        self.acabou = False
        self.quadros = 0
        self.espera = REABRIR_S
        self.rast = Rastreador(f"c{indice}")
        if ligada:
            self.abrir()

    def ligar(self):
        if self.ligada:
            return
        self.ligada, self.acabou, self.ultimo = True, False, 0.0
        self.espera = REABRIR_S
        # O MESMO rastreador: um novo recomecaria a numeracao (c1-1, c1-2...)
        # e o juiz ainda tem as trilhas antigas com esses nomes; quem entrasse
        # herdaria o nome de quem estava na tela antes. Com o mesmo, as trilhas
        # antigas so expiram e as novas ganham numero novo.
        self.abrir()

    def desligar(self):
        if not self.ligada:
            return
        self.ligada = False
        self.fechar()
        self.cap = None

    def abrir(self):
        self.aberta_em = time.monotonic()
        if str(self.fonte).startswith("rtsp"):
            from aibox.gstcam import Gst
            self.cap = Gst(self.fonte, self.largura, self.altura, self.fps, bordas=True,
                           codec=self.codec)
        else:
            import cv2
            f = int(self.fonte) if str(self.fonte).isdigit() else self.fonte
            self.cap = cv2.VideoCapture(f)
            if self.como_caixa and self.fps:
                fps_arq = float(self.cap.get(cv2.CAP_PROP_FPS) or 0)
                if not 1 <= fps_arq <= 120:
                    # Gravado do RTSP, o .mp4 as vezes diz um ritmo sem sentido
                    # (0, ou 90000 da base de tempo): 30/s e o da HAIZ.
                    print(f"[arena] o arquivo diz {fps_arq:.0f} quadros/s; usando 30", flush=True)
                    fps_arq = 30.0
                self.pular = max(1, int(round(fps_arq / self.fps))) if fps_arq > self.fps else 1
                self.passo_s = self.pular / fps_arq
                self.proximo = self.aberta_em
                print(f"[arena] {os.path.basename(str(self.fonte))}: como na caixa, "
                      f"{self.largura}x{self.altura}, 1 quadro a cada {self.pular} "
                      f"(arquivo a {fps_arq:.0f}/s, teto {self.fps}/s)", flush=True)

    def ler(self):
        """(quadro ou None). Arquivo que acabou marca `acabou`."""
        if self.passo_s:
            agora = time.monotonic()
            if agora < self.proximo:
                return None         # ainda nao e a hora deste quadro no video
            # PC mais lento que o video: segue do ponto em que esta, sem
            # tentar recuperar o atraso de uma vez.
            self.proximo = max(self.proximo + self.passo_s, agora - self.passo_s)
        for _ in range(self.pular - 1):
            self.cap.grab()
        ok, q = self.cap.read()
        if ok and self.como_caixa and q.shape[:2] != (self.altura, self.largura):
            q = como_gst(q, self.largura, self.altura)
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
        if not self.ligada:
            return "desligada"
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
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass


def cameras_em_uso(cams, usar):
    """Indices que a caixa deve ler: 0 = todas."""
    return {c.indice for c in cams} if usar == 0 else {usar}


def aplicar_uso(cams, usar):
    """Desliga as cameras fora da escolha ANTES de ligar as outras: duas
    conexoes abertas ao mesmo tempo custam CPU e, na Intelbras, bloqueio."""
    quero = cameras_em_uso(cams, usar)
    for c in cams:
        if c.indice not in quero:
            c.desligar()
    for c in cams:
        if c.indice in quero:
            c.ligar()


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
        # O NOME SO FICA NA TELA ENQUANTO A ULTIMA LEITURA O CONFIRMA. Quem
        # ocupa o lugar de um autorizado herda a trilha, e o juiz so percebe a
        # troca depois de 8 leituras: no teste da pagina (21/10) o nome de um
        # ficou 1 a 2 s em cima do rosto de outro. O placar nao muda com isso.
        if t.notas and t.nome in juiz.nomes:
            x, i = t.notas[-1], juiz.nomes.index(t.nome)
            if x[i] < LIMIAR_BAIXO or int(np.argmax(x)) != i:
                return AMBAR, "conferindo"
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
/* O MESMO VISUAL DA CENTRAL (auditix-central.html), mas tudo daqui: a caixa
   nao tem as fontes do PC, entao fica a fonte do sistema. A pagina so mexe no
   que MUDOU (cada pedaco tem a sua chave): com a CPU da caixa cheia, redesenhar
   tudo a cada 0,7 s seria trabalho jogado fora no navegador do notebook. */
:root{color-scheme:dark;--fundo:#070D0C;--fundo2:#0B1413;--card:#0F1A18;--card2:#132320;
      --linha:#1E3530;--linha2:#284840;--texto:#E4F1EC;--fraco:#9DB8AF;--apagado:#6B8880;
      --verde:#5FBFA0;--verdeluz:rgba(95,191,160,.13);--rubi:#F0707F;--rubiluz:rgba(240,112,127,.14);
      --ambar:#E8C06F;--ambarluz:rgba(232,192,111,.13);
      --mono:ui-monospace,Menlo,Consolas,monospace}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{margin:0;color:var(--texto);font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
     background:radial-gradient(1100px 520px at 85% -10%,rgba(95,191,160,.10),transparent 60%),var(--fundo);min-height:100vh}
button,select{font:inherit;color:inherit}
header{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:16px;flex-wrap:wrap;
       padding:12px 20px;background:rgba(7,13,12,.85);backdrop-filter:blur(8px);border-bottom:1px solid var(--linha)}
.marca{display:flex;align-items:center;gap:10px}
.marca b{font-size:19px;letter-spacing:-.3px}.marca b i{font-style:normal;color:var(--verde)}
.marca small{display:block;color:var(--apagado);font-size:10.5px;letter-spacing:.16em;text-transform:uppercase}
.dir{margin-left:auto;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:7px;padding:5px 11px;border-radius:999px;border:1px solid var(--linha);
      background:var(--fundo2);color:var(--fraco);font-size:12.5px;white-space:nowrap}
.chip i{width:7px;height:7px;border-radius:50%;background:var(--apagado)}
.chip.ok i{background:var(--verde);box-shadow:0 0 0 3px var(--verdeluz)}
.chip.mal{color:var(--rubi)}.chip.mal i{background:var(--rubi);animation:pisca 1s infinite}
.chip.av i{background:var(--ambar)}
.relogio{font:500 16px var(--mono)}
main{display:grid;grid-template-columns:minmax(0,1fr) 370px;gap:18px;padding:18px 20px 30px;max-width:1680px;margin:0 auto}
.palco{position:relative;background:#000;border:1px solid var(--linha2);border-radius:14px;overflow:hidden;line-height:0}
.palco img{width:100%;height:auto;display:block}
.hud{position:absolute;left:12px;right:12px;top:12px;display:flex;justify-content:space-between;align-items:center;
     line-height:1.3;pointer-events:none;font:12.5px var(--mono);color:#fff;text-shadow:0 1px 2px #000}
.vivo{display:inline-flex;align-items:center;gap:7px;padding:4px 9px;border-radius:6px;background:rgba(240,112,127,.92);
      font:600 11px system-ui,sans-serif;letter-spacing:.14em;text-shadow:none}
.vivo i{width:7px;height:7px;border-radius:50%;background:#fff;animation:pisca 1.2s infinite}
.vivo.off{background:rgba(120,135,130,.85)}.vivo.off i{animation:none}
.barra{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
.rot{color:var(--apagado);font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;margin-right:2px}
.btn{border:1px solid var(--linha2);background:var(--card);padding:6px 13px;border-radius:10px;cursor:pointer;font-size:13px}
.btn:hover{border-color:var(--verde)}
.btn.ativa{background:var(--verde);border-color:var(--verde);color:#062019;font-weight:600}
.btn:disabled{opacity:.45;cursor:default}
#usarMsg{color:var(--apagado);font-size:12.5px;font-style:normal}
.lado{display:flex;flex-direction:column;gap:14px}
.card{background:linear-gradient(180deg,var(--card),var(--fundo2));border:1px solid var(--linha);border-radius:14px;padding:15px 16px}
.card h2{display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:12.5px;font-weight:600;letter-spacing:.13em;
         text-transform:uppercase;color:var(--fraco)}
.card h2 small{margin-left:auto;font-weight:400;letter-spacing:0;text-transform:none;color:var(--apagado);font-size:12px}
.placar{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.num{position:relative;overflow:hidden;background:linear-gradient(180deg,var(--card),var(--fundo2));border:1px solid var(--linha);
     border-radius:14px;padding:14px 16px}
.num::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--verde)}
.num.rubi::before{background:var(--rubi)}
.num span{color:var(--apagado);font-size:11px;letter-spacing:.13em;text-transform:uppercase}
.num b{display:block;font:600 44px/1.1 system-ui,sans-serif;letter-spacing:-1px;font-variant-numeric:tabular-nums;color:var(--verde)}
.num b small{font-size:20px;color:var(--apagado);letter-spacing:0;font-weight:500}
.num.rubi b{color:var(--rubi)}
.num.pulsa{animation:acende .9s ease-out}
.pessoas{display:flex;flex-direction:column;gap:6px}
.p{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;background:var(--fundo2);border:1px solid transparent}
.p .av{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:var(--card2);color:var(--apagado);
       font-weight:700;font-size:13px}
.p b{font-weight:600}
.p em{margin-left:auto;font-style:normal;font-size:12px;color:var(--apagado)}
.p.sim{border-color:rgba(95,191,160,.4);background:linear-gradient(90deg,var(--verdeluz),var(--fundo2))}
.p.sim .av{background:var(--verde);color:#062019}
.p.sim em{color:var(--verde);font-weight:600}
.desc{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.desc span{padding:3px 9px;border-radius:999px;background:var(--rubiluz);color:var(--rubi);font:600 12px var(--mono)}
.cams{display:flex;flex-direction:column;gap:8px}
.cam{display:flex;align-items:center;gap:8px;font-size:13.5px}
.cam i{width:8px;height:8px;border-radius:50%;background:var(--apagado)}
.cam.ok i{background:var(--verde);box-shadow:0 0 0 3px var(--verdeluz)}
.cam.mal i{background:var(--rubi);animation:pisca 1s infinite}
.cam em{margin-left:auto;font:12.5px var(--mono);font-style:normal;color:var(--fraco)}
.desemp{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.d{background:var(--fundo2);border:1px solid var(--linha);border-radius:11px;padding:9px 12px}
.d span{display:block;color:var(--apagado);font-size:10.5px;letter-spacing:.13em;text-transform:uppercase}
.d b{display:block;font:500 19px var(--mono);margin:2px 0 3px}
.d svg{display:block;width:100%;height:26px}
.ev{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:5px;max-height:300px;overflow:auto}
.ev li{padding:7px 10px;border-radius:9px;background:var(--fundo2);font-size:12.5px;border-left:3px solid var(--linha2);
       color:var(--fraco);font-family:var(--mono)}
.ev li.a{border-left-color:var(--verde);color:var(--texto)}
.ev li.x{border-left-color:var(--rubi);color:var(--texto)}
.ev li.t{border-left-color:var(--ambar)}
#cad select{flex:1;background:var(--fundo2);border:1px solid var(--linha2);border-radius:10px;padding:6px 10px}
#cadMsg{color:var(--fraco);font-size:13px;margin-top:8px}
body.morto .vivo{background:rgba(120,135,130,.85)}
@keyframes pisca{50%{opacity:.25}}
@keyframes acende{from{box-shadow:0 0 0 0 rgba(95,191,160,.55)}to{box-shadow:0 0 0 14px rgba(95,191,160,0)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
@media (max-width:980px){main{grid-template-columns:1fr;padding:14px 16px}header{padding:10px 16px}
  /* No celular o placar vem logo depois da imagem, e os eventos por ultimo. */
  main>section{display:contents}.lado{order:2}#cardEv{order:3;margin-top:0!important}}
</style>
<header>
  <div class="marca">
    <svg width="32" height="32" viewBox="0 0 34 34" aria-hidden="true"><rect x="1" y="1" width="32" height="32" rx="9" fill="#0F1A18" stroke="#284840"/><path d="M9 23 17 9l8 14" fill="none" stroke="#5FBFA0" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="17" cy="20" r="2.4" fill="#7FE0BF"/></svg>
    <div><b>Audit<i>ix</i> IA</b><small>arena · identificação na AI BOX</small></div>
  </div>
  <div class="dir">
    <span class="chip" id="conexao"><i></i><span>conectando…</span></span>
    <span class="chip" id="cmodo" hidden><i></i><span>modo preparo</span></span>
    <span class="relogio" id="tempo">--:--</span>
  </div>
</header>
<main>
  <section>
    <div class="barra" id="usar" hidden><span class="rot">câmera</span><span id="usarBotoes"></span><em id="usarMsg"></em></div>
    <div class="palco"><img src="/video" alt="imagem ao vivo das câmeras">
      <div class="hud"><span class="vivo" id="vivo"><i></i>AO VIVO</span><span id="hud"></span></div></div>
    <div class="card" id="cardEv" style="margin-top:14px"><h2>Eventos<small>mais novo em cima</small></h2><ol class="ev" id="ev"></ol></div>
  </section>
  <aside class="lado">
    <div class="placar">
      <div class="num" id="cAut"><span>autorizados</span><b id="nAut">--</b></div>
      <div class="num rubi" id="cDesc"><span>desconhecidos</span><b id="nDesc">--</b></div>
    </div>
    <div class="card"><h2>Galeria<small id="galS"></small></h2><div class="pessoas" id="pessoas"></div>
      <div class="desc" id="descs"></div></div>
    <div class="card"><h2>Câmeras</h2><div class="cams" id="cams"></div></div>
    <div class="card"><h2>Desempenho</h2><div class="desemp">
      <div class="d"><span>leituras/s</span><b id="qps">--</b><svg id="sq" viewBox="0 0 120 26" preserveAspectRatio="none"></svg></div>
      <div class="d"><span>ms por quadro</span><b id="ms">--</b><svg id="sm" viewBox="0 0 120 26" preserveAspectRatio="none"></svg></div>
      <div class="d" id="linhaVideo" hidden><span>vídeo</span><b id="vqps">--</b></div></div></div>
    <div class="card" id="cad" hidden><h2>Cadastro<small>modo preparo</small></h2>
      <div style="display:flex;gap:8px"><select id="cadNome"></select><button class="btn ativa" id="cadBotao" type="button">Cadastrar</button></div>
      <div id="cadMsg"></div></div>
  </aside>
</main>
<script>
const $ = i => document.getElementById(i);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
/* So escreve no DOM quando o pedaco mudou. */
const chaves = {};
function trocar(id, chave, html){
  if(chaves[id] === chave) return false;
  chaves[id] = chave; $(id).innerHTML = html; return true;
}
const H = {qps: [], ms: []};
function linha(id, xs, cor){
  if(xs.length < 2) return;
  const max = Math.max(...xs) * 1.15 || 1;
  const pts = xs.map((v, i) => (i / (xs.length - 1) * 120).toFixed(1) + ',' + (25 - v / max * 23).toFixed(1)).join(' ');
  $(id).innerHTML = '<polyline points="0,26 ' + pts + ' 120,26" fill="' + cor + '" fill-opacity=".12"/>' +
    '<polyline points="' + pts + '" fill="none" stroke="' + cor + '" stroke-width="1.6" vector-effect="non-scaling-stroke"/>';
}
let antes = {aut: -1, desc: -1}, falhas = 0;
setInterval(async () => {
  let e;
  try{ e = await (await fetch('/estado', {cache: 'no-store'})).json(); falhas = 0; }
  catch(_){
    if(++falhas >= 3){
      document.body.classList.add('morto');
      $('conexao').className = 'chip mal'; $('conexao').lastElementChild.textContent = 'sem conexão com a caixa';
      $('vivo').className = 'vivo off';
    }
    return;
  }
  document.body.classList.remove('morto');
  $('vivo').className = 'vivo';
  const camOk = e.cameras.some(c => c.estado === 'ok');
  $('conexao').className = 'chip ' + (camOk ? 'ok' : 'mal');
  $('conexao').lastElementChild.textContent = camOk ? 'identificando' : 'nenhuma câmera com imagem';
  $('tempo').textContent = e.tempo;
  $('cmodo').hidden = !e.cadastro;

  /* O placar. O numero que mudou acende uma vez. */
  const na = e.autorizados.length, nd = e.desconhecidos.length;
  $('nAut').innerHTML = na + '<small> de ' + e.total_autorizados + '</small>';
  $('nDesc').textContent = nd;
  if(antes.aut >= 0 && na !== antes.aut){ $('cAut').classList.remove('pulsa'); void $('cAut').offsetWidth; $('cAut').classList.add('pulsa'); }
  if(antes.desc >= 0 && nd !== antes.desc){ $('cDesc').classList.remove('pulsa'); void $('cDesc').offsetWidth; $('cDesc').classList.add('pulsa'); }
  antes = {aut: na, desc: nd};

  const gal = e.galeria || e.autorizados;
  const sim = new Set(e.autorizados);
  trocar('pessoas', gal.join('|') + '#' + e.autorizados.join('|'), gal.map(n =>
    '<div class="p' + (sim.has(n) ? ' sim' : '') + '"><span class="av">' + esc(n.slice(0, 1).toUpperCase()) + '</span><b>' + esc(n) +
    '</b><em>' + (sim.has(n) ? '✓ identificado' : 'aguardando') + '</em></div>').join(''));
  $('galS').textContent = gal.length + ' autorizado' + (gal.length === 1 ? '' : 's');
  trocar('descs', e.desconhecidos.join(','), e.desconhecidos.map(d => '<span>desconhecido #' + d + '</span>').join(''));

  trocar('cams', JSON.stringify(e.cameras.map(c => [c.indice, c.estado, c.qps.toFixed(1)])), e.cameras.map(c =>
    '<div class="cam ' + (c.estado === 'ok' ? 'ok' : c.estado === 'desligada' ? '' : 'mal') + '"><i></i>câmera ' + c.indice +
    '<em>' + esc(c.estado) + (c.estado === 'desligada' ? '' : ' · ' + c.qps.toFixed(1) + '/s') + '</em></div>').join(''));

  H.qps.push(e.qps); H.ms.push(e.ms); if(H.qps.length > 60){ H.qps.shift(); H.ms.shift(); }
  $('qps').textContent = e.qps.toFixed(1);
  $('ms').textContent = Math.round(e.ms);
  linha('sq', H.qps, '#5FBFA0'); linha('sm', H.ms, '#7FB2E8');
  $('hud').textContent = e.qps.toFixed(1) + ' leituras/s · ' + Math.round(e.ms) + ' ms';
  if(e.video_qps != null){ $('linhaVideo').hidden = false; $('vqps').textContent = e.video_qps.toFixed(1) + '/s'; }

  trocar('ev', e.eventos.join('\\n'), e.eventos.map(x =>
    '<li class="' + (/AUTORIZADO/.test(x) ? 'a' : /ALERTA/.test(x) ? 'x' : /troca|deixou|camera/.test(x) ? 't' : '') + '">' + esc(x) + '</li>').join('') ||
    '<li>nada ainda</li>');

  /* ESCOLHER A CAMERA. So com duas ou mais. Muda o que a caixa LE e
     analisa, nao so o que a pagina mostra: a camera fora da escolha fecha. */
  if(e.cameras.length > 1){
    $('usar').hidden = false;
    const op = [[0, 'as duas']].concat(e.cameras.map(c => [c.indice, 'câmera ' + c.indice]));
    trocar('usarBotoes', op.map(o => o[0]).join(',') + '|' + e.usar + '|' + (e.troca_espera > 0), op.map(([v, t]) =>
      '<button type="button" class="btn' + (v === e.usar ? ' ativa' : '') + '" data-usar="' + v + '"' +
      (e.troca_espera > 0 ? ' disabled' : '') + '>' + t + '</button>').join(' '));
    $('usarMsg').textContent = e.troca_msg || '';
  }
  if(e.cadastro){
    $('cad').hidden = false;
    const sel = $('cadNome');
    if(sel.options.length !== e.cadastro.nomes.length)
      sel.innerHTML = e.cadastro.nomes.map(n => '<option>' + esc(n) + '</option>').join('');
    $('cadBotao').disabled = e.cadastro.ativo;
    $('cadMsg').textContent = e.cadastro.msg || '';
  }
}, 700);
$('usarBotoes').addEventListener('click', async ev => {
  const b = ev.target.closest('button');
  if(!b || b.disabled) return;
  $('usarMsg').textContent = 'trocando…';
  try{
    await fetch('/usar', {method: 'POST', headers: {'Content-Type': 'application/json'},
                          body: JSON.stringify({camera: Number(b.dataset.usar)})});
  }catch(_){ $('usarMsg').textContent = 'a caixa não respondeu'; }
});
$('cadBotao').addEventListener('click', async () => {
  $('cadBotao').disabled = true;
  $('cadMsg').textContent = 'começando…';
  try{
    await fetch('/cadastrar', {method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify({nome: $('cadNome').value})});
  }catch(_){ $('cadMsg').textContent = 'a caixa não respondeu'; }
});
</script>
""".encode("utf-8")


class Tela:
    """MJPEG + JSON, servidos pela caixa. O mesmo jeito do aibox/vivo.py."""

    def __init__(self, porta, preparo=False):
        self.jpeg, self.estado, self.clientes = None, {}, 0
        self.preparo, self.pedido = preparo, None
        self.pedido_usar = None     # camera pedida pela pagina (0 = todas)
        self._trava = threading.Lock()
        tela = self

        class Mao(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path.startswith("/usar"):
                    return self._usar()
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

            def _usar(self):
                # Fora do modo preparo de proposito: escolher a camera e
                # montar a estacao, nao cadastrar nem mexer no juiz. Quem
                # aplica e o laco (ele e o dono das cameras).
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    tela.pedido_usar = max(0, int(json.loads(self.rfile.read(n) or b"{}")
                                                  .get("camera", 0)))
                    corpo, cod = b'{"ok": true}', 200
                except Exception:
                    corpo, cod = b'{"erro": "camera invalida"}', 400
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


def tempo_ate_decidir(eventos):
    """Mediana e pior tempo entre o rosto aparecer e virar AUTORIZADO ou
    DESCONHECIDO. None sem decisao nenhuma."""
    t = [e["levou"] for e in eventos
         if e.get("tipo") in ("autorizado", "desconhecido") and e.get("levou") is not None]
    if not t:
        return None
    return dict(mediana=round(float(np.median(t)), 2), pior=round(float(max(t)), 2),
                decisoes=len(t))


def conferencia(c):
    """(texto, dict) do NPU_CONFERIR. Serve para a NPU se: cosseno do ArcFace
    >= 0,98 no pior caso, nota contra a galeria mudando <= 0,02, e o YuNet da
    NPU dando pelo menos tantas leituras boas quanto o da CPU."""
    d = dict(rostos=len(c["cos"]), quadros_comparados=c["quadros"],
             leituras_boas_cpu=c["boas_cpu"], leituras_boas_npu=c["boas_npu"])
    partes = []
    if c["cos"]:
        d.update(cos_medio=round(float(np.mean(c["cos"])), 4),
                 cos_pior=round(float(min(c["cos"])), 4))
        partes.append(f"ArcFace cos medio {d['cos_medio']:.4f}, pior {d['cos_pior']:.4f}"
                      f" ({d['rostos']} rostos)")
    if c["dnota"]:
        d["nota_muda_max"] = round(float(max(c["dnota"])), 3)
        partes.append(f"nota muda ate {d['nota_muda_max']:.3f}")
    if c["quadros"]:
        partes.append(f"YuNet leituras boas CPU {c['boas_cpu']} x NPU {c['boas_npu']}"
                      f" em {c['quadros']} quadros")
    if c["nota_dif"]:
        d["yunet_nota_npu_menos_cpu"] = round(float(np.mean(c["nota_dif"])), 3)
        partes.append(f"nota do detector NPU-CPU {d['yunet_nota_npu_menos_cpu']:+.3f}")
    return ("; ".join(partes) or "nada medido ainda (ninguem na frente da camera?)"), d


def main():
    from aibox.marca import letreiro
    letreiro("arena")
    from aibox.sala import carregar_env
    carregar_env()
    p = argparse.ArgumentParser(description="Auditix IA, modo arena (so rosto)")
    p.add_argument("--usar", type=int, default=int(_num("ARENA_USAR", "0")),
                   help="qual camera ler ao subir: 0 = todas (padrao), 1 ou 2. "
                        "A pagina troca depois")
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
    p.add_argument("--como-caixa", action="store_true",
                   help="video gravado (aibox/gravar.sh): le no tamanho --largura x "
                        "--altura e no ritmo --fps, como a caixa le a camera")
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
    # VERSAO NPU: o YuNet vai para a NPU (tamanho fixo 1280x736, entao o
    # ARENA_DETECCAO deixa de valer) e o ArcFace tambem, se o arcface_pc.dlc
    # (por canal, cosseno 0,999 com a CPU: a galeria vale) estiver na caixa.
    # NPU_ARCFACE=0 deixa o ArcFace na CPU.
    from aibox import npu
    # NPU_CONFERIR=1: SO PARA O LABORATORIO. Cada rosto bom tambem e medido
    # pelo ArcFace da CPU (cosseno e nota contra a galeria, NPU x CPU), e a
    # cada 10 quadros o YuNet da CPU procura no MESMO quadro (leituras boas de
    # um e do outro). E o unico jeito de medir a quantizacao das ATIVACOES:
    # no GitHub o SNPE roda na CPU dele, que desquantiza a rede e faz a conta
    # em float. Fica mais lento: nao usar na prova.
    conferir = os.environ.get("NPU_CONFERIR", "0") == "1"
    detect_cpu, medir_cpu = motor.detect, medir
    conf = dict(cos=[], dnota=[], boas_cpu=0, boas_npu=0, quadros=0, nota_dif=[])
    det_npu = npu.tentar(npu.DetectorNPU, "YuNet")
    if det_npu is not None:
        motor.detect = det_npu.detect
    pc_ok = os.path.exists(os.path.join(npu.NPU_DIR, "arcface_pc.dlc"))
    if modelo == "arcface" and os.environ.get("NPU_ARCFACE", "1" if pc_ok else "0") == "1":
        arc_npu = npu.tentar(npu.ArcFaceNPU, "ArcFace")
        if arc_npu is not None:
            medir = arc_npu.embedding
    if conferir:
        print("[arena] NPU_CONFERIR=1: medindo NPU contra CPU (mais lento; so no "
              "laboratorio)", flush=True)
    juiz = Juiz(nomes, M, dono)
    codecs = [os.environ.get("CAMERA_ARENA_CODEC" if i == 0 else f"CAMERA_ARENA{i + 1}_CODEC")
              for i in range(len(fontes))]
    # ARENA_USAR (ou --usar): qual camera a caixa le ao subir. 0 = todas, que
    # e o de sempre. A pagina troca depois, com um clique.
    usar = a.usar if 0 <= a.usar <= len(fontes) else 0
    if usar:
        print(f"[arena] usando so a camera {usar} (ARENA_USAR); a pagina troca", flush=True)
    cams = [Camera(i + 1, f, a.largura, a.altura, a.fps or None, a.como_caixa, codecs[i],
                   ligada=(usar in (0, i + 1)))
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
    if RECONFERIR_S > 0:
        print(f"[arena] quem ja foi decidido e medido de novo a cada {RECONFERIR_S:g} s "
              "(ARENA_RECONFERIR_S); 0 mede todo quadro", flush=True)
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

    troca_em, troca_msg = -TROCA_MIN_S, ""
    while not parar.is_set():
        agora = time.monotonic()
        if a.segundos and agora - inicio >= a.segundos:
            break
        if all(c.acabou or not c.ligada for c in cams):
            break
        if tela.pedido_usar is not None:
            pedido, tela.pedido_usar = tela.pedido_usar, None
            if pedido > len(cams) or len(cams) < 2:
                troca_msg = f"nao existe a camera {pedido}"
            elif pedido == usar:
                troca_msg = ""
            elif agora - troca_em < TROCA_MIN_S:
                troca_msg = (f"espere {TROCA_MIN_S - (agora - troca_em):.0f} s entre trocas "
                             "(a Intelbras bloqueia conexoes seguidas)")
            else:
                usar, troca_em = pedido, agora
                aplicar_uso(cams, usar)
                quadro_tela.clear()
                troca_msg = "trocado: " + ("as duas" if usar == 0 else f"so a camera {usar}")
                txt = f"{relogio(agora - inicio)} camera: " + \
                      ("as duas" if usar == 0 else f"so a {usar}")
                log.append(txt)
                print(f"[arena] {txt} (pela pagina)", flush=True)
        trabalhou = False
        if tela.pedido and coleta is None:
            nome, tela.pedido = tela.pedido, None
            if nome in juiz.nomes:
                coleta = Coleta(nome, agora)
                print(f"[arena] cadastro pelo botao: {nome}", flush=True)
            else:
                cadastro_msg = f"{nome} nao esta na galeria"
        for cam in cams:
            if not cam.ligada:
                continue
            img = cam.ler()
            if img is None:
                cam.talvez_reabrir(agora)
                continue
            trabalhou = True
            t0 = time.monotonic()
            dcfg.DETECT_WIDTH = a.deteccao or img.shape[1]
            linhas = motor.detect(img)
            if conferir and det_npu is not None and cam.quadros % 10 == 1:
                outras = detect_cpu(img)
                conf["quadros"] += 1
                conf["boas_npu"] += sum(leitura_boa(l)[0] for l in linhas)
                conf["boas_cpu"] += sum(leitura_boa(l)[0] for l in outras)
                for lc in outras:
                    perto = [ln for ln in linhas
                             if abs(ln[0] + ln[2] / 2 - lc[0] - lc[2] / 2) < lc[2] / 2
                             and abs(ln[1] + ln[3] / 2 - lc[1] - lc[3] / 2) < lc[3] / 2]
                    if perto:
                        conf["nota_dif"].append(float(perto[0][14] - lc[14]))
            caixas = [tuple(float(x) for x in l[:4]) for l in linhas]
            ids = cam.rast.associar(caixas, t0)
            vistos, rostos = [], []
            for l, ident, cx in zip(linhas, ids, caixas):
                # Antes de atualizar o visto: a lacuna desde a ultima vez na
                # tela e uma das travas do RECONFERIR_S.
                precisa = coleta is not None or juiz.precisa_medir(ident, t0 - inicio)
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
                # Por padrao TODO rosto bom e medido, mesmo de quem ja foi
                # decidido. Medir menos quem ja tem nome foi tentado (20/10)
                # sem trava e quebrou a troca de trilha: a pessoa nova que
                # ocupa o lugar herdava o nome (4 de 4 virou 1 de 4). Com
                # ARENA_RECONFERIR_S, as travas estao em Juiz.precisa_medir.
                v = None
                if boa and not precisa:
                    juiz.poupados += 1
                elif boa:
                    v = medir(img, l)
                    if conferir and medir is not medir_cpu:
                        u = np.asarray(v, np.float32)
                        u = u / (np.linalg.norm(u) + 1e-9)
                        w = np.asarray(medir_cpu(img, l), np.float32)
                        w = w / (np.linalg.norm(w) + 1e-9)
                        conf["cos"].append(float(u @ w))
                        if len(juiz.M):
                            conf["dnota"].append(float(np.abs(juiz.M @ u - juiz.M @ w).max()))
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
                               f" em {ev['levou']:.1f} s"
                               + (f", era o desconhecido #{ev['era_desconhecido']}"
                                  if ev.get("era_desconhecido") else "")
                               if ev["tipo"] == "autorizado" else
                               f"{relogio(t0 - inicio)} ALERTA desconhecido #{ev['numero']}"
                               f" em {ev['levou']:.1f} s"
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
            galeria=juiz.nomes,
            desconhecidos=r["desconhecidos"],
            cameras=[dict(indice=c.indice, estado=c.estado(agora),
                          qps=len(qps_cam[c.indice]) / 5.0) for c in cams],
            qps=sum(len(v) for v in qps_cam.values()) / 5.0,
            ms=float(np.mean(tempos)) if tempos else 0.0,
            tempo=relogio(agora - inicio), eventos=log[-8:][::-1],
            video_qps=fluido.qps(agora) if fluido is not None else None,
            usar=usar, troca_msg=troca_msg,
            troca_espera=max(0.0, TROCA_MIN_S - (agora - troca_em)) if len(cams) > 1 else 0.0,
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
            if conferir:
                print("[conferir] " + conferencia(conf)[0], flush=True)
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
        tempo_ate_decidir_s=tempo_ate_decidir(juiz.eventos),
        reconferir_s=RECONFERIR_S, rostos_medidos=juiz.medidos,
        rostos_poupados=juiz.poupados,
        conferencia_npu=conferencia(conf)[1] if conferir else None,
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
    td = resultado["tempo_ate_decidir_s"]
    if td:
        print(f"  tempo ate decidir:         mediana {td['mediana']} s, pior {td['pior']} s"
              f" ({td['decisoes']} decisoes)")
    if RECONFERIR_S > 0:
        tot = juiz.medidos + juiz.poupados
        print(f"  rostos medidos:            {juiz.medidos} de {tot}"
              f" ({juiz.poupados} seguidos sem medir, ARENA_RECONFERIR_S={RECONFERIR_S:g})")
    if conferir:
        print(f"  NPU contra CPU:            {conferencia(conf)[0]}")
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
