"""A cola entre o motor de rosto e as trilhas — roda pelo testes/rosto.mjs.

O motor de verdade (YuNet + SFace) precisa de um rosto de verdade na frente da
camera, e isso nao se testa com codigo. O que SE testa, e onde os defeitos
moram, e a cola: em qual corpo o rosto entra, quando perguntar de novo, e o que
acontece quando o servidor nao responde. E o que este arquivo cobra.
"""
import os
import sys
import threading

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


class Trilha:
    def __init__(self, ident, caixa):
        self.id, self.caixa, self.nome = ident, caixa, None


class MotorFalso:
    """Devolve rostos onde mandarem, e um vetor por rosto."""

    backend = "falso"

    def __init__(self, rostos):
        self.rostos = rostos
        self.embeddings = 0

    def detect(self, img, full_res=False):
        return self.rostos

    def embedding(self, img, linha):
        self.embeddings += 1
        return [0.1] * 128


import numpy as np  # noqa: E402

from aibox import rosto as rosto_mod  # noqa: E402


def montar(rostos, resposta="Enzo"):
    r = rosto_mod.Rosto.__new__(rosto_mod.Rosto)
    r.base, r.espera = "http://x", 0.0
    r.nomes, r.vistos, r.reconhecidos, r.erro = {}, 0, 0, None
    r._trava, r._pendente, r.vivo = threading.Lock(), None, True
    r.motor = MotorFalso(rostos)
    r._perguntar = lambda vetor: resposta
    return r


img = np.zeros((100, 200, 3), dtype=np.uint8)   # 200 x 100 pixels

# ---- 1. o rosto entra no corpo que o contem ------------------------------
# Corpo A ocupa a metade esquerda; o rosto esta em cima dele.
r = montar([[20.0, 10.0, 20.0, 20.0, 0.9]])
r.ver(img, [Trilha(7, (0.0, 0.0, 0.5, 1.0)), Trilha(9, (0.6, 0.0, 1.0, 1.0))])
r._trabalhar(*r._pendente)
ok("o rosto nomeia o corpo que o contem, nao o outro",
   r.nomes.get(7) is not None and 9 not in r.nomes, str(r.nomes))

# ---- 2. entre dois corpos que contem o rosto, vale o MENOR ---------------
# Alguem na frente e alguem atras: o nome tem que ir para quem esta na frente,
# senao o rosto de quem passa perto gruda em quem esta la atras.
r = montar([[100.0, 40.0, 20.0, 20.0, 0.9]])
grande, pequeno = Trilha(1, (0.0, 0.0, 1.0, 1.0)), Trilha(2, (0.45, 0.3, 0.7, 0.8))
r.ver(img, [grande, pequeno])
r._trabalhar(*r._pendente)
ok("entre dois corpos, o nome vai para o MENOR que contem o rosto",
   2 in r.nomes and 1 not in r.nomes, str(r.nomes))

# ---- 3. rosto sem corpo nenhum nao inventa trilha ------------------------
r = montar([[10.0, 10.0, 8.0, 8.0, 0.9]])
r.ver(img, [Trilha(3, (0.8, 0.8, 1.0, 1.0))])
r._trabalhar(*r._pendente)
ok("rosto fora de qualquer corpo nao vira nome nenhum", not r.nomes, str(r.nomes))

# ---- 4. quem ja tem nome nao e reperguntado a cada quadro ----------------
# Sem isto seria uma ida ao servidor por rosto por quadro, e o custo de rede
# comeria os quadros por segundo que este modulo existe para preservar.
r = montar([[20.0, 10.0, 20.0, 20.0, 0.9]])
t = Trilha(5, (0.0, 0.0, 0.5, 1.0))
for _ in range(4):
    r.ver(img, [t])
    if r._pendente:
        r._trabalhar(*r._pendente)
ok("quem ja tem nome nao e reperguntado a cada quadro",
   r.motor.embeddings == 1, f"{r.motor.embeddings} leituras de rosto")

# ---- 5. servidor fora nao derruba nem inventa ---------------------------
r = montar([[20.0, 10.0, 20.0, 20.0, 0.9]], resposta=None)
r.ver(img, [Trilha(8, (0.0, 0.0, 0.5, 1.0))])
r._trabalhar(*r._pendente)
ok("servidor sem resposta nao vira nome inventado", not r.nomes, str(r.nomes))

# ---- 6. um quadro por vez: o de tras e descartado -----------------------
# Trabalhar no quadro de tres segundos atras nao ajuda ninguem.
r = montar([[20.0, 10.0, 20.0, 20.0, 0.9]])
r.ver(img, [Trilha(1, (0.0, 0.0, 1.0, 1.0))])
primeiro = r._pendente
r.ver(img, [Trilha(2, (0.0, 0.0, 1.0, 1.0))])
ok("com um quadro ja na fila, o proximo e descartado",
   r._pendente is primeiro)

# ---- 7. trilha sem caixa nao quebra -------------------------------------
r = montar([])
sem = Trilha(4, None)
r.ver(img, [sem])
ok("trilha ainda sem caixa nao derruba o modulo", r._pendente is not None)

print(f"\n{'FALHOU' if falhas else 'a cola do rosto passou'}")
sys.exit(1 if falhas else 0)
