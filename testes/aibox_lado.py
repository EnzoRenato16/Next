"""O lado Python da conferencia de porte. Chamado por testes/aibox.mjs.

Le um cenario de quadros em JSON na entrada padrao, roda o MESMO caminho que a
AIBOX vai rodar, e devolve os numeros em JSON na saida. Quem compara e o teste
em JS, que roda o navegador com o mesmo cenario.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aibox import medidas, rede, trilhas          # noqa: E402

ent = json.load(sys.stdin)

if ent.get("modo") == "provas":
    # As 40 provas geradas por treino/provas.py: geometria por quadro, as 12
    # caracteristicas e a nota. Se este caminho divergir, o porte esta errado
    # e nao ha o que discutir.
    p = json.load(open(os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), "treino", "provas.json")))
    piorC = piorN = 0.0
    for c in p["casos"]:
        g = [dict(hx=q[0], hy=q[1], altura=q[2], eixo=q[3], ang=q[4],
                  ombro=q[5], prop=q[6]) for q in c["quadros"]]
        car = medidas.caracteristicas(g, 0, len(g), fps=p["fps"])
        piorC = max(piorC, max(abs(float(a) - b) for a, b in zip(car, c["car"])))
        piorN = max(piorN, abs(rede.nota(car) - c["nota"]))
    print(json.dumps(dict(casos=len(p["casos"]), pior_caracteristica=piorC,
                          pior_nota=piorN)))
    sys.exit(0)

# Cenario ao vivo: cada quadro traz os 17 pontos COCO e o instante.
reb = trilhas.Rebanho()
asp = ent["aspecto"]
saida = []
for q in ent["quadros"]:
    kp = [tuple(p) for p in q["kp"]]
    al = reb.quadro([(1, kp)], asp, q["t"])
    t = reb.trilhas.get(1)
    # SEM arredondar. A primeira versao arredondava em 6 casas e o teste em JS
    # acusava diferenca de 5e-7 em tudo — que era exatamente o quantum deste
    # arredondamento, e nao divergencia nenhuma entre os dois lados. Ruido
    # introduzido pelo proprio instrumento de medida e o jeito mais facil de
    # esconder (ou inventar) um erro de porte.
    saida.append(dict(
        t=q["t"],
        baixo=t.baixo, ang=t.ang, altura=t.altura, prop=t.prop,
        nota=t.notaQueda, fora=t.foraDoTreino,
        vel=t.velocidade, fps=t.fps,
        regua=t.regua, armado=bool(t.quedaDesde),
        alertas=[a["tipo"] for a in al]))
print(json.dumps(saida))
