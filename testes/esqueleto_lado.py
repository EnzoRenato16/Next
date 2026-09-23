"""A prova sem rosto, do lado da caixa — roda pelo testes/esqueleto.mjs."""
import math
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from aibox import trilhas  # noqa: E402

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


def corpo(y_quadril):
    """Um corpo de 17 pontos, em pe ou no chao conforme o quadril."""
    kp = [[0.5, y_quadril - 0.3, 0.9]] * 5          # cabeca
    kp += [[0.45, y_quadril - 0.2, 0.9], [0.55, y_quadril - 0.2, 0.9]] * 3   # bracos
    kp += [[0.47, y_quadril, 0.9], [0.53, y_quadril, 0.9]]                   # quadril
    kp += [[0.47, y_quadril + 0.15, 0.9], [0.53, y_quadril + 0.15, 0.9]] * 2  # pernas
    return kp[:17]


r = trilhas.Rebanho()
# 5 s de uma pessoa a 10 quadros por segundo, descendo no fim.
for i in range(50):
    agora = i * 100.0
    y = 0.5 if i < 40 else 0.5 + (i - 40) * 0.03
    r.quadro([(1, corpo(y))], 16 / 9, agora)
t = r.trilhas[1]

ok("a trilha guarda so os ultimos 3 s de pontos, e nao a aula inteira",
   len(t._poses) <= 31, f"{len(t._poses)} quadros guardados")

p = trilhas.poses_da_prova(t, 4900.0, 16 / 9)
ok("a prova pega a janela dos ultimos 2,5 s", p is not None and 20 <= len(p) <= 26,
   f"{len(p) if p else 0} quadros")
ok("cada quadro tem os 17 pontos com [x, y, confianca]",
   all(len(q) == 17 and all(len(pt) == 3 for pt in q) for q in p))
ok("o ULTIMO quadro e o corpo no chao (quadril mais baixo que o primeiro)",
   p[-1][11][1] > p[0][11][1], f"{p[0][11][1]} -> {p[-1][11][1]}")
# x multiplicado pela proporcao: 0.47 * 16/9 = 0.8356
ok("o x sai em alturas de quadro (multiplicado pela proporcao 16:9)",
   abs(p[-1][11][0] - round(0.47 * 16 / 9, 4)) < 1e-9, str(p[-1][11][0]))

p8 = trilhas.poses_da_prova(t, 4900.0, 16 / 9, maximo=8)
ok("com teto de 8 quadros, rarefaz por igual e MANTEM o ultimo",
   len(p8) == 8 and p8[-1] == p[-1], f"{len(p8)} quadros")

# Ponto que o detector nao viu nao pode virar NaN no JSON: o servidor recusaria
# o alerta inteiro por causa de um tornozelo.
r2 = trilhas.Rebanho()
ruim = corpo(0.5)
ruim[16] = [float("nan"), 0.9, 0.0]
r2.quadro([(2, ruim)], 1.0, 0.0)
pr = trilhas.poses_da_prova(r2.trilhas[2], 0.0, 1.0)
ok("ponto nao visto (NaN) vira zero, e nao derruba o alerta",
   all(math.isfinite(v) for v in pr[0][16]), str(pr[0][16]))

ok("sem pontos recentes, nao inventa prova",
   trilhas.poses_da_prova(t, 60000.0, 1.0) is None)

print(f"\n{'FALHOU' if falhas else 'a prova sem rosto passou na caixa'}")
sys.exit(1 if falhas else 0)
