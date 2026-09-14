# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Quanto uma pessoa REAL se mexe quando esta parada.

Existe porque um casaco na cadeira tem ombros, tronco e a silhueta certa: o
detector de pose aceita, e como ele nunca se move, nenhuma defesa de tempo
pega. Ele fica ali contando como gente e podendo virar alerta de queda.

O que separa os dois e que pessoa nenhuma fica imovel. Mas "imovel" precisa de
numero, senao a regra descarta gente sentada quieta. Este script mede a
amplitude do quadril em janelas de pessoas reais e mostra o custo de cada corte.

Resultado que justifica PARADO_MIN no auditix-sala.html: em 530 janelas de 5s,
a pessoa MAIS parada de todas deslocou 0,0082 alturas de corpo. O corte em
0,005 nao descartou uma unica pessoa real.

  DADOS=/caminho/dos/csv uv run treino/parado.py
"""
import glob, os, sys
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import extrair as E

DADOS = os.environ.get("DADOS", "/tmp/ds")
JANELAS = (("5s", 150), ("10s", 300))


def amplitudes(caminho, n):
    """Amplitude do quadril em janelas de n quadros, em alturas de corpo."""
    g = [E.geometria(q) for q in E.ler_clipe(caminho)]
    bons = [x for x in g if x]
    if len(bons) < n:
        return []
    fora = []
    for k in range(0, len(bons) - n + 1, 30):
        jan = bons[k:k + n]
        alt = float(np.median([x["altura"] for x in jan]))
        if alt < 1e-6:
            continue
        hx = np.array([x["hx"] for x in jan]); hy = np.array([x["hy"] for x in jan])
        fora.append(float(np.hypot(hx.max() - hx.min(), hy.max() - hy.min()) / alt))
    return fora


def main():
    arqs = [a for p in sorted(os.listdir(DADOS))
            if p.startswith("nf_") and p.endswith("_keypoints_csv")
            for a in sorted(glob.glob(os.path.join(DADOS, p, "*.csv")))]
    if not arqs:
        print(f"nenhum CSV em {DADOS} (veja o LEIA.md para baixar)")
        return 1
    for nome, n in JANELAS:
        v = []
        for a in arqs:
            try:
                v += amplitudes(a, n)
            except Exception:
                pass
        if not v:
            print(f"\njanela de {nome}: nenhum clipe tem {n} quadros seguidos")
            continue
        v = np.array(v)
        print(f"\njanela de {nome} — {len(v)} janelas de pessoas REAIS")
        print(f"  a pessoa MAIS parada de todas: {v.min():.4f} alturas de corpo")
        for corte in (0.005, 0.010, 0.020, 0.030, 0.050):
            print(f"  corte {corte:.3f}: descartaria {(v < corte).mean():6.2%} das pessoas")
    print("\nO corte escolhido esta em PARADO_MIN, no auditix-sala.html.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
