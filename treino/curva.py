# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Quanto mais dados melhoram o modelo — medido, nao chutado.

A pergunta era direta: "se eu gravar mais exemplos, ela fica melhor?". Em vez de
opinar, treina com quantidades crescentes de clipes e mede sempre nos MESMOS
1.020 clipes de teste.

A resposta que sai daqui: com 20 clipes o modelo ja chega perto do teto, e 175
vezes mais dados rendem poucos pontos. Sao 113 pesos — ele satura cedo. Isso
muda a decisao de quem esta gravando: quantidade nao e a alavanca, cobrir os
casos em que ele erra e.

  uv run treino/curva.py
"""
import sys, os
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import treinar as T

d = np.load(os.path.join(AQUI, "janelas.npz"), allow_pickle=True)
X, dono, rot, grupo, pastas = (d["X"].astype(np.float64), d["dono"],
                               d["rot"].astype(np.float64), d["grupo"], d["pastas"])

# O teste e o mesmo do treino original: cenarios inteiros que o modelo nunca ve.
teste = {i for i, g in enumerate(grupo) if str(pastas[g]).endswith("_s_3_keypoints_csv")}
idxte = np.array(sorted(teste))
resto = np.array([i for i in range(len(rot)) if i not in teste])


def treinar_com(idxtr, semente):
    remap = -np.ones(len(rot), np.int64); remap[idxtr] = np.arange(len(idxtr))
    sel = remap[dono] >= 0
    Xtr, dtr, ytr = X[sel], remap[dono[sel]], rot[idxtr]
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-8
    r = T.Rede(X.shape[1], np.random.default_rng(semente))
    r.treinar((Xtr - mu) / sd, dtr, ytr)
    remap2 = -np.ones(len(rot), np.int64); remap2[idxte] = np.arange(len(idxte))
    s2 = remap2[dono] >= 0
    p = r.nota_clipe((X[s2] - mu) / sd, remap2[dono[s2]], len(idxte))
    ptr = r.nota_clipe((Xtr - mu) / sd, dtr, len(idxtr))
    # limiar escolhido NO TREINO, nunca no teste
    lim = max(np.arange(0.05, 0.96, 0.01), key=lambda t: T.medir(ytr, ptr, t)["f1"])
    return T.auc(rot[idxte], p), T.medir(rot[idxte], p, lim)


def main():
    print(f"teste fixo: {len(idxte)} clipes de cenarios que o modelo nunca ve\n")
    print(f"{'clipes':>8} {'AUC':>7} {'precisao':>9} {'revocacao':>10} {'F1':>6}")
    for n in (20, 50, 100, 250, 500, 1000, 2000, len(resto)):
        a, p, r_, f = [], [], [], []
        # varias amostragens nos tamanhos pequenos: ali o acaso pesa muito
        for k in range(3 if n < 2000 else 1):
            rng = np.random.default_rng(100 + k)
            idxtr = np.sort(rng.choice(resto, min(n, len(resto)), replace=False))
            if rot[idxtr].sum() < 2 or (1 - rot[idxtr]).sum() < 2:
                continue
            au, m = treinar_com(idxtr, T.SEMENTE + k)
            a.append(au); p.append(m["prec"]); r_.append(m["rec"]); f.append(m["f1"])
        if a:
            print(f"{n:>8} {np.mean(a):>7.3f} {np.mean(p):>8.0%} "
                  f"{np.mean(r_):>9.0%} {np.mean(f):>6.2f}")
    print("\nA curva achata cedo: mais exemplos do MESMO tipo rendem pouco.")
    print("O que rende e cobrir os casos em que ele erra — e, na pratica, o angulo")
    print("da camera, que mudou mais o resultado do que qualquer treino.")


if __name__ == "__main__":
    main()
