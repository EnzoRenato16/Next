"""SFace (o de hoje) contra ArcFace pequeno: qual separa melhor dono de estranho?

  python aibox\\comparar_modelos.py --estranho ensaio.mp4 --autorizados ensaio4.mp4

So mede, nao muda nada: a galeria da arena e o arena.py continuam como estao.

POR QUE EXISTE. No laboratorio (20/10) o Enzo, fora da galeria, ficou em 0,30
contra o Lucas com o SFace, com picos de 0,40, e o dono precisa passar de um
limiar ACIMA disso. A folga entre "o estranho mais parecido" e "o dono no pior
momento" e o que decide a prova, e modelos da familia ArcFace costumam abrir
essa folga. Mas "costumam" nao e medida: este script mede, com as MESMAS fotos
e os MESMOS videos, nos dois modelos.

O QUE ELE FAZ. Monta duas galerias com as fotos de fotos-cadastro (so as
pastas de --nomes), le os videos com o mesmo detector (YuNet) e o mesmo portao
de qualidade da arena, e para cada rosto bom calcula a nota nos dois modelos.
No video --estranho toda nota e de estranho; no --autorizados, a nota do nome
que ganhou e a do dono (so os autorizados aparecem nele).

AS NOTAS NAO SE COMPARAM ENTRE MODELOS (cada um tem a sua escala). O que se
compara e a FOLGA: o dono no pior momento (5% mais baixos) menos o estranho no
melhor momento. Folga maior = limiar mais facil de acertar na camera da caixa.

O MODELO. w600k_mbf.onnx (13 MB), do pacote buffalo_s da InsightFace, roda
pelo OpenCV (o mesmo cv2.dnn da caixa, sem instalar nada). Licenca: pesquisa e
uso nao comercial; serve para a competicao, nao para vender o produto. Fica
FORA do Git. Baixar uma vez (PowerShell, na pasta do projeto):

  curl.exe -L -o buffalo_s.zip https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip
  tar -xf buffalo_s.zip w600k_mbf.onnx
  move w600k_mbf.onnx daten\\models\\
  del buffalo_s.zip
"""
import argparse
import os
import sys

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox import arena, cadastrar_fotos as cf  # noqa: E402
from aibox import arcface as arcface_mod  # noqa: E402
from aibox.arcface import ArcFace  # noqa: E402

ARCFACE = arcface_mod.CAMINHO


def unit(v):
    v = np.asarray(v, np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def galerias(motor, arc, pasta, nomes):
    """{modelo: (nomes, M, dono)} com as mesmas fotos aceitas nos dois."""
    import cv2
    linhas = {"sface": [], "arcface": []}
    dono = []
    for i, nome in enumerate(nomes):
        d = os.path.join(pasta, nome)
        arquivos = sorted(os.path.join(d, f) for f in os.listdir(d)
                          if os.path.splitext(f)[1].lower() in cf.EXTENSOES)
        sf, af = [], []
        for arq in arquivos:
            img = cf.ler(arq)
            if img is None:
                continue
            melhor = None
            for giro in (None, cv2.ROTATE_90_CLOCKWISE,
                         cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180):
                q = img if giro is None else cv2.rotate(img, giro)
                ls = motor.detect(q, full_res=True)
                if len(ls) and (melhor is None or float(ls[0][14]) > melhor[0]):
                    melhor = (float(ls[0][14]), q, ls)
            if melhor is None or len(melhor[2]) != 1:
                continue
            _, q, ls = melhor
            if not cf.em_pe(ls[0]) or float(ls[0][2]) < cf.ROSTO_MIN_PX:
                continue
            sf.append(unit(motor.embedding(q, ls[0])))
            af.append(unit(arc.embedding(q, ls[0])))
        fora = set(cf.separar_destoantes(sf))
        sf = [v for k, v in enumerate(sf) if k not in fora][:cf.MAXIMO]
        af = [v for k, v in enumerate(af) if k not in fora][:cf.MAXIMO]
        print(f"  {nome}: {len(sf)} fotos")
        linhas["sface"] += sf
        linhas["arcface"] += af
        dono += [i] * len(sf)
    return {k: (nomes, np.array(v, np.float32), np.array(dono)) for k, v in linhas.items()}


def notas(M, dono, n, v, topk):
    s = M @ v
    out = np.full(n, -1.0)
    for i in range(n):
        x = np.sort(s[dono == i])
        if len(x):
            out[i] = float(x[-topk:].mean())
    return out


def ler_video(caminho, motor, arc, gal, a_cada):
    """[(modelo, topk, melhor_nome, nota, segunda)] por rosto bom."""
    import cv2
    from daten.app import config as dcfg
    cap = cv2.VideoCapture(caminho)
    saida, k = [], 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        k += 1
        if k % a_cada:
            continue
        dcfg.DETECT_WIDTH = img.shape[1]
        # SO O MAIOR ROSTO DO QUADRO, que e quem esta na frente da camera. Quem
        # passa ao fundo do video dos autorizados nao e autorizado, e a nota
        # dele entraria na conta como se fosse do dono.
        bons = [l for l in motor.detect(img) if arena.leitura_boa(l)[0]]
        for l in sorted(bons, key=lambda l: -float(l[2]))[:1]:
            vs = {"sface": unit(motor.embedding(img, l)),
                  "arcface": unit(arc.embedding(img, l))}
            for modelo, v in vs.items():
                nomes, M, dono = gal[modelo]
                for topk in (1, 3):
                    x = notas(M, dono, len(nomes), v, topk)
                    o = np.argsort(x)[::-1]
                    saida.append((modelo, topk, nomes[o[0]], x[o[0]],
                                  x[o[1]] if len(o) > 1 else -1.0))
    return saida


def main():
    p = argparse.ArgumentParser(description="SFace contra ArcFace pequeno")
    p.add_argument("--fotos", default=os.path.join(RAIZ, "fotos-cadastro"))
    p.add_argument("--nomes", nargs="+", default=["Daniel", "Lucas", "Matheus", "Samuel"])
    p.add_argument("--estranho", action="append", default=[],
                   help="video so com quem NAO esta na galeria (repita para varios)")
    p.add_argument("--autorizados", action="append", default=[],
                   help="video so com quem ESTA na galeria (repita para varios)")
    p.add_argument("--arcface", default=ARCFACE)
    p.add_argument("--a-cada", type=int, default=2, help="le 1 de cada N quadros")
    a = p.parse_args()

    if not os.path.exists(a.arcface):
        print(f"falta o modelo {a.arcface}. Como baixar: veja o topo deste arquivo.")
        return 2
    if not (a.estranho or a.autorizados):
        print("passe pelo menos um video: --estranho e/ou --autorizados")
        return 2

    from daten.app.recognizer import FaceEngine
    motor, arc = FaceEngine(), ArcFace(a.arcface)
    print("galerias (mesmas fotos nos dois modelos):")
    gal = galerias(motor, arc, a.fotos, a.nomes)

    est = [r for v in a.estranho for r in ler_video(v, motor, arc, gal, a.a_cada)]
    aut = [r for v in a.autorizados for r in ler_video(v, motor, arc, gal, a.a_cada)]
    print(f"\nleituras boas: {len(est) // 4} de estranho, {len(aut) // 4} de autorizado")

    print("\n modelo   nota       | estranho: mediana  maior | dono: pior 5%  mediana"
          " | FOLGA   limiar sugerido")
    resultado = []
    for modelo in ("sface", "arcface"):
        for topk in (1, 3):
            e = np.array([r[3] for r in est if r[0] == modelo and r[1] == topk])
            d = np.array([r[3] for r in aut if r[0] == modelo and r[1] == topk])
            em = f"{np.median(e):6.2f} {e.max():6.2f}" if len(e) else "     -      -"
            dm = (f"{np.percentile(d, 5):6.2f}   {np.median(d):6.2f}" if len(d)
                  else "     -        -")
            if len(e) and len(d):
                folga = float(np.percentile(d, 5) - e.max())
                limiar = (np.percentile(d, 5) + e.max()) / 2
                fx = f"{folga:+6.2f}   {limiar:.2f}" if folga > 0 else f"{folga:+6.2f}   (sobrepoe)"
                resultado.append((folga, modelo, topk))
            else:
                fx = "     -"
            rotulo = "melhor foto" if topk == 1 else "media de 3 "
            print(f" {modelo:8s} {rotulo} |          {em} |        {dm} | {fx}")

    if aut:
        print("\nquem ganhou no video dos autorizados (sface, melhor foto):")
        cont = {}
        for r in aut:
            if r[0] == "sface" and r[1] == 1:
                cont[r[2]] = cont.get(r[2], 0) + 1
        for n, c in sorted(cont.items(), key=lambda x: -x[1]):
            print(f"  {n}: {c} leituras")

    if resultado:
        f, m, t = max(resultado)
        print(f"\nconclusao: a maior folga e do {m} com "
              f"{'a melhor foto' if t == 1 else 'a media das 3 melhores'} ({f:+.2f}). "
              "Folga positiva = existe um limiar que separa todo mundo nestes videos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
