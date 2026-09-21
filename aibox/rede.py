"""A rede de queda: 12 entradas, 8 neuronios, 113 pesos.

E a MESMA de treino/modelo.json, a mesma que o navegador roda e a mesma que
treino/provas.py usou para gerar as provas. Nao ha um segundo modelo, nao ha
conversao e nao ha reexportacao: os pesos sao lidos do arquivo que saiu do
treino. Essa e a razao de o porte para a AIBOX ser barato — o que muda e quem
enxerga o corpo, nao quem decide.
"""
import json
import os

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
MODELO = os.path.join(os.path.dirname(AQUI), "treino", "modelo.json")

_m = json.load(open(MODELO, encoding="utf-8"))
MU = np.array(_m["mu"], dtype=np.float64)
SD = np.array(_m["sd"], dtype=np.float64)
W1 = np.array(_m["W1"], dtype=np.float64)
B1 = np.array(_m["b1"], dtype=np.float64)
W2 = np.array(_m["W2"], dtype=np.float64)
B2 = float(_m["b2"])

LIMIAR = 0.50      # QUEDA_LIMIAR no auditix-sala.html
# Acima disto a janela esta fora do mundo em que o modelo foi medido, e a nota
# dele nao vale. A geometria, que nao aprendeu nada e so mede, continua valendo.
FORA = 6.0         # QUEDA_FORA


def nota(c):
    """0 a 1. Identica a `nota` de treino/provas.py, de proposito."""
    h = np.tanh((np.asarray(c, dtype=np.float64) - MU) / SD @ W1 + B1)
    return float(1.0 / (1.0 + np.exp(-(h @ W2 + B2))))


def distancia_do_treino(c):
    """O maior desvio-padrao entre as 12 entradas e o que o treino viu.

    Um modelo nao sabe que nao sabe: fora do que ele viu ele responde com a
    mesma confianca de sempre. Este numero e o que autoriza DESCARTAR a nota em
    vez de acreditar nela — e por isso ele entra no registro de calibracao."""
    return float(np.max(np.abs((np.asarray(c, dtype=np.float64) - MU) / SD)))
