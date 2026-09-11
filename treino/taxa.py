"""Quanto a taxa de quadros da camera custa em deteccao de queda.

A rede foi treinada a 30 quadros por segundo. Camera domestica (Tapo C200,
C210) entrega 15. Uma queda dura meio segundo: a 30fps a rede ve ~15 amostras
do tombo, a 15fps ve ~7. Este script mede o preco disso em vez de estimar.

Metodo: reextrai os MESMOS clipes de teste jogando fora quadros alternados, e
pontua com o modelo que JA ESTA NO AR (treino/modelo.json), sem retreinar.
E essa a pergunta real - o modelo embarcado hoje, numa camera mais lenta.

  DADOS=/caminho/dos/csv python3 treino/taxa.py
"""
import glob, json, os, sys
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import extrair as E

DADOS = os.environ.get("DADOS", "/tmp/ds")
# As mesmas pastas separadas no treino: cenarios que o modelo nunca viu.
TESTE = ("f_mask_s_3_keypoints_csv", "nf_mask_s_3_keypoints_csv")


def janelas(caminho, salto):
    """Janelas de ~1s de um clipe, ficando com 1 quadro a cada `salto`."""
    g = [E.geometria(q) for q in E.ler_clipe(caminho)][::salto]
    saida = []
    for i in range(0, max(1, len(g) - E.JANELA + 1), E.PASSO):
        c = E.caracteristicas(g, i, i + E.JANELA)
        if c is not None and np.isfinite(c).all():
            saida.append(c)
    return saida


def extrair_teste(fps):
    """(X, dono, rotulo) do conjunto de teste na taxa de quadros pedida."""
    salto = int(round(30.0 / fps))
    E.FPS = 30.0 / salto
    E.JANELA = max(4, int(round(30 / salto)))   # sempre ~1 segundo de tempo real
    E.PASSO = max(1, int(round(5 / salto)))
    X, dono, rot = [], [], []
    for pasta in TESTE:
        queda = 1 if pasta.startswith("f_") else 0
        for a in sorted(glob.glob(os.path.join(DADOS, pasta, "*.csv"))):
            try:
                w = janelas(a, salto)
            except Exception:
                continue
            if not w:
                continue
            X += w
            dono += [len(rot)] * len(w)
            rot.append(queda)
    return (np.array(X, dtype=np.float64), np.array(dono), np.array(rot, dtype=float))


def nota_clipe(m, X, dono, n):
    """Mesmo caminho do treino: tanh -> log-sum-exp por clipe -> sigmoide."""
    Z = (X - np.array(m["mu"])) / np.array(m["sd"])
    z = np.tanh(Z @ np.array(m["W1"]) + np.array(m["b1"])) @ np.array(m["W2"]) + m["b2"]
    TAU = 5.0
    mx = np.full(n, -1e30); np.maximum.at(mx, dono, z)
    s = np.zeros(n); np.add.at(s, dono, np.exp(TAU * (z - mx[dono])))
    return 1 / (1 + np.exp(-(mx + np.log(s) / TAU)))


def auc(y, p):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    return (r[y == 1].sum() - y.sum() * (y.sum() + 1) / 2) / (y.sum() * (1 - y).sum())


def medir(y, p, limiar):
    d = (p >= limiar).astype(int)
    vp = int(((d == 1) & (y == 1)).sum()); fp = int(((d == 1) & (y == 0)).sum())
    fn = int(((d == 0) & (y == 1)).sum()); vn = int(((d == 0) & (y == 0)).sum())
    prec = vp / max(vp + fp, 1); rec = vp / max(vp + fn, 1)
    return dict(vp=vp, fp=fp, fn=fn, vn=vn, prec=prec, rec=rec,
                f1=2 * prec * rec / max(prec + rec, 1e-9))


def main():
    m = json.load(open(os.path.join(AQUI, "modelo.json")))
    print(f"modelo em uso: limiar {m['limiar']:.2f}\n")
    print(f"{'fps':>5} {'clipes':>7} {'AUC':>6} {'precisao':>9} {'revocacao':>10} {'F1':>6}"
          f" {'perdidas':>9}   geometria(rev)")
    for fps in (30, 15, 10):
        X, dono, rot = extrair_teste(fps)
        p = nota_clipe(m, X, dono, len(rot))
        r = medir(rot, p, m["limiar"])
        gz = (X[:, 1] > 0.35) & (X[:, 3] > 55 / 90)
        gc = np.zeros(len(rot)); np.maximum.at(gc, dono, gz.astype(float))
        g = medir(rot, gc, 0.5)
        print(f"{fps:>5} {len(rot):>7} {auc(rot, p):>6.3f} {r['prec']:>8.0%}"
              f" {r['rec']:>9.0%} {r['f1']:>6.2f} {r['fn']:>9} {g['rec']:>13.0%}")


if __name__ == "__main__":
    main()
