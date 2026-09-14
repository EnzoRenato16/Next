# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""A caixa do corpo mais larga que alta, como sinal de queda.

Quem esta no chao ocupa um retangulo deitado, venha a camera de onde vier. E o
que faz esse sinal valer: ele nao depende do eixo do tronco, que a perspectiva
encurta, nem do angulo, que uma camera alta distorce — as duas coisas que
falharam na sala do Enzo.

Mede nos 4.509 clipes, por clipe, e mostra o custo de cada corte. O valor
escolhido esta em QUEDA_PROP, no auditix-sala.html.

  uv run treino/caixa.py
"""
import os, sys
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
CAIXA = 10   # indice do atributo "caixa mais larga que alta" em extrair.py


def main():
    d = np.load(os.path.join(AQUI, "janelas.npz"), allow_pickle=True)
    X, dono, rot = d["X"].astype(float), d["dono"], d["rot"].astype(float)
    prop = np.zeros(len(rot))
    np.maximum.at(prop, dono, X[:, CAIXA])
    q, n = prop[rot == 1], prop[rot == 0]
    print(f"largura/altura da caixa, por clipe "
          f"({len(q)} quedas, {len(n)} nao-quedas)\n")
    print(f"{'percentil':>10} {'queda':>8} {'nao-queda':>11}")
    for p in (50, 75, 90, 95, 99):
        print(f"{p:>10} {np.percentile(q, p):>8.2f} {np.percentile(n, p):>11.2f}")
    print(f"\n{'corte':>7} {'pega das quedas':>17} {'dispara em nao-quedas':>23}")
    for c in (0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6):
        print(f"{c:>7.1f} {(q > c).mean():>16.0%} {(n > c).mean():>22.0%}")
    print("\nQUEDA_PROP e DEMO_PROP, no auditix-sala.html, saem desta tabela.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
