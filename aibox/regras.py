"""As tres camadas de analise, em Python, para rodar dentro da AIBOX.

    queda    -> rede treinada (4.509 clipes) + regra geometrica, lado a lado
    corrida  -> regra pura, em alturas de corpo por segundo
    briga    -> regra pura, com as features do DIFEM (arXiv 2412.05386)

E UM PORTE, NAO UMA REESCRITA. Cada limiar aqui e o mesmo de auditix-sala.html,
com o mesmo nome, para que as duas versoes possam ser lidas lado a lado e a
divergencia aparecer. Os numeros nao foram reajustados para "ficar bom no
Python": foram medidos uma vez, no dataset, e mexer neles aqui criaria duas
verdades sobre o mesmo sistema.

HONESTIDADE SOBRE CORRIDA E BRIGA: sao REGRAS, nao modelos. A rede de queda tem
4.509 clipes por tras; estas duas tem zero. O caminho para virarem modelo e o
RWF-2000, e ate la elas se chamam regra — no codigo, na tela e no pitch.
"""
import math

from . import medidas, rede

# ---- memoria e maturidade --------------------------------------------------
HIST_MS = 2500        # memoria de movimento de cada pessoa
ANOM_IDADE = 2000     # uma trilha recem-nascida nao tem "antes" para comparar

# ---- queda -----------------------------------------------------------------
QUEDA_ANG = 55        # graus fora da vertical
QUEDA_CAI = 0.35      # queda do quadril em ALTURAS DE CORPO
QUEDA_SEG = 1200      # ms deitado para virar alerta
QUEDA_JANELA = 500    # ms: um tombo cabe aqui, um agachamento nao
QUEDA_EIXO = 0.60
QUEDA_PROP = 1.2
QUEDA_PROP_SO = 1.4
QUEDA_BAIXO = 0.40
QUEDA_AMOSTRAS = 8

# ---- corrida ---------------------------------------------------------------
CORRE_VEL = 1.20      # alturas de corpo por segundo
CORRE_JANELA = 700    # ms de caminho somado
CORRE_SEG = 600       # ms acima do limiar antes de acusar
CORRE_PASSO = 100     # ms entre amostras: abaixo disso soma-se tremor

# ---- briga -----------------------------------------------------------------
BRIGA_PERTO = 1.6
BRIGA_TOQUE = 0.55
BRIGA_GOLPE = 1.80
BRIGA_TOQUES = 2
BRIGA_JANELA = 2500
GOLPE_MEM = 250
BRIGA_GAP = 250
BRIGA_SOLTA = 0.6
BRIGA_SEG = 600

# ---- parado ----------------------------------------------------------------
PARADO_JANELA = 5000
PARADO_MIN = 0.005


class Trilha:
    """Uma pessoa acompanhada ao longo do tempo.

    O acompanhamento e o que separa "ha um corpo deitado" de "este corpo caiu":
    sem memoria do antes, um sofa e uma pessoa no chao sao a mesma imagem.
    """

    def __init__(self, ident, nasceu):
        self.id = ident
        self.nasceu = nasceu
        self.hist = []
        self.lento = []
        self.topos = {}
        self.quedaDesde = 0
        self.correDesde = 0
        self.alertaDe = {}
        self.qx = self.qy = self.ox = self.oy = None
        self.altura = self.ang = self.baixo = self.prop = 0.0
        self.velocidade = 0.0
        self.notaQueda = 0.0
        self.foraDoTreino = 0.0
        self.analisavel = False
        self.parado = False
        self.fps = 0
        self.regua = None
        self.visto = nasceu

    # -- utilidades ---------------------------------------------------------
    @property
    def firme(self):
        """Uma trilha nova nao tem passado, e queda e uma afirmacao sobre o
        passado. Acusar antes disso e acusar o proprio nascimento da trilha."""
        return (self.visto - self.nasceu) >= ANOM_IDADE

    def _janela(self, agora, ms):
        return [h for h in self.hist if agora - h["t"] < ms]

    # -- o quadro -----------------------------------------------------------
    def ver(self, kp, asp, agora):
        """Um quadro de 17 pontos. Devolve a lista de alertas deste quadro."""
        self.visto = agora
        g = medidas.geometria(kp, asp)
        if g is None:
            # Sem ombro ou sem quadril nao ha tronco, e tronco chutado vira
            # alarme falso. A camada cala e DIZ que calou, em vez de afirmar
            # seguranca que nao tem como verificar.
            self.analisavel = False
            self.quedaDesde = self.correDesde = 0
            self.qx = self.qy = self.ox = self.oy = None
            return []
        self.analisavel = True
        self.regua = g["regua"]

        h = dict(t=agora, qx=g["hx"], qy=g["hy"], ang=g["ang"],
                 altura=g["altura"], eixo=g["eixo"], ombro=g["ombro"],
                 prop=g["prop"],
                 px=(g["pxx"], g["pxy"]), pd=(g["pdx"], g["pdy"]),
                 hx=g["hx"], hy=g["hy"])
        self.hist.append(h)
        self.hist = [x for x in self.hist if agora - x["t"] < HIST_MS]

        self.altura = g["altura"]
        self.qx, self.qy = g["hx"], g["hy"]
        self.ang, self.prop = g["ang"], g["prop"]
        # O meio dos ombros e a mira da briga: e dele que sai o centro do tronco
        # alheio, que e o alvo contra o qual o avanco do punho e medido.
        self.ox = (kp[medidas.OMBRO_E][0] + kp[medidas.OMBRO_D][0]) / 2
        self.oy = (kp[medidas.OMBRO_E][1] + kp[medidas.OMBRO_D][1]) / 2

        self._parado(agora)
        alertas = []
        alertas += self._queda(agora)
        alertas += self._corrida(agora, asp)
        return alertas

    # -- parado -------------------------------------------------------------
    def _parado(self, agora):
        """Objeto parado nao cai. Sem isto, uma mochila no chao que o detector
        insiste em achar que e gente vira queda todo dia no mesmo horario."""
        if not self.lento or agora - self.lento[-1]["t"] > 250:
            self.lento.append(dict(t=agora, x=self.qx, y=self.qy, a=self.altura))
        self.lento = [x for x in self.lento if agora - x["t"] < PARADO_JANELA]
        if len(self.lento) >= 8 and agora - self.lento[0]["t"] >= PARADO_JANELA * 0.8:
            xs = [x["x"] for x in self.lento]
            ys = [x["y"] for x in self.lento]
            alt = max(x["a"] for x in self.lento)
            amp = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / alt if alt > 1e-6 else 0
            self.parado = amp < PARADO_MIN

    # -- queda --------------------------------------------------------------
    def _queda(self, agora):
        jan_rede = self._janela(agora, 1000)
        # A taxa de quadros e MEDIDA, nao presumida: a janela e de 1s, entao o
        # numero de amostras nela e o fps real desta maquina. O treino foi a 30,
        # e duas das 12 entradas dividem por tempo.
        self.fps = len(jan_rede)
        car = None
        if len(jan_rede) >= QUEDA_AMOSTRAS:
            # `minimo` igual ao piso do navegador, e nao ao do treino: ver o
            # porque em treino/extrair.py. Sem ele a rede ficaria muda abaixo
            # de 15 quadros por segundo, e muda sem avisar.
            car = medidas.caracteristicas(jan_rede, 0, len(jan_rede),
                                          fps=self.fps, minimo=QUEDA_AMOSTRAS)
        self.foraDoTreino = rede.distancia_do_treino(car) if car is not None else 0.0
        # Fora do mundo do modelo a nota dele nao vale. A geometria continua.
        self.notaQueda = (rede.nota(car)
                          if car is not None and self.foraDoTreino <= rede.FORA else 0.0)

        jan = self._janela(agora, 900)
        if not jan:
            return []
        altura_max = max(x["altura"] for x in jan)
        curta = self._janela(agora, QUEDA_JANELA)
        antes_q = min(x["qy"] for x in curta) if curta else self.qy
        caiu = (self.qy - antes_q) / max(altura_max, 1e-6) > QUEDA_CAI
        eixo_max = max(x["eixo"] for x in jan)
        eixo = self.hist[-1]["eixo"]
        cx = self.prop

        # A REGUA DA PESSOA, com as duas travas que o navegador aprendeu na
        # marra (ver o comentario longo em auditix-sala.html): cada regua tem o
        # seu proprio topo, porque as tres nao dao o mesmo numero; e a
        # referencia e o TERCEIRO maior, nao o maior, porque um unico quadro com
        # ponto inventado nao pode virar regua para o resto da trilha.
        topo = self.topos.setdefault(self.regua, [])
        topo.append(self.altura)
        topo.sort(reverse=True)
        del topo[5:]
        self.alturaTopo = topo[min(2, len(topo) - 1)]
        self.baixo = self.altura / max(self.alturaTopo, 1e-6)

        geo = (((self.ang > QUEDA_ANG or eixo < eixo_max * QUEDA_EIXO
                 or cx > QUEDA_PROP) and caiu)
               or cx > QUEDA_PROP_SO or self.baixo < QUEDA_BAIXO)
        pela_rede = self.notaQueda >= rede.LIMIAR

        if (geo or pela_rede) and not self.quedaDesde:
            self.quedaDesde = agora
            self.eixoAntes = eixo_max
            self.porRede = not geo
            # congelados no instante em que o relogio arma: 1,2s depois estes
            # numeros ja sao outros e nao explicam mais nada
            self.angQueda = self.ang
            self.notaArmou = self.notaQueda
            self.foraQueda = self.foraDoTreino
            self.baixoQueda = self.baixo
            self.propQueda = cx

        # Depois do tombo o que se cobra e so continuar deitado: o tombo ja saiu
        # da janela, e cobrar as duas coisas junto faria o alerta nunca sair.
        no_chao = (self.ang > QUEDA_ANG
                   or eixo < getattr(self, "eixoAntes", eixo_max) * QUEDA_EIXO
                   or cx > QUEDA_PROP or self.baixo < QUEDA_BAIXO * 1.2
                   or self.notaQueda >= rede.LIMIAR)
        if self.quedaDesde and not no_chao:
            self.quedaDesde = 0
        if self.quedaDesde and agora - self.quedaDesde > QUEDA_SEG:
            return self._anomalia("queda", agora, self._porque_queda())
        return []

    def _porque_queda(self):
        if getattr(self, "porRede", False):
            base = f"rede {self.notaArmou:.2f} (limiar {rede.LIMIAR:.2f})"
        else:
            base = (f"geometria: tronco {round(self.angQueda)}°, "
                    f"caixa {self.propQueda:.1f}, "
                    f"altura {round(self.baixoQueda * 100)}% da dele")
        fora = "" if self.foraQueda <= rede.FORA else " (FORA, rede ignorada)"
        return (f"{base} · rede {self.notaArmou:.2f} · "
                f"distância do treino {self.foraQueda:.1f}{fora}")

    # -- corrida ------------------------------------------------------------
    def _corrida(self, agora, asp):
        jan = self._janela(agora, CORRE_JANELA)
        vel = 0.0
        if len(jan) >= 3:
            # Reduzida a ~100ms de proposito: o ponto treme alguns pixels a cada
            # quadro, e somar o caminho a 30fps faz o tremor virar velocidade
            # que nao existe. Uma pessoa parada "correria".
            am = [jan[0]]
            for h in jan:
                if h["t"] - am[-1]["t"] >= CORRE_PASSO:
                    am.append(h)
            if len(am) >= 3:
                # Somado passo a passo, nao de ponta a ponta: quem corre de um
                # lado para o outro e volta tem deslocamento liquido zero.
                caminho = sum(math.hypot((am[i]["qx"] - am[i - 1]["qx"]) * asp,
                                         am[i]["qy"] - am[i - 1]["qy"])
                              for i in range(1, len(am)))
                dt = (am[-1]["t"] - am[0]["t"]) / 1000.0
                reg = max(h["altura"] for h in am)
                if dt > 0 and reg > 1e-6:
                    vel = caminho / reg / dt
        self.velocidade = vel

        # Correr e coisa de quem esta EM PE. Sem esta trava a queda dispara
        # corrida junto: o tombo e o movimento mais rapido que uma pessoa faz.
        em_pe = self.ang < 40 and self.baixo > 0.72 and not self.quedaDesde
        if vel > CORRE_VEL and em_pe:
            if not self.correDesde:
                self.correDesde = agora
            elif agora - self.correDesde > CORRE_SEG:
                return self._anomalia(
                    "corrida", agora,
                    f"deslocamento de {vel:.2f} alturas de corpo por segundo "
                    f"(limiar {CORRE_VEL}), corpo em pé por "
                    f"{round(agora - self.correDesde)}ms")
        else:
            self.correDesde = 0
        return []

    # -- memoria de alerta --------------------------------------------------
    def _anomalia(self, tipo, agora, porque, espera=30000):
        """Um alerta por tipo por pessoa a cada 30s. Sem isto, uma pessoa caida
        vira um alerta por quadro e afoga o painel em trinta segundos."""
        if not self.firme or self.parado:
            return []
        ult = self.alertaDe.get(tipo)
        if ult is not None and agora - ult < espera:
            return []
        self.alertaDe[tipo] = agora
        return [dict(tipo=tipo, corpo=self.id, quando=agora, porque=porque)]


# ---- briga: a pergunta e sobre PARES, nunca sobre uma pessoa ---------------
def _centro_tronco(t):
    return ((t.qx + t.ox) / 2, (t.qy + t.oy) / 2)


def distancia_entre(a, b, asp):
    if a.qx is None or b.qx is None:
        return float("inf")
    escala = (a.altura + b.altura) / 2
    if not escala > 1e-6:
        return float("inf")
    return math.hypot((a.qx - b.qx) * asp, a.qy - b.qy) / escala


def tocando(t, alvo, asp):
    if t.qx is None or alvo.qx is None or alvo.ox is None or not t.hist:
        return False
    h = t.hist[-1]
    cx, cy = _centro_tronco(alvo)
    lim = BRIGA_TOQUE * (alvo.altura or 1)
    return any(math.hypot((p[0] - cx) * asp, p[1] - cy) < lim
               for p in (h["px"], h["pd"]))


def golpe_dirigido(t, alvo, agora, asp):
    """O PICO num trecho curto, nao a media da janela. Um soco dura uns 130ms;
    medido de ponta a ponta de uma janela longa ele aparece pela metade."""
    if alvo.qx is None or alvo.ox is None:
        return 0.0
    tx, ty = _centro_tronco(alvo)
    h = t._janela(agora, GOLPE_MEM)
    if len(h) < 2:
        return 0.0
    alt = t.altura or 1
    melhor = 0.0
    for lado in ("px", "pd"):
        for i in range(len(h)):
            p0 = h[i][lado]
            d0 = math.hypot((tx - p0[0]) * asp, ty - p0[1])
            for j in range(i + 1, len(h)):
                dt = (h[j]["t"] - h[i]["t"]) / 1000.0
                if dt < 0.09:
                    continue
                if dt > 0.20:
                    break
                p1 = h[j][lado]
                d1 = math.hypot((tx - p1[0]) * asp, ty - p1[1])
                melhor = max(melhor, (d0 - d1) / alt / dt)
    return melhor


def analisar_briga(trilhas, agora, asp, memoria):
    """As quatro condicoes existem para derrubar os quatro falsos positivos que
    qualquer regra ingenua produz numa escola:
        perto          -> duas pessoas conversando de longe nao brigam
        mao no outro   -> gesticular no proprio espaco nao e briga
        golpe dirigido -> abraco tambem aproxima, mas devagar e sem direcao
        repeticao      -> um empurrao e um empurrao; briga e vai-e-vem
    """
    gente = [t for t in trilhas
             if t.firme and t.analisavel and not t.parado
             and t.qx is not None and t.ox is not None]
    alertas = []
    for i in range(len(gente)):
        for j in range(i + 1, len(gente)):
            a, b = gente[i], gente[j]
            # A chave e ordenada pelo id: (3,7) e (7,3) sao o mesmo par, e sem
            # ordenar seriam duas memorias e dois alertas.
            ka, kb = min(a.id, b.id), max(a.id, b.id)
            est = memoria.setdefault(
                (ka, kb), dict(desde=0, toques=[], visto=agora,
                               armado=False, pico=0.0))
            est["visto"] = agora
            est["toques"] = [x for x in est["toques"] if agora - x < BRIGA_JANELA]

            dist = distancia_entre(a, b, asp)
            encosta = dist < BRIGA_PERTO and (tocando(a, b, asp) or tocando(b, a, asp))
            # Medido nos dois sentidos e vale o maior: numa briga de verdade
            # raramente os dois acertam ao mesmo tempo.
            golpe = max(golpe_dirigido(a, b, agora, asp),
                        golpe_dirigido(b, a, agora, asp))

            # BORDA DE SUBIDA, nao nivel. Enquanto o sinal continua alto e o
            # MESMO soco, e conta-lo a cada quadro faria a exigencia de
            # repeticao nao filtrar nada.
            if encosta and golpe >= BRIGA_GOLPE and not est["armado"]:
                ult = est["toques"][-1] if est["toques"] else None
                if ult is None or agora - ult > BRIGA_GAP:
                    est["toques"].append(agora)
                    # O pico fica congelado AQUI. Lido so na hora do alerta,
                    # 600ms depois, ele ja voltou a zero.
                    est["pico"] = max(est["pico"], golpe)
                est["armado"] = True
            if golpe < BRIGA_GOLPE * BRIGA_SOLTA:
                est["armado"] = False

            if encosta and len(est["toques"]) >= BRIGA_TOQUES:
                if not est["desde"]:
                    est["desde"] = agora
                elif agora - est["desde"] > BRIGA_SEG:
                    dono = a if a.id <= b.id else b
                    alertas += dono._anomalia(
                        "briga", agora,
                        f"regra (não modelo treinado): {len(est['toques'])} "
                        f"impulsos em {BRIGA_JANELA / 1000}s, avanço de punho "
                        f"de {est['pico']:.2f} alturas/s (limiar {BRIGA_GOLPE}), "
                        f"distância {dist:.2f} alturas")
            else:
                est["desde"] = 0
            if not est["toques"]:
                est["pico"] = 0.0

    for k in [k for k, v in memoria.items() if agora - v["visto"] > BRIGA_JANELA * 2]:
        del memoria[k]
    return alertas
