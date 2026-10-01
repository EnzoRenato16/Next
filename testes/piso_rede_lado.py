"""O piso de amostras da rede de queda. Roda pelo testes/piso-rede.mjs.

Uso: python3 testes/piso_rede_lado.py

Monta o MESMO cenario de queda em duas taxas de quadros — a da AIBOX de verdade
(6,7 analises por segundo, medida na caixa) e a do navegador (30) — e cobra que
a rede FALE nas duas. O porque esta no cabecalho do testes/piso-rede.mjs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aibox import regras, trilhas  # noqa: E402

ASP = 16 / 9
falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print("  ok   " + nome + ("   " + det if det else ""))
    else:
        falhas += 1
        print("  FALHA " + nome + "   " + det)


# Os 17 pontos COCO de um corpo, nos mesmos indices do MediaPipe que o
# testes/aibox.mjs usa — a mesma pessoa sintetica dos dois lados.
def corpo(ombro, quadril, joelho, torn, cx=0.5, punho=0.20, v=0.9):
    return [
        (cx, ombro - 0.12, v),                                   # nariz
        (cx - 0.02, ombro - 0.14, v), (cx + 0.02, ombro - 0.14, v),   # olhos
        (cx - 0.05, ombro - 0.13, v), (cx + 0.05, ombro - 0.13, v),   # orelhas
        (cx - 0.06, ombro, v), (cx + 0.06, ombro, v),                 # ombros
        (cx - 0.08, ombro + 0.10, v), (cx + 0.08, ombro + 0.10, v),   # cotovelos
        (cx - 0.08, ombro + punho, v), (cx + 0.08, ombro + punho, v),  # punhos
        (cx - 0.05, quadril, v), (cx + 0.05, quadril, v),             # quadris
        (cx - 0.05, joelho, v), (cx + 0.05, joelho, v),               # joelhos
        (cx - 0.05, torn, v), (cx + 0.05, torn, v),                   # tornozelos
    ]


def cenario_queda():
    """Em pe por 1,4 s e entao o tombo: o tronco deita e o quadril desce."""
    passos = [dict(ombro=0.30, quadril=0.55, joelho=0.75, torn=0.95)] * 42
    for i in range(18):
        passos.append(dict(ombro=0.30 + i * 0.048, quadril=0.55 + i * 0.030,
                           joelho=0.75 + i * 0.012, torn=0.95,
                           cx=0.5 + i * 0.012))
    passos += [passos[-1]] * 60
    return passos


def rodar(fps):
    """Roda o cenario reamostrado para `fps` e devolve (maior nota, pisos vistos).

    Os passos sao de 1/30 s, entao reamostrar e ficar com 1 a cada `salto` —
    e o mesmo que o treino/taxa.py faz para medir a rede em taxas baixas.
    """
    passos = cenario_queda()
    salto = 30.0 / fps
    reb = trilhas.Rebanho()
    maior, piso, amostras = 0.0, regras.QUEDA_AMOSTRAS, 0
    i = 0.0
    while int(i) < len(passos):
        t = int(i * (1000.0 / 30.0))
        reb.quadro([(1, corpo(**passos[int(i)]))], ASP, t)
        tr = reb.trilhas.get(1)
        if tr is not None:
            maior = max(maior, tr.notaQueda)
            # O piso e as amostras do REGIME, nao do nascimento da trilha: nos
            # primeiros 0,3 s ainda nao ha vao para medir a taxa, e ai vale o
            # piso do navegador de proposito (a trilha nem tem idade para
            # alertar). Olhar esse comeco seria medir o instrumento.
            piso, amostras = tr.pisoRede, max(amostras, tr.fps)
        i += salto
    return maior, piso, amostras


print("== o piso acompanha a maquina ==")

# 1. A caixa de verdade. 6,7 analises por segundo, lido na tela ao vivo da
#    AIBOX no laboratorio, com a camera da sala.
nota_caixa, piso_caixa, amostras_caixa = rodar(6.7)
ok("a 6,7/s (a AIBOX de verdade) a rede FALA numa queda",
   nota_caixa > 0.0, "maior nota %.3f" % nota_caixa)
ok("e a nota passa do limiar, entao a rede acusa a queda sozinha",
   nota_caixa >= 0.50, "maior nota %.3f, limiar 0.50" % nota_caixa)
ok("o piso a 6,7/s cabe na janela de 1 s",
   piso_caixa <= amostras_caixa,
   "piso %d, e no maximo %d amostras cabem em 1 s" % (piso_caixa, amostras_caixa))

# A REGRESSAO, dita em numero: com o piso antigo de 8 isto aqui era impossivel.
ok("e o piso antigo de 8 NAO cabia: era esse o silencio da rede na caixa",
   amostras_caixa < regras.QUEDA_AMOSTRAS,
   "%d amostras em 1 s, piso antigo %d" % (amostras_caixa, regras.QUEDA_AMOSTRAS))

# 2. O navegador. Aqui NADA pode mudar, senao o testes/aibox.mjs quebra.
nota_nav, piso_nav, amostras_nav = rodar(30.0)
ok("a 30/s o piso continua 8, igual ao navegador",
   piso_nav == regras.QUEDA_AMOSTRAS, "piso %d" % piso_nav)
ok("e a 30/s a rede continua acusando a mesma queda",
   nota_nav >= 0.50, "maior nota %.3f" % nota_nav)

# 3. O fundo do poco. Numa maquina muito lenta o piso para de cair: abaixo de
#    QUEDA_PISO as duas entradas que dividem por tempo viram ruido, e uma nota
#    tirada de tres pontos nao e medida, e chute.
_, piso_lento, _ = rodar(3.0)
ok("por mais lenta que a maquina esteja, o piso nao desce de %d"
   % regras.QUEDA_PISO,
   piso_lento == regras.QUEDA_PISO, "piso %d a 3/s" % piso_lento)

print("\nRESULTADO: " + ("FALHOU" if falhas else "passou"))
sys.exit(1 if falhas else 0)
