"""Seguir primeiro, reconhecer depois: vale a pena?   python3 testes/arena_reconferir.py

ARENA_RECONFERIR_S faz o juiz medir de novo quem ja foi decidido so a cada N
segundos. Este arquivo simula a arena quadro a quadro (6 por segundo, o
ARENA_FPS da caixa), com o Rastreador e o Juiz DE VERDADE e vetores sinteticos
no lugar dos rostos (como testes/arena_juiz.py), e mede, para cada N:

- quantos rostos o modelo de rosto mediu (o que se economiza);
- o placar no fim (autorizados e alertas);
- os segundos em que um ESTRANHO ficou com o nome de um autorizado na tela,
  nos dois jeitos de a trilha trocar de dono: duas pessoas que se cruzam, e
  uma que sai e outra que entra no mesmo lugar (o defeito de 20/10).

Cobra que N=0 e o de sempre e que as travas seguram o nome errado.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aibox import arena  # noqa: E402

FPS = 6.0
BOA = 0.7          # chance de o rosto de um quadro passar no portao de qualidade
falhas = 0


def ok(nome, cond, det=""):
    global falhas
    print(("  ok   " if cond else "  FALHA ") + nome + (f"   {det}" if det else ""))
    if not cond:
        falhas += 1


def unit(v):
    return v / np.linalg.norm(v)


class Mundo:
    def __init__(self, semente):
        self.rng = np.random.default_rng(semente)
        self.base = {n: unit(self.rng.normal(size=128))
                     for n in ("Lucas", "Daniel", "Samuel", "Matheus", "X1", "X2", "X3")}
        self.nomes = ["Daniel", "Lucas", "Matheus", "Samuel"]
        linhas, dono = [], []
        for i, n in enumerate(self.nomes):
            for _ in range(12):
                linhas.append(self.parecido(self.base[n], 0.75))
                dono.append(i)
        self.M = np.array([unit(v) for v in linhas], np.float32)
        self.dono = dono

    def parecido(self, b, cos):
        r = unit(self.rng.normal(size=128))
        r = unit(r - (r @ b) * b)
        return unit(cos * b + np.sqrt(1 - cos ** 2) * r)

    def leitura(self, quem):
        if quem.endswith("~"):
            # longe e mal iluminado: a leitura quase nao lembra a pessoa
            return self.parecido(self.base[quem[:-1]], float(self.rng.uniform(0.0, 0.2)))
        # cosseno entre a leitura e a pessoa: como o ArcFace de frente na HAIZ
        return self.parecido(self.base[quem], float(np.clip(self.rng.normal(0.62, 0.08), 0.3, 0.9)))


def rodar(reconf, roteiro, semente, segundos=40.0):
    """roteiro(t) -> lista de (quem, x, y, largura) na tela no instante t.
    Devolve medidas da rodada."""
    os.environ["ARENA_RECONFERIR_S"] = str(reconf)
    arena.configurar("arcface")
    w = Mundo(semente)
    juiz = arena.Juiz(w.nomes, w.M, w.dono)
    rast = arena.Rastreador("c1")
    errado = 0.0          # segundos com estranho exibido com nome de autorizado
    ate_nome = None       # quando o Samuel ganhou o nome dele (roteiro "chega")
    quadros = 0
    t = 0.0
    while t < segundos:
        gente = roteiro(t)
        caixas = [(x - lg / 2, y - lg / 2, lg, lg) for _, x, y, lg in gente]
        ids = rast.associar(caixas, t)
        for (quem, *_), ident in zip(gente, ids):
            precisa = juiz.precisa_medir(ident, t)
            tr = juiz.trilha(ident, 0)
            tr.visto = max(tr.visto, t)
            if tr.comeco is None:
                tr.comeco = t
            if w.rng.random() < BOA:
                if precisa:
                    juiz.ler(ident, w.leitura(quem), t, 0)
                else:
                    juiz.poupados += 1
            tr = juiz.trilhas[ident]
            if quem.startswith("X") and tr.estado == "autorizado":
                errado += 1 / FPS
            if quem == "Samuel" and tr.nome == "Samuel" and ate_nome is None:
                ate_nome = t
        quadros += 1
        t = round(t + 1 / FPS, 6)
    r = juiz.resumo()
    tot = juiz.medidos + juiz.poupados
    return dict(medidos=juiz.medidos, total=tot, aut=len(r["autorizados"]),
                alertas=len(r["desconhecidos"]), errado=errado, ate_nome=ate_nome)


def parados(t):
    """4 da galeria e 2 estranhos, cada um no seu lugar, mexendo um pouco."""
    lugares = [("Lucas", 300), ("Daniel", 600), ("Samuel", 900), ("Matheus", 1200),
               ("X1", 1500), ("X2", 1800)]
    return [(q, x + 5 * np.sin(t + i), 500, 120) for i, (q, x) in enumerate(lugares)]


def cruzam(t):
    """Samuel e um estranho andam um na direcao do outro e se cruzam aos 15 s.
    No cruzamento as trilhas trocam (o rastreador cola no mais proximo): a
    partir dai a trilha do Samuel e do estranho. Forcado aqui para ser o pior
    caso todas as vezes."""
    base = parados(t)[:4] + [("X2", 1800, 500, 120)]
    base = [b for b in base if b[0] != "Samuel"]
    if t < 15:
        return base + [("Samuel", 900, 500, 120), ("X1", 1100, 500, 120)]
    return base + [("X1", 900, 500, 120), ("Samuel", 1100, 500, 120)]


def sai_entra(lacuna):
    """O Samuel sai aos 15 s e, `lacuna` segundos depois, um estranho entra no
    MESMO lugar, do mesmo tamanho: o rastreador da a trilha do Samuel a ele."""
    def roteiro(t):
        g = [b for b in parados(t) if b[0] != "Samuel"]
        if t < 15:
            g.append(("Samuel", 900, 500, 120))
        elif t >= 15 + lacuna:
            g.append(("X3", 900, 500, 120))
        return g
    return roteiro


def chega(t):
    """O Samuel aparece longe (leitura ruim que ainda passa no portao) e vira
    desconhecido; aos 10 s chega perto e o rosto fica bom. Quanto demora para
    o nome dele aparecer? Quem ja e desconhecido tambem e medido menos."""
    g = [b for b in parados(t) if b[0] != "Samuel"]
    return g + [("Samuel~" if t < 10 else "Samuel", 900, 500, 120)]


VALORES = [0, 0.5, 1, 2, 3]
SEMENTES = range(int(os.environ.get("SEMENTES", "100")))


def tabela(titulo, roteiro, segundos=40.0):
    print(f"\n== {titulo} ==")
    print("   RECONFERIR_S | rostos medidos | economia | autorizados | alertas | estranho com nome (s): media / pior")
    res = {}
    for n in VALORES:
        rs = [rodar(n, roteiro, s, segundos) for s in SEMENTES]
        med = sum(r["medidos"] for r in rs) / len(rs)
        tot = sum(r["total"] for r in rs) / len(rs)
        aut = np.mean([r["aut"] for r in rs])
        al = np.mean([r["alertas"] for r in rs])
        err = [r["errado"] for r in rs]
        res[n] = dict(economia=1 - med / tot, aut=aut, alertas=al,
                      err_med=float(np.mean(err)), err_pior=float(np.max(err)), rs=rs)
        print(f"   {n:>12g} | {med:8.0f} de {tot:4.0f} | {100 * (1 - med / tot):6.0f}% |"
              f" {aut:11.2f} | {al:7.2f} | {np.mean(err):6.1f} / {np.max(err):.1f}")
    return res


a = tabela("sala parada: 4 da galeria + 2 estranhos, 40 s", parados)
b = tabela("duas pessoas se cruzam e trocam de trilha (Samuel x estranho)", cruzam)
c = tabela("Samuel sai e um estranho entra no lugar 1 s depois", sai_entra(1.0))
d = tabela("Samuel sai e um estranho entra no lugar 0,3 s depois (pior caso)", sai_entra(0.3))
e = tabela("Samuel chega longe (vira desconhecido) e aos 10 s fica com o rosto bom", chega)
print("   segundos ate o Samuel ganhar o nome, depois de o rosto ficar bom: media / pior")
for n in VALORES:
    ts = [x["ate_nome"] - 10 if x["ate_nome"] is not None else 99 for x in e[n]["rs"]]
    e[n]["ate"] = (float(np.mean(ts)), float(np.max(ts)))
    print(f"   {n:>12g} | {np.mean(ts):.1f} / {np.max(ts):.1f}")

print("\n== o que se cobra ==")
ok("N=0 mede todo rosto bom (o de sempre)", a[0]["economia"] == 0)
for n in VALORES[1:]:
    ok(f"N={n:g}: sala parada continua 4 de 4 e 2 alertas",
       a[n]["aut"] == 4 and a[n]["alertas"] == 2, f"{a[n]['aut']:.2f} / {a[n]['alertas']:.2f}")
ok("N=1 economiza mais da metade dos rostos na sala parada", a[1]["economia"] > 0.5,
   f"{100 * a[1]['economia']:.0f}%")
for nome, r in (("cruzam", b), ("sai e entra 1 s", c), ("sai e entra 0,3 s", d)):
    for n in VALORES[1:]:
        ok(f"{nome}, N={n:g}: o estranho levou o alerta em todas as rodadas",
           all(x["alertas"] >= 2 for x in r[n]["rs"]))
    ok(f"{nome}, N=1: nome errado em media no maximo 1 s a mais que N=0",
       r[1]["err_med"] <= r[0]["err_med"] + 1.0,
       f"{r[0]['err_med']:.1f} s -> {r[1]['err_med']:.1f} s (pior rodada {r[0]['err_pior']:.1f} -> {r[1]['err_pior']:.1f})")
ok("chega, N=1: o Samuel ganha o nome em todas as rodadas", e[1]["ate"][1] < 99)
ok("chega, N=1: em media no maximo 1 s depois de N=0",
   e[1]["ate"][0] <= e[0]["ate"][0] + 1.0, f"{e[0]['ate'][0]:.1f} s -> {e[1]['ate'][0]:.1f} s")

print("\nRESULTADO", "ok" if not falhas else f"{falhas} FALHA(S)")
sys.exit(1 if falhas else 0)
