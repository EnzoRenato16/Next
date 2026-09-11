"""Transforma os CSVs de keypoints do Fall Vision em janelas com rótulo.

O dataset (Harvard Dataverse, CC0) traz 17 pontos por quadro, no formato COCO.
Os 17 existem TODOS no MediaPipe que a Sala já roda, e essa é a razão de ele
servir: o que sai daqui é calculável ao vivo, no navegador, sem nada novo.

A saída é uma janela de ~1s descrita por numeros que NAO dependem da distancia
da camera nem do tamanho da pessoa. Isso e o ponto: um modelo treinado em
pixels de outra sala nao serve para a nossa.
"""
import csv, glob, os, sys, numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
DADOS = os.environ.get("DADOS", "/tmp/ds")
FPS = 30.0
JANELA = 30          # quadros: 1 segundo
PASSO = 5

# nomes no CSV -> o que a gente usa
OMBRO_E, OMBRO_D = "Left Shoulder", "Right Shoulder"
QUADRIL_E, QUADRIL_D = "Left Hip", "Right Hip"
JOELHO_E, JOELHO_D = "Left Knee", "Right Knee"
TORN_E, TORN_D = "Left Ankle", "Right Ankle"
PULSO_E, PULSO_D = "Left Wrist", "Right Wrist"
CONF_MIN = 0.30


def ler_clipe(caminho):
    """CSV longo (uma linha por ponto) -> lista de dicionarios por quadro."""
    quadros = {}
    with open(caminho, newline="") as f:
        r = csv.reader(f)
        next(r, None)
        for linha in r:
            if len(linha) < 5:
                continue
            n = int(linha[0])
            quadros.setdefault(n, {})[linha[1]] = (
                float(linha[2]), float(linha[3]), float(linha[4]))
    return [quadros[k] for k in sorted(quadros)]


def geometria(q):
    """Por quadro: os mesmos numeros que a Sala mede ao vivo."""
    def pt(a, b):
        pa, pb = q.get(a), q.get(b)
        if not pa or not pb:
            return None
        if pa[2] < CONF_MIN and pb[2] < CONF_MIN:
            return None
        return ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)

    o, h = pt(OMBRO_E, OMBRO_D), pt(QUADRIL_E, QUADRIL_D)
    if not o or not h:
        return None
    jo, to = pt(JOELHO_E, JOELHO_D), pt(TORN_E, TORN_D)

    # A regua. Mesma escada de estimativas do auditix-sala.html: se o tornozelo
    # aparece usa ele, senao o joelho, senao a proporcao do tronco.
    if to:
        altura = abs(to[1] - o[1]) * 1.25
    elif jo:
        altura = abs(jo[1] - o[1]) * 1.9
    else:
        altura = abs(o[1] - h[1]) * 3.2
    if altura < 1e-6:
        return None

    eixo = float(np.hypot(o[0] - h[0], o[1] - h[1]))          # tronco no proprio eixo
    ang = abs(np.degrees(np.arctan2(o[0] - h[0], h[1] - o[1])))
    oe, od = q.get(OMBRO_E), q.get(OMBRO_D)
    ombro = float(np.hypot(oe[0] - od[0], oe[1] - od[1])) if oe and od else 0.0

    # Caixa do corpo: a proporcao dela e o sinal classico de "esta deitado".
    xs = [p[0] for p in q.values() if p[2] >= CONF_MIN]
    ys = [p[1] for p in q.values() if p[2] >= CONF_MIN]
    largura = (max(xs) - min(xs)) if len(xs) > 2 else 0.0
    alto = (max(ys) - min(ys)) if len(ys) > 2 else 1.0
    return dict(hx=h[0], hy=h[1], altura=altura, eixo=eixo, ang=ang,
                ombro=ombro, prop=largura / max(alto, 1e-6))


def caracteristicas(g, i0, i1):
    """Uma janela -> 12 numeros, todos adimensionais."""
    j = [x for x in g[i0:i1] if x]
    if len(j) < JANELA // 2:
        return None
    reg = max(x["altura"] for x in j)      # o tamanho que a pessoa TINHA
    if reg < 1e-6:
        return None
    hy = np.array([x["hy"] for x in j])
    hx = np.array([x["hx"] for x in j])
    ang = np.array([x["ang"] for x in j])
    alt = np.array([x["altura"] for x in j])
    eixo = np.array([x["eixo"] for x in j])
    omb = np.array([x["ombro"] for x in j])
    prop = np.array([x["prop"] for x in j])
    dt = 1.0 / FPS

    # queda do quadril: total na janela e a mais rapida em 0,5s
    meia = max(2, int(FPS * 0.5))
    desc = max((hy[k] - hy[max(0, k - meia)]) for k in range(len(hy))) / reg

    return np.array([
        (hy.max() - hy.min()) / reg,                 # 0 amplitude vertical
        desc,                                        # 1 descida mais rapida em 0,5s
        np.abs(np.diff(hx)).max() / reg / dt if len(hx) > 1 else 0,  # 2 pico lateral
        ang.max() / 90.0,                            # 3 tronco mais deitado
        ang.mean() / 90.0,                           # 4 tronco medio
        ang[-max(1, len(ang)//3):].mean() / 90.0,    # 5 tronco no fim da janela
        alt.min() / reg,                             # 6 quanto encolheu
        alt[-max(1, len(alt)//3):].mean() / reg,     # 7 altura no fim
        eixo.min() / max(eixo.max(), 1e-6),          # 8 encurtamento do tronco
        omb.min() / max(omb.max(), 1e-6),            # 9 variacao do ombro
        prop.max(),                                  # 10 caixa mais larga que alta
        prop[-max(1, len(prop)//3):].mean(),         # 11 proporcao no fim
    ], dtype=np.float32)


def janelas_do_clipe(caminho):
    g = [geometria(q) for q in ler_clipe(caminho)]
    saida = []
    for i in range(0, max(1, len(g) - JANELA + 1), PASSO):
        c = caracteristicas(g, i, i + JANELA)
        if c is not None and np.isfinite(c).all():
            saida.append(c)
    return np.array(saida, dtype=np.float32) if saida else None


def main():
    pastas = sorted(d for d in os.listdir(DADOS) if d.endswith("_keypoints_csv"))
    X, dono, rot, grupo = [], [], [], []
    for pi, pasta in enumerate(pastas):
        queda = 1 if pasta.startswith("f_") else 0
        arqs = sorted(glob.glob(os.path.join(DADOS, pasta, "*.csv")))
        for ai, a in enumerate(arqs):
            try:
                w = janelas_do_clipe(a)
            except Exception:
                continue
            if w is None or len(w) == 0:
                continue
            X.append(w)
            dono.append(np.full(len(w), len(rot), dtype=np.int32))
            rot.append(queda)
            grupo.append(pi)
        print(f"  {pasta}: {len(arqs)} clipes", flush=True)
    X = np.concatenate(X); dono = np.concatenate(dono)
    rot = np.array(rot, dtype=np.int8); grupo = np.array(grupo, dtype=np.int16)
    np.savez_compressed(os.path.join(AQUI, "janelas.npz"),
                        X=X, dono=dono, rot=rot, grupo=grupo, pastas=np.array(pastas))
    print(f"\njanelas {X.shape}  clipes {len(rot)}  quedas {int(rot.sum())}")


if __name__ == "__main__":
    main()
