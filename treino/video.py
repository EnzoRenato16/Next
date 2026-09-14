# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "mediapipe", "opencv-python-headless"]
# ///
"""Transforma um VIDEO numa amostra de treino, do mesmo jeito que a Sala grava.

Serve para aproveitar material que ja existe: uma queda que voces filmaram, um
trecho salvo no cartao da camera, um ensaio que ninguem quer repetir.

Usa o MESMO detector de pose da Sala (vendor/mediapipe/pose_landmarker_lite.task)
e escreve no MESMO arquivo, entao o que sai daqui e indistinguivel do que sai do
botao "Gravar amostra".

  uv run treino/video.py queda caminho/do/video.mp4
  uv run treino/video.py normal ~/videos/*.mp4

AVISO QUE IMPORTA MAIS QUE O RESTO: so vale se o video vier DA CAMERA QUE VAI
SER USADA, no lugar onde ela vai ficar. Video de celular tem outra lente, outra
altura e outro angulo — treinar com ele ensina a camera errada, que e
exatamente o erro que custou um dia inteiro neste projeto.

Do video sai apenas geometria do esqueleto. Nenhum quadro e guardado.

Medido num video real de 130s, 2160x3840, 30fps: 3.309 dos 3.913 quadros
renderam esqueleto (2 minutos de processamento). Os 15% restantes eram quadros
em que a pessoa estava perto demais e saia do enquadramento — o mesmo motivo
que quebra a deteccao ao vivo.
"""
import argparse, glob, json, os, sys
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
MODELO = os.path.join(RAIZ, "vendor", "mediapipe", "pose_landmarker_lite.task")
AMOSTRAS = os.path.join(AQUI, "local", "amostras.jsonl")
VIS_MIN = 0.30

# indices do MediaPipe Pose que a Sala usa
NARIZ = 0
OMBRO_E, OMBRO_D = 11, 12
PULSO_E, PULSO_D = 15, 16
QUADRIL_E, QUADRIL_D = 23, 24
JOELHO_E, JOELHO_D = 25, 26
TORN_E, TORN_D = 27, 28


def geometria(lm, larg, alt):
    """Os mesmos numeros que o auditix-sala.html mede ao vivo, do mesmo jeito.

    Coordenadas normalizadas (0 a 1) como no navegador, e o x corrigido pela
    proporcao do quadro na hora de medir distancia — sem isso, deslocamento
    horizontal sai encolhido e o modelo aprende velocidades erradas."""
    asp = larg / max(alt, 1)
    def pt(a, b):
        pa, pb = lm[a], lm[b]
        if pa.visibility < VIS_MIN and pb.visibility < VIS_MIN:
            return None
        return ((pa.x + pb.x) / 2, (pa.y + pb.y) / 2)

    o, h = pt(OMBRO_E, OMBRO_D), pt(QUADRIL_E, QUADRIL_D)
    if not o or not h:
        return None
    jo, to = pt(JOELHO_E, JOELHO_D), pt(TORN_E, TORN_D)
    if to:
        altura = abs(to[1] - o[1]) * 1.25
    elif jo:
        altura = abs(jo[1] - o[1]) * 1.9
    else:
        altura = abs(o[1] - h[1]) * 3.2
    if altura < 1e-6:
        return None

    eixo = float(np.hypot((o[0] - h[0]) * asp, o[1] - h[1]))
    ang = float(abs(np.degrees(np.arctan2((o[0] - h[0]) * asp, h[1] - o[1]))))
    ombro = float(np.hypot((lm[OMBRO_E].x - lm[OMBRO_D].x) * asp,
                           lm[OMBRO_E].y - lm[OMBRO_D].y))
    vis = [p for p in lm if p.visibility >= VIS_MIN]
    if len(vis) > 2:
        xs = [p.x for p in vis]; ys = [p.y for p in vis]
        prop = (max(xs) - min(xs)) / max(max(ys) - min(ys), 1e-6)
    else:
        prop = 0.0
    return dict(qx=h[0], qy=h[1], altura=altura, eixo=eixo, ang=ang,
                ombro=ombro, prop=prop,
                pxx=lm[PULSO_E].x, pxy=lm[PULSO_E].y,
                pdx=lm[PULSO_D].x, pdy=lm[PULSO_D].y)


def do_video(caminho, detector):
    import cv2
    import mediapipe as mp
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        print(f"  nao consegui abrir {caminho}")
        return None, 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    quadros, n, perdidos = [], 0, 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        alt, larg = img.shape[:2]
        mpimg = mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        r = detector.detect_for_video(mpimg, int(n * 1000 / fps))
        n += 1
        if not r.pose_landmarks:
            perdidos += 1
            continue
        g = geometria(r.pose_landmarks[0], larg, alt)
        if not g:
            perdidos += 1
            continue
        quadros.append(dict(corpo=1, t=round(n * 1000 / fps),
                            **{k: round(float(v), 5) for k, v in g.items()}))
    cap.release()
    return quadros, perdidos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rotulo", help="queda, normal, agachar, corrida, deitar, engano")
    ap.add_argument("videos", nargs="+")
    args = ap.parse_args()

    if not os.path.exists(MODELO):
        print(f"nao achei o detector em {MODELO}")
        return 1
    import mediapipe as mp
    from mediapipe.tasks.python import vision, BaseOptions
    det = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODELO),
        running_mode=vision.RunningMode.VIDEO,
        min_pose_detection_confidence=0.6, min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6))

    arqs = [a for p in args.videos for a in sorted(glob.glob(p))]
    if not arqs:
        print("nenhum video encontrado nesse caminho.")
        return 1
    # So cria a pasta quando houver o que guardar: arquivo vazio faz o
    # local.py achar que existem amostras e nao existem.
    linhas, guardados = [], 0
    for a in arqs:
        print(f"{os.path.basename(a)}:", end=" ", flush=True)
        quadros, perdidos = do_video(a, det)
        if not quadros:
            print("nenhum corpo detectado — descartado")
            continue
        if len(quadros) < 10:
            print(f"so {len(quadros)} quadros com corpo — descartado")
            continue
        linhas.append(json.dumps({"rotulo": args.rotulo, "sessao": abs(hash(a)) % 10**9,
                                  "fps": 30, "gravada": "video:" + os.path.basename(a),
                                  "quadros": quadros}, ensure_ascii=False))
        guardados += 1
        aviso = f", {perdidos} quadros sem corpo" if perdidos else ""
        print(f"{len(quadros)} quadros{aviso}")
    if linhas:
        os.makedirs(os.path.dirname(AMOSTRAS), exist_ok=True)
        with open(AMOSTRAS, "a", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
    print(f"\n{guardados} de {len(arqs)} videos viraram amostra '{args.rotulo}'.")
    print("Confira com: uv run treino/local.py --listar")
    if guardados:
        print("\nLembre: isto so ajuda se o video vier da camera que vai ser usada,")
        print("no lugar onde ela vai ficar. Video de celular ensina a camera errada.")
    return 0


if __name__ == "__main__":
    codigo = main()
    # O mediapipe 1.0.1 reclama ao ser desmontado ("NoneType is not callable").
    # E ruido de saida, depois de todo o trabalho feito — deixar aparecer faria
    # parecer que falhou.
    os._exit(codigo)
