"""Gera o arquivo de provas que trava o porte para JavaScript.

Sem isto, a unica forma de saber se a Sala calcula o mesmo que o treino seria
olhar a tela e torcer. Ja aconteceu nesta base de codigo: um tensor lido no
formato errado nao da erro, da numero plausivel e errado.

Grava sequencias de geometria por quadro, as 12 caracteristicas que o Python
extraiu delas e a nota final do modelo. O teste em JS refaz o caminho inteiro e
compara.
"""
import glob, json, os, numpy as np
import extrair

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.environ.get("DADOS", "/tmp/ds")

m = json.load(open(os.path.join(AQUI, "modelo.json")))
mu, sd = np.array(m["mu"]), np.array(m["sd"])
W1, b1 = np.array(m["W1"]), np.array(m["b1"])
W2, b2 = np.array(m["W2"]), float(m["b2"])

def nota(c):
    h = np.tanh((np.array(c) - mu)/sd @ W1 + b1)
    return float(1/(1+np.exp(-(h @ W2 + b2))))

casos = []
for pasta, queda in (("f_mask_b_1_keypoints_csv", 1), ("nf_mask_c_1_keypoints_csv", 0)):
    for a in sorted(glob.glob(os.path.join(DADOS, pasta, "*.csv")))[:4]:
        g = [extrair.geometria(q) for q in extrair.ler_clipe(a)]
        for i in range(0, max(1, len(g) - extrair.JANELA + 1), 25):
            c = extrair.caracteristicas(g, i, i + extrair.JANELA)
            if c is None or not np.isfinite(c).all():
                continue
            jan = [x for x in g[i:i+extrair.JANELA] if x]
            casos.append(dict(
                clipe=os.path.basename(a), queda=queda, i=i,
                quadros=[[round(x["hx"],3), round(x["hy"],3), round(x["altura"],4),
                          round(x["eixo"],4), round(x["ang"],4), round(x["ombro"],4),
                          round(x["prop"],5)] for x in jan],
                car=[round(float(v),6) for v in c],
                nota=round(nota(c), 6)))
            if len(casos) >= 40:
                break
        if len(casos) >= 40:
            break
    if len(casos) >= 40:
        break

json.dump(dict(fps=extrair.FPS, janela=extrair.JANELA, casos=casos),
          open(os.path.join(AQUI, "provas.json"), "w"))
print(f"{len(casos)} provas, {len(casos[0]['quadros'])} quadros cada")
