"""COCO-17 -> os mesmos numeros que a Sala mede no navegador.

POR QUE ISTO CABE, e nao e coincidencia feliz.

A rede de queda foi treinada no Fall Vision (Harvard Dataverse, CC0), que traz
17 pontos por quadro no formato COCO. O YOLO11-pose, que e o que roda na AIBOX,
devolve exatamente esses 17 pontos, na mesma ordem. Ou seja: o modelo nao esta
sendo adaptado para um detector diferente — ele esta voltando para o formato em
que nasceu. Quem foi adaptado, no navegador, foi o MediaPipe, que tem 33 pontos
e dos quais a Sala usa justamente os 17 do COCO.

O QUE ESTE ARQUIVO NAO FAZ: reimplementar as 12 caracteristicas. Elas moram em
treino/extrair.py desde o treino, ja foram medidas em 4.509 clipes e ja tem uma
prova travada contra o JavaScript. Copiar seria criar uma segunda versao para
divergir da primeira em silencio. Aqui elas sao IMPORTADAS.
"""
import os
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
TREINO = os.path.join(os.path.dirname(AQUI), "treino")
if TREINO not in sys.path:
    sys.path.insert(0, TREINO)

import extrair as _E                                     # noqa: E402

# As 12 caracteristicas e a janela vem do treino, sem copia.
caracteristicas = _E.caracteristicas
JANELA = _E.JANELA
FPS_TREINO = _E.FPS

# Ordem COCO-17, que e a que o YOLO-pose devolve.
NARIZ = 0
OLHO_E, OLHO_D = 1, 2
ORELHA_E, ORELHA_D = 3, 4
OMBRO_E, OMBRO_D = 5, 6
COTOV_E, COTOV_D = 7, 8
PULSO_E, PULSO_D = 9, 10
QUADRIL_E, QUADRIL_D = 11, 12
JOELHO_E, JOELHO_D = 13, 14
TORN_E, TORN_D = 15, 16

# 0,30 e o corte do TREINO (CONF_MIN em extrair.py), nao o 0,40 do navegador.
# A diferenca e deliberada: o que a rede aprendeu a ver foi filtrado a 0,30, e
# e com ela que estes numeros vao conversar.
CONF_MIN = 0.30

# De onde sai cada ponto do COCO dentro dos 33 do MediaPipe. Existe para poder
# comparar os dois caminhos com a MESMA entrada — sem isto, "a caixinha calcula
# igual ao navegador?" so teria resposta com a caixinha na mao.
DO_MEDIAPIPE = (0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28)


def de_mediapipe(lm):
    """Os 33 pontos do MediaPipe -> os 17 do COCO, na ordem do YOLO."""
    return [(lm[i].x, lm[i].y, getattr(lm[i], "visibility", 1.0))
            for i in DO_MEDIAPIPE]


def geometria(kp, asp=1.0):
    """Um quadro de 17 pontos -> o dicionario que `caracteristicas` consome.

    `kp` sao 17 triplas (x, y, confianca) em coordenadas de 0 a 1. `asp` e a
    proporcao do quadro (largura/altura).

    O ASPECTO NAO E DETALHE. Em coordenadas normalizadas, um metro na horizontal
    e um metro na vertical nao valem o mesmo numero: num quadro 16:9 o
    horizontal sai encolhido em 44%. Sem corrigir, toda distancia e velocidade
    lateral entra errada na rede. E o mesmo fator que o navegador aplica.

    Devolve None quando nao da para medir — e isso e resposta, nao falha. Sem
    ombro ou sem quadril nao existe tronco, e um tronco chutado vira alerta
    falso, que e o defeito que faz uma escola parar de olhar para o alerta.
    """
    def pt(a, b):
        pa, pb = kp[a], kp[b]
        if pa[2] < CONF_MIN and pb[2] < CONF_MIN:
            return None
        return ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)

    o, h = pt(OMBRO_E, OMBRO_D), pt(QUADRIL_E, QUADRIL_D)
    if not o or not h:
        return None
    jo, to = pt(JOELHO_E, JOELHO_D), pt(TORN_E, TORN_D)

    # A regua do corpo, na MESMA escada do treino e do navegador: tornozelo se
    # aparece, senao joelho, senao a proporcao do tronco. Medir com o que da
    # para ver, e nunca chutar o que nao da.
    if to:
        altura, regua = abs(to[1] - o[1]) * 1.25, "tornozelo"
    elif jo:
        altura, regua = abs(jo[1] - o[1]) * 1.9, "joelho"
    else:
        altura, regua = abs(o[1] - h[1]) * 3.2, "tronco"
    if altura < 1e-6:
        return None

    eixo = float(np.hypot((o[0] - h[0]) * asp, o[1] - h[1]))
    ang = float(abs(np.degrees(np.arctan2((o[0] - h[0]) * asp, h[1] - o[1]))))
    ombro = float(np.hypot((kp[OMBRO_E][0] - kp[OMBRO_D][0]) * asp,
                           kp[OMBRO_E][1] - kp[OMBRO_D][1]))

    # A caixa sai dos 17 pontos confiaveis, que e exatamente como o treino a
    # mediu. O navegador usa os 33 do MediaPipe e por isso da um numero um
    # pouco diferente — aqui a conta fica MAIS perto do treino, nao menos.
    vis = [p for p in kp if p[2] >= CONF_MIN]
    if len(vis) > 2:
        xs = [p[0] for p in vis]
        ys = [p[1] for p in vis]
        prop = (max(xs) - min(xs)) * asp / max(max(ys) - min(ys), 1e-6)
    else:
        prop = 0.0

    # `regua` vai junto porque QUAL das tres foi usada importa tanto quanto o
    # numero: as tres sao aproximacoes diferentes da mesma pessoa, e comparar
    # uma com a outra e comparar centimetro com polegada. Foi assim que o
    # navegador acusou dezesseis quedas numa pessoa parada.
    return dict(hx=h[0], hy=h[1], altura=altura, eixo=eixo, ang=ang,
                ombro=ombro, prop=prop, regua=regua,
                pxx=kp[PULSO_E][0], pxy=kp[PULSO_E][1],
                pdx=kp[PULSO_D][0], pdy=kp[PULSO_D][1])


def caixa(kp):
    """(x0, y0, x1, y1) dos pontos confiaveis. Serve ao rastreio."""
    vis = [p for p in kp if p[2] >= CONF_MIN]
    if len(vis) < 3:
        return None
    xs = [p[0] for p in vis]
    ys = [p[1] for p in vis]
    return (min(xs), min(ys), max(xs), max(ys))
