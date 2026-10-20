"""ArcFace pequeno (w600k_mbf, 512 numeros), a opcao ao SFace na arena.

POR QUE EXISTE. Medido em 20/10: contra a galeria do grupo, o Enzo (fora dela)
chegou a 0,40 no SFace e a 0,24 neste modelo; no LFW, com rosto de 38 px, ele
aceita 99,0% dos donos contra 97,8% do SFace, com 0,1% de estranhos aprovados
(ver aibox/comparar_modelos.py). Mais folga entre dono e estranho.

QUEM ESCOLHE O MOTOR E A GALERIA, nao uma variavel solta: cada galeria grava
com qual motor foi feita ("motor" no json), e a arena le com o mesmo. Numeros
de um motor comparados com os do outro sao ruido (ver "DOIS MOTORES QUE NAO SE
FALAM" no CLAUDE.md), e e assim que isso nao acontece por descuido.

Roda pelo cv2.dnn (o OpenCV 4.10 da caixa), sem instalar nada: o resultado e
identico ao do ONNX Runtime (cosseno 1,0 medido). O detector continua o YuNet,
e os 5 pontos dele alinham o rosto no molde do ArcFace.

O ARQUIVO fica fora do Git (licenca da InsightFace: pesquisa e uso nao
comercial). Como baixar: topo de aibox/comparar_modelos.py. Para a caixa,
`pc modelos` ja copia todo .onnx de daten\\models.
"""
import os

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO = os.environ.get("ARCFACE_MODELO") or os.path.join(
    RAIZ, "daten", "models", "w600k_mbf.onnx")
# Onde o ArcFace espera olhos, nariz e cantos da boca num rosto de 112x112.
# A ordem e a mesma do YuNet: olho da esquerda DA IMAGEM primeiro.
MOLDE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                  [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)


class ArcFace:
    def __init__(self, caminho=None):
        import cv2
        caminho = caminho or CAMINHO
        if not os.path.exists(caminho):
            raise FileNotFoundError(
                f"falta {caminho}. Baixe com as linhas do topo de "
                "aibox/comparar_modelos.py (no PC) e leve com `pc modelos`.")
        self.cv2 = cv2
        self.net = cv2.dnn.readNetFromONNX(caminho)

    def embedding(self, img, linha):
        cv2 = self.cv2
        pontos = np.asarray(linha[4:14], np.float32).reshape(5, 2)
        m, _ = cv2.estimateAffinePartial2D(pontos, MOLDE, method=cv2.LMEDS)
        rosto = cv2.warpAffine(img, m, (112, 112), borderValue=0)
        blob = cv2.dnn.blobFromImage(rosto, 1 / 127.5, (112, 112),
                                     (127.5, 127.5, 127.5), swapRB=True)
        self.net.setInput(blob)
        return self.net.forward().ravel().astype(np.float32)


def extrator(modelo, rosto):
    """A funcao (img, linha_do_yunet) -> vetor do motor pedido. `rosto` e o
    FaceEngine do daten, que ja tem o SFace carregado."""
    if modelo == "arcface":
        return ArcFace().embedding
    if modelo == "sface":
        return rosto.embedding
    raise ValueError(f"motor desconhecido: {modelo!r} (sface ou arcface)")
