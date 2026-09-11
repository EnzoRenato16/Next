"""Treina o classificador de queda a partir das janelas extraidas.

Rede minuscula de proposito: 12 entradas -> 8 -> 1. Sao 113 pesos, que cabem
num JSON dentro do proprio auditix-sala.html. Nada de baixar modelo, nada de
runtime novo, nada de CDN — a Sala continua abrindo sem internet.

Escrito em numpy puro, com a derivada na mao. Nao e teimosia: sem torch e sem
sklearn aqui, e um modelo desse tamanho nao precisa deles. O efeito colateral e
bom, porque da para ler cada passo.

ROTULO FRACO. O dataset diz "este clipe TEM uma queda", nao diz em que quadro.
Entao o treino usa agregacao por clipe: a nota do clipe e o maior valor entre
as janelas dele (suavizado por log-sum-exp, para a derivada existir em todo
lugar). Um clipe sem queda empurra TODAS as janelas para baixo; um clipe com
queda so exige que UMA passe. E exatamente como o sistema funciona ao vivo.
"""
import json, os, numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
OCULTO, TAU, EPOCAS, LOTE, PASSO = 8, 5.0, 260, 64, 0.02
SEMENTE = 7

NOMES = ["amplitude vertical", "descida em 0,5s", "pico lateral",
         "tronco mais deitado", "tronco medio", "tronco no fim",
         "altura minima", "altura no fim", "encurtamento do tronco",
         "variacao do ombro", "caixa mais larga", "proporcao no fim"]


def lse(z, dono, n):
    """Nota por clipe: log-sum-exp das janelas. Aproxima o maximo, com derivada."""
    m = np.full(n, -1e30)
    np.maximum.at(m, dono, z)
    e = np.exp(TAU * (z - m[dono]))
    s = np.zeros(n); np.add.at(s, dono, e)
    return m + np.log(s) / TAU, e, s


class Rede:
    def __init__(self, d, rng):
        self.W1 = rng.normal(0, 1/np.sqrt(d), (d, OCULTO)).astype(np.float64)
        self.b1 = np.zeros(OCULTO)
        self.W2 = rng.normal(0, 1/np.sqrt(OCULTO), OCULTO)
        self.b2 = 0.0
        self.m = {k: np.zeros_like(getattr(self, k)) for k in ("W1","b1","W2")}
        self.v = {k: np.zeros_like(getattr(self, k)) for k in ("W1","b1","W2")}
        self.mb2 = self.vb2 = 0.0; self.passo = 0

    def frente(self, X):
        h = np.tanh(X @ self.W1 + self.b1)
        return h, h @ self.W2 + self.b2

    def treinar(self, X, dono, y, epocas=EPOCAS):
        rng = np.random.default_rng(SEMENTE)
        n = len(y)
        for ep in range(epocas):
            ordem = rng.permutation(n)
            for k in range(0, n, LOTE):
                cl = ordem[k:k+LOTE]
                sel = np.isin(dono, cl)
                Xb = X[sel]
                # renumera os clipes do lote para 0..len(cl)-1
                mapa = -np.ones(n, dtype=np.int64); mapa[cl] = np.arange(len(cl))
                db = mapa[dono[sel]]
                h, z = self.frente(Xb)
                nota, e, s = lse(z, db, len(cl))
                p = 1/(1+np.exp(-nota))
                g = (p - y[cl]) / len(cl)            # dL/dnota
                gz = g[db] * e / s[db]               # espalha pelas janelas
                gW2 = h.T @ gz
                gb2 = gz.sum()
                gh = np.outer(gz, self.W2) * (1 - h*h)
                gW1 = Xb.T @ gh
                gb1 = gh.sum(0)
                self._passo(gW1, gb1, gW2, gb2)

    def _passo(self, gW1, gb1, gW2, gb2):
        self.passo += 1; t = self.passo
        for k, g in (("W1",gW1), ("b1",gb1), ("W2",gW2)):
            self.m[k] = 0.9*self.m[k] + 0.1*g
            self.v[k] = 0.999*self.v[k] + 0.001*g*g
            mh = self.m[k]/(1-0.9**t); vh = self.v[k]/(1-0.999**t)
            setattr(self, k, getattr(self, k) - PASSO*mh/(np.sqrt(vh)+1e-8))
        self.mb2 = 0.9*self.mb2 + 0.1*gb2
        self.vb2 = 0.999*self.vb2 + 0.001*gb2*gb2
        self.b2 -= PASSO*(self.mb2/(1-0.9**t))/(np.sqrt(self.vb2/(1-0.999**t))+1e-8)

    def nota_clipe(self, X, dono, n):
        _, z = self.frente(X)
        nota, _, _ = lse(z, dono, n)
        return 1/(1+np.exp(-nota))


def auc(y, p):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p)+1)
    pos, neg = y.sum(), (1-y).sum()
    return (r[y==1].sum() - pos*(pos+1)/2) / (pos*neg)


def medir(y, p, limiar):
    d = (p >= limiar).astype(int)
    vp = int(((d==1)&(y==1)).sum()); fp = int(((d==1)&(y==0)).sum())
    fn = int(((d==0)&(y==1)).sum()); vn = int(((d==0)&(y==0)).sum())
    prec = vp/max(vp+fp,1); rec = vp/max(vp+fn,1)
    return dict(vp=vp, fp=fp, fn=fn, vn=vn, prec=prec, rec=rec,
                f1=2*prec*rec/max(prec+rec,1e-9))


def main():
    d = np.load(os.path.join(AQUI, "janelas.npz"), allow_pickle=True)
    X, dono, rot, grupo = d["X"].astype(np.float64), d["dono"], d["rot"].astype(np.float64), d["grupo"]
    pastas = [str(p) for p in d["pastas"]]
    print(f"janelas {X.shape}  clipes {len(rot)}  quedas {int(rot.sum())}\n")

    # TESTE POR PASTA INTEIRA: cenarios que o modelo nunca viu. E o corte
    # honesto — separar por clipe deixaria quadros do mesmo cenario dos dois
    # lados e a nota sairia otimista.
    fora = [i for i,p in enumerate(pastas) if p in
            ("f_mask_s_3_keypoints_csv", "nf_mask_s_3_keypoints_csv")]
    te = np.isin(grupo, fora); tr = ~te
    print("teste = cenarios inteiros deixados de fora:",
          ", ".join(pastas[i] for i in fora))
    print(f"treino {tr.sum()} clipes | teste {te.sum()} clipes\n")

    idxtr = np.where(tr)[0]; idxte = np.where(te)[0]
    remap = -np.ones(len(rot), dtype=np.int64)
    remap[idxtr] = np.arange(len(idxtr))
    seltr = remap[dono] >= 0
    Xtr, dtr, ytr = X[seltr], remap[dono[seltr]], rot[idxtr]

    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-8
    Xtr = (Xtr - mu)/sd

    rede = Rede(X.shape[1], np.random.default_rng(SEMENTE))
    rede.treinar(Xtr, dtr, ytr)

    remap2 = -np.ones(len(rot), dtype=np.int64)
    remap2[idxte] = np.arange(len(idxte))
    selte = remap2[dono] >= 0
    Xte, dte, yte = (X[selte]-mu)/sd, remap2[dono[selte]], rot[idxte]

    ptr = rede.nota_clipe(Xtr, dtr, len(idxtr))
    pte = rede.nota_clipe(Xte, dte, len(idxte))
    print(f"AUC treino {auc(ytr, ptr):.3f}   AUC teste {auc(yte, pte):.3f}\n")

    # A GEOMETRIA que esta no ar hoje, medida nos MESMOS clipes.
    gz = (X[:,1] > 0.35) & (X[:,3] > 55/90)
    gclip = np.zeros(len(rot))
    np.maximum.at(gclip, dono, gz.astype(float))
    print("comparacao no conjunto de teste:")
    g = medir(yte, gclip[idxte], 0.5)
    print(f"  regra geometrica   precisao {g['prec']:.0%}  revocacao {g['rec']:.0%}  F1 {g['f1']:.2f}")
    melhor = max(np.arange(0.05, 0.96, 0.01),
                 key=lambda t: medir(ytr, ptr, t)["f1"])   # limiar escolhido NO TREINO
    m = medir(yte, pte, melhor)
    print(f"  rede (limiar {melhor:.2f}) precisao {m['prec']:.0%}  revocacao {m['rec']:.0%}  F1 {m['f1']:.2f}")
    print(f"     verdadeiros {m['vp']}  falsos alarmes {m['fp']}  perdidas {m['fn']}  corretos {m['vn']}")

    json.dump(dict(mu=mu.tolist(), sd=sd.tolist(),
                   W1=rede.W1.tolist(), b1=rede.b1.tolist(),
                   W2=rede.W2.tolist(), b2=float(rede.b2),
                   limiar=float(melhor), nomes=NOMES,
                   auc_teste=float(auc(yte, pte))),
              open(os.path.join(AQUI, "modelo.json"), "w"), indent=1)
    print(f"\npesos em treino/modelo.json  ({rede.W1.size+rede.b1.size+rede.W2.size+1} numeros)")


if __name__ == "__main__":
    main()
