"""O batimento da AIBOX — roda pelo testes/batimento.mjs.

Uso: python3 testes/batimento_lado.py [base-do-servidor-de-teste]

Primeiro a conta da imagem, com relogio falso (sem esperar de verdade): sala
com detalhe = ok; lente tampada = tampada so depois de TAMPADA_S; camera muda
= sem_imagem. Depois, se veio um servidor, a caixa bate nele de verdade.
"""
import os
import sys
import time

os.environ["BATIDA_S"] = "1"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import numpy as np  # noqa: E402

from aibox import batimento  # noqa: E402

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


enviados = []
b = batimento.Batimento("http://x", "sala-teste", caixa="caixa-t",
                        post=lambda alvo, corpo, espera: enviados.append(corpo) or 200)
rng = np.random.default_rng(1)
sala = rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)       # cheia de coisa
mao = np.full((360, 640, 3), 22, np.uint8) + rng.integers(0, 3, (360, 640, 3),
                                                            dtype=np.uint8)

t = 1000.0
b.quadro(sala, t)
ok("sala com detalhe: imagem ok", b.estado(t) == "ok", f"detalhe {b.valor:.0f}")
ok("e o detalhe da sala fica bem acima do limiar",
   b.valor > 3 * batimento.TAMPADA_LIMIAR, f"{b.valor:.0f}")

for k in range(1, 6):
    b.quadro(mao, t + k)
ok("mao na lente por 5 s: AINDA nao e tampada (sombra passageira nao alarma)",
   b.estado(t + 5) == "ok", f"detalhe {b.valor:.1f}")
for k in range(6, 17):
    b.quadro(mao, t + k)
ok("mao na lente por mais de TAMPADA_S: tampada", b.estado(t + 16) == "tampada")
b.quadro(sala, t + 17)
ok("tirou a mao: volta a ok no mesmo segundo", b.estado(t + 17) == "ok")
ok("sem quadro por mais de SEM_IMAGEM_S: sem_imagem",
   b.estado(t + 17 + batimento.SEM_IMAGEM_S + 1) == "sem_imagem")

# A conta so roda uma vez por segundo: 100 quadros no mesmo segundo = 1 conta.
chamadas = []
original = batimento.detalhe
batimento.detalhe = lambda img: chamadas.append(1) or original(img)
for k in range(100):
    b.quadro(sala, t + 30 + k / 1000)
batimento.detalhe = original
ok("100 quadros no mesmo segundo custam UMA conta", len(chamadas) == 1, str(len(chamadas)))

t0 = time.perf_counter()
for _ in range(200):
    batimento.detalhe(sala)
ms = (time.perf_counter() - t0) / 200 * 1000
ok("e a conta cabe folgada no laco (< 2 ms)", ms < 2, f"{ms:.3f} ms")

b.fechar()
ok("ao fechar, avisa 'parada' (encerramento de proposito, sem sirene)",
   enviados and enviados[-1]["estado"] == "parada")
ok("a batida leva o numero do detalhe, para o limiar ser ajustado no local",
   "detalhe" in enviados[-1] and enviados[-1]["caixa"] == "caixa-t")

if len(sys.argv) > 1:
    # De verdade, contra o servidor de teste: 2 batidas ok e depois fecha.
    real = batimento.Batimento(sys.argv[1], "sala-real", caixa="caixa-real")
    real.quadro(sala)
    time.sleep(2.3)
    ok("contra o servidor de verdade, as batidas chegam", real.batidas >= 2,
       f"{real.batidas} batidas, {real.falhas} falhas ({real.ultimo_erro})")
    real.fechar()

print("RESULTADO", "ok" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
