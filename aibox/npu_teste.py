"""VERSAO NPU: o teste na caixa. Carrega cada .dlc na NPU, mede o tempo e
compara com o modelo de hoje (CPU) nas MESMAS imagens.

    source aibox/npu_env.sh && $P aibox/npu_teste.py [foto.jpg ...]

ALGUEM NA FRENTE DA CAMERA. Sem foto, le uns 12 quadros da CAMERA_ARENA pelo
GStreamer (o OpenCV da caixa nao abre RTSP: armadilha 1). Sem rosto nos
quadros, o ArcFace NAO e comparado, e o teste diz isso em vez de calar.

POR QUE NA CAIXA E NAO SO NO GITHUB. No GitHub o SNPE roda o .dlc na CPU dele,
e a CPU DESQUANTIZA a rede: a conta sai em float. Os 8/16 bits das ativacoes
so existem de verdade na NPU. Os numeros do relatorio do CI medem o efeito dos
pesos quantizados; este aqui mede o resto.

Nao grava nada, nao abre porta, nao mexe em ~/auditix.
"""
import os
import sys
import time

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox import npu  # noqa: E402

FAIXAS = ((0, 32), (32, 48), (48, 80), (80, 10000))   # largura do rosto, px do quadro


def tempo(f, n=20):
    f()
    t0 = time.monotonic()
    for _ in range(n):
        f()
    return 1000 * (time.monotonic() - t0) / n


def quadros(cv2):
    """Fotos da linha de comando, ou ~12 quadros da camera da arena."""
    if len(sys.argv) > 1:
        imgs = [cv2.imread(f) for f in sys.argv[1:]]
        return [i for i in imgs if i is not None]
    url = os.environ.get("CAMERA_ARENA", "")
    if url.startswith("rtsp"):
        from aibox.gstcam import Gst, sem_senha
        larg = int(os.environ.get("ARENA_LARG", "1920"))
        alt = int(os.environ.get("ARENA_ALT", "1080"))
        print(f"lendo a camera {sem_senha(url)[:60]}... (UMA conexao, ~10 s)", flush=True)
        cap = Gst(url, larg, alt, 2, bordas=True)
        saida, primeiro, fim = [], None, time.monotonic() + 20
        try:
            while time.monotonic() < fim and len(saida) < 12:
                ok, q = cap.read()
                if not ok:
                    if ok is False:
                        break               # o gst morreu (senha? 403?)
                    time.sleep(0.05)
                    continue
                agora = time.monotonic()
                primeiro = primeiro or agora
                # Os primeiros quadros podem vir antes do quadro-chave (cinza
                # ou borrado): pula 2 s antes de guardar.
                if agora - primeiro >= 2.0:
                    saida.append(q.copy())
                    time.sleep(0.5)
        finally:
            cap.release()
        if saida:
            return saida
        print("(a camera nao entregou quadro; veja o erro do GStreamer acima)")
    print("(sem camera: imagem de teste, so serve para o TEMPO; qualidade nao e medida)")
    return [np.random.default_rng(1).integers(0, 255, (1080, 1920, 3), np.uint8)]


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    i = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def faixa(w):
    for lo, hi in FAIXAS:
        if lo <= w < hi:
            return f"{lo}-{hi if hi < 10000 else ''}px"
    return "?"


def main():
    import cv2
    try:
        from aibox.sala import carregar_env
        carregar_env()
    except Exception:
        pass
    from aibox import arena
    arena.configurar("arcface")
    imgs = quadros(cv2)
    print(f"{len(imgs)} imagem(ns) {imgs[0].shape[1]}x{imgs[0].shape[0]}")
    print(f"runtime pedido: {os.environ.get('NPU_RUNTIME', 'dsp')}  "
          f"SNPE_LIB={os.environ.get('SNPE_LIB', '(padrao)')}")

    # ------------------------------------------------------------ YuNet ---
    cpu = cv2.FaceDetectorYN.create(os.path.join(RAIZ, "daten", "models",
                                                 "face_detection_yunet_2023mar.onnx"),
                                    "", (320, 320), score_threshold=0.7, nms_threshold=0.3)

    def det_cpu(img):
        """O que a arena da CPU faz: busca em 1280 de largura, volta para o quadro."""
        e = 1280 / img.shape[1]
        menor = cv2.resize(img, (1280, int(round(img.shape[0] * e))), interpolation=cv2.INTER_AREA)
        cpu.setInputSize((menor.shape[1], menor.shape[0]))
        _, a = cpu.detect(menor)
        if a is None:
            return np.empty((0, 15), np.float32)
        a = a.copy()
        a[:, :14] /= e
        return a

    print(f"\n[YuNet] CPU: {tempo(lambda: det_cpu(imgs[0])):.0f} ms (com redimensionar)")
    det = npu.tentar(npu.DetectorNPU, "YuNet")
    if det:
        print(f"[YuNet] NPU: {tempo(lambda: det.detect(imgs[0])):.0f} ms (com redimensionar e decodificar)")
        # QUALIDADE: o que importa para o juiz e quantas leituras BOAS saem
        # (nota >= ARENA_NOTA_MIN, largura >= ARENA_ROSTO_MIN, de frente).
        por = {}
        difs, pontos = [], []
        for img in imgs:
            a, b = det_cpu(img), det.detect(img)
            usados = set()
            for la in a:
                k = faixa(float(la[2]))
                d = por.setdefault(k, [0, 0, 0, 0])   # cpu, npu achou, cpu boas, npu boas
                d[0] += 1
                d[2] += int(arena.leitura_boa(la)[0])
                j = max(range(len(b)), key=lambda x: iou(la, b[x]), default=None)
                if j is not None and iou(la, b[j]) >= 0.5:
                    usados.add(j)
                    d[1] += 1
                    d[3] += int(arena.leitura_boa(b[j])[0])
                    difs.append(float(b[j][14] - la[14]))
                    pontos.append(float(np.abs(b[j][4:14] - la[4:14]).mean() / max(la[2], 1)))
            extra = len(b) - len(usados)
            if extra:
                por.setdefault("so na NPU", [0, 0, 0, 0])[1] += extra
        if not por:
            print("[YuNet] nenhum rosto nas imagens: a QUALIDADE da NPU nao foi medida")
        else:
            print("[YuNet] faixa       CPU achou  NPU achou   leituras boas CPU -> NPU")
            for k in sorted(por, key=lambda s: (not s[0].isdigit(), int(s.split("-")[0]) if s[0].isdigit() else 0)):
                c, n, cb, nb = por[k]
                print(f"        {k:<11} {c:>6}     {n:>6}       {cb:>4} -> {nb}")
            if difs:
                print(f"[YuNet] nota NPU - CPU: media {np.mean(difs):+.3f}, pior {min(difs):+.3f} "
                      f"(o portao da arena e {arena.NOTA_MIN:.2f}); erro dos 5 pontos "
                      f"{100 * np.mean(pontos):.1f}% do rosto")

    # ----------------------------------------------------------- ArcFace ---
    rostos = [(img, l) for img in imgs for l in det_cpu(img)
              if float(l[2]) >= arena.ROSTO_MIN and float(l[14]) >= 0.7]
    nomes, M, dono = [], None, None
    try:
        from aibox import galeria
        nomes, M, dono = galeria.matriz(os.environ.get("GALERIA") or galeria.PADRAO)
        if galeria.motor_de(os.environ.get("GALERIA") or galeria.PADRAO) != "arcface":
            nomes = []
    except Exception:
        nomes = []
    if not rostos:
        print("\n[ArcFace] NAO MEDIDO: nenhum rosto de 32 px ou mais nas imagens. "
              "Rode de novo com alguem a 1-3 m da camera, olhando para ela.")
    else:
        from aibox.arcface import ArcFace
        ref = ArcFace()
        img0, l0 = rostos[0]
        print(f"\n[ArcFace] {len(rostos)} rosto(s) para comparar. "
              f"CPU: {tempo(lambda: ref.embedding(img0, l0)):.0f} ms por rosto")
        vref = [ref.embedding(img, l) for img, l in rostos]
        for nome in ("arcface_pc.dlc", "arcface_pce.dlc", "arcface.dlc", "arcface_a8.dlc"):
            if not os.path.exists(os.path.join(npu.NPU_DIR, nome)):
                continue
            q = npu.tentar(lambda: npu.ArcFaceNPU(os.path.join(npu.NPU_DIR, nome)), nome)
            if not q:
                continue
            cos, dnota = [], []
            for (img, l), va in zip(rostos, vref):
                vb = q.embedding(img, l)
                ua, ub = va / np.linalg.norm(va), vb / np.linalg.norm(vb)
                cos.append(float(ua @ ub))
                if nomes and len(M):
                    # O que o juiz ve: a nota contra cada foto da galeria.
                    dnota.append(float(np.abs(M @ ua - M @ ub).max()))
            linha = (f"[ArcFace] {nome}: {tempo(lambda: q.embedding(img0, l0)):.0f} ms, "
                     f"cosseno com a CPU medio {np.mean(cos):.4f}, pior {min(cos):.4f}")
            if dnota:
                linha += f"; nota contra a galeria muda no maximo {max(dnota):.3f}"
            veredito = "SERVE" if min(cos) >= 0.98 and (not dnota or max(dnota) <= 0.02) else "NAO SERVE"
            print(linha + f"  -> {veredito} para a galeria de hoje")

    # -------------------------------------------------------------- pose ---
    for nome in ("pose.dlc", "pose_a8.dlc"):
        if not os.path.exists(os.path.join(npu.NPU_DIR, nome)):
            continue
        r = npu.tentar(lambda: npu.Rede(os.path.join(npu.NPU_DIR, nome)), nome)
        if r:
            x = np.zeros(r.forma(), np.float32)
            print(f"\n[pose] {nome}: {tempo(lambda: r(entrada=x)):.0f} ms so a rede "
                  f"(na CPU, ONNX 320: ~110 ms)")
            r.fechar()
    # O CAMINHO INTEIRO DA SALA na caixa: letterbox, rede, NMS e o ByteTrack
    # do Ultralytics DESTA caixa (o CI testou com o Ultralytics novo; o da
    # caixa e mais antigo, e o OlhoNPU entrega a ele um objeto imitado).
    olho = npu.tentar(npu.OlhoNPU, "sala (OlhoNPU + ByteTrack da caixa)")
    if olho:
        try:
            for img in imgs:
                pessoas = olho.ver(img)
            print(f"[sala] OlhoNPU.ver: {tempo(lambda: olho.ver(imgs[0]), 10):.0f} ms por quadro, "
                  f"{len(pessoas)} pessoa(s) no ultimo quadro"
                  + (" (ninguem na imagem, ou o ByteTrack nao confirmou: ver no ir.sh)"
                     if not pessoas else ""))
        except Exception as e:
            print(f"[sala] OlhoNPU.ver FALHOU na caixa: {type(e).__name__}: {e}. "
                  "A sala continua no OlhoYolo da CPU.")


if __name__ == "__main__":
    main()
