"""Versao NPU: gera os .dlc quantizados e confere a qualidade. Roda no GitHub
Actions (.github/workflows/npu-modelos.yml), nunca na caixa.

    python npu/preparar.py SDK_DIR SAIDA_DIR

O QUE SAI em SAIDA_DIR:
    yunet.dlc            YuNet, 8 bits, entrada fixa 1280x736
    arcface.dlc          ArcFace w600k_mbf, 8 bits nos pesos / 16 nas ativacoes
    pose.dlc             YOLO11n-pose 320, 8 bits nos pesos / 16 nas ativacoes
    *_a8.dlc             as mesmas com 8 bits nas ativacoes (mais rapidas)
    relatorio.txt        a comparacao com o modelo original (ONNX) nas mesmas fotos

As fotos de calibracao sao publicas (LFW e coco128); nenhuma foto do grupo.
"""
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)

SDK, SAIDA = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
TRAB = os.path.join(SAIDA, "_trab")
os.makedirs(TRAB, exist_ok=True)
YUNET_HW = (736, 1280)          # 1280x720 da HAIZ, arredondado para multiplo de 32
POSE = 320
REL = []


def diga(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    REL.append(s)


def binario(nome):
    p = glob.glob(os.path.join(SDK, "bin", "x86_64-linux-clang", nome))
    if not p:
        raise SystemExit(f"falta {nome} no SDK")
    return p[0]


def rodar(*cmd):
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-3000:], flush=True)
    if r.returncode:
        erro = [l for l in (r.stdout + r.stderr).splitlines() if "rror" in l][-4:]
        diga("ERRO:", " | ".join(erro))
        raise SystemExit(f"falhou: {cmd[0]}")


def baixar(url, destino):
    if not os.path.exists(destino):
        print("baixando", url, flush=True)
        urllib.request.urlretrieve(url, destino)
    return destino


# ---------------------------------------------------------------- modelos ---

def modelos():
    import onnx
    yunet = os.path.join(RAIZ, "daten", "models", "face_detection_yunet_2023mar.onnx")
    z = baixar("https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
               os.path.join(TRAB, "buffalo_s.zip"))
    arc = os.path.join(TRAB, "w600k_mbf.onnx")
    if not os.path.exists(arc):
        with zipfile.ZipFile(z) as f:
            nome = [n for n in f.namelist() if n.endswith("w600k_mbf.onnx")][0]
            open(arc, "wb").write(f.read(nome))
    pose = os.path.join(TRAB, "yolo11n-pose.onnx")
    if not os.path.exists(pose):
        import torch
        from ultralytics import YOLO
        from ultralytics.nn.modules.head import Pose

        # O kpts_decode normal fatia os canais de 3 em 3 (y[:, 2::3]), e o
        # conversor do SNPE recusa esse Slice ("Stride is zero"). Esta versao
        # faz a mesma conta com reshape, que vira operacoes que a NPU aceita.
        def kpts_decode(self, *args):          # (bs, kpts) ou (kpts), conforme a versao
            kpts = args[-1]
            bs = kpts.shape[0]
            # Sem fatiar nada: o conversor tambem recusa y[:, :, :2] num
            # tensor de 4 dimensoes. Split vira uma operacao que ele aceita.
            y = kpts.view(bs, *self.kpt_shape, -1)
            xy, vis = torch.split(y, [2, 1], dim=2)
            a = (xy * 2.0 + (self.anchors - 0.5)) * self.strides
            a = torch.cat((a, vis.sigmoid()), 2)
            return a.view(bs, self.nk, -1)
        Pose.kpts_decode = kpts_decode

        # O mesmo para a caixa: dist2bbox usa chunk (vira Slice). Split.
        import ultralytics.nn.modules.head as cabeca

        def dist2bbox(distance, anchor_points, xywh=True, dim=-1):
            lt, rb = torch.split(distance, [2, 2], dim)
            x1y1, x2y2 = anchor_points - lt, anchor_points + rb
            if xywh:
                return torch.cat(((x1y1 + x2y2) / 2, x2y2 - x1y1), dim)
            return torch.cat((x1y1, x2y2), dim)
        cabeca.dist2bbox = dist2bbox
        cwd = os.getcwd()
        os.chdir(TRAB)
        YOLO("yolo11n-pose.pt").export(format="onnx", imgsz=POSE, opset=12,
                                       simplify=True, dynamic=False)
        os.chdir(cwd)
    slices_explicitos(pose)
    nomes = {}
    for k, p in (("yunet", yunet), ("arcface", arc), ("pose", pose)):
        m = onnx.load(p)
        nomes[k] = m.graph.input[0].name
        diga(f"{k}: entrada {nomes[k]}, saidas {[o.name for o in m.graph.output]}")
    return {"yunet": yunet, "arcface": arc, "pose": pose}, nomes


def mostrar_slices(caminho):
    import onnx
    from onnx import numpy_helper
    m = onnx.load(caminho)
    const = {i.name: numpy_helper.to_array(i) for i in m.graph.initializer}
    for n in m.graph.node:
        if n.op_type == "Constant":
            const[n.output[0]] = numpy_helper.to_array(n.attribute[0].t)
    for n in m.graph.node:
        if n.op_type == "Slice" and "model.23" in n.name:
            diga("SLICE", n.name, [(i, const.get(i, "?").tolist() if i in const else "?") for i in n.input[1:]],
                 "de", n.input[0])


def slices_explicitos(caminho):
    """Todo Slice ganha 'axes' e 'steps' explicitos. Sem 'steps', o conversor
    do SNPE 2.26 monta um StridedSlice com passo 0 ("Stride is zero at index
    0") no cabecalho do YOLO-pose. Mesma conta, so escrita por extenso."""
    import onnx
    from onnx import helper, numpy_helper
    m = onnx.load(caminho)
    const = {i.name: numpy_helper.to_array(i) for i in m.graph.initializer}
    for n in m.graph.node:
        if n.op_type == "Constant" and n.attribute and n.attribute[0].name == "value":
            const[n.output[0]] = numpy_helper.to_array(n.attribute[0].t)
    mudou = 0
    for n in m.graph.node:
        if n.op_type != "Slice":
            continue
        starts = const.get(n.input[1])
        if starts is None:
            continue
        k = len(np.atleast_1d(starts))
        ins = list(n.input) + [""] * (5 - len(n.input))
        if not ins[3]:
            nome = n.name + "_axes"
            m.graph.initializer.append(numpy_helper.from_array(np.arange(k, dtype=np.int64), nome))
            ins[3] = nome
        if not ins[4]:
            nome = n.name + "_steps"
            m.graph.initializer.append(numpy_helper.from_array(np.ones(k, dtype=np.int64), nome))
            ins[4] = nome
            mudou += 1
        del n.input[:]
        n.input.extend(ins)
    onnx.save(m, caminho)
    diga(f"[pose] {mudou} Slice ganharam passo explicito")


def converter(onnx_path, dlc, nome_in, dims):
    rodar(binario("snpe-onnx-to-dlc"), "-i", onnx_path, "-o", dlc,
          "--input_dim", nome_in, ",".join(str(d) for d in dims))


# ------------------------------------------------------------ fotos -------

def fotos_coco():
    z = baixar("https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip",
               os.path.join(TRAB, "coco128.zip"))
    d = os.path.join(TRAB, "coco128")
    if not os.path.isdir(d):
        zipfile.ZipFile(z).extractall(TRAB)
    return sorted(glob.glob(os.path.join(d, "images", "*", "*.jpg")))


def fotos_lfw():
    from sklearn.datasets import fetch_lfw_pairs
    p = fetch_lfw_pairs(subset="test", color=True, resize=1.0, slice_=None,
                        data_home=os.path.join(TRAB, "lfw"))
    pares = (p.pairs * (255 if p.pairs.max() <= 1.0 else 1)).astype(np.uint8)
    return pares[..., ::-1].copy(), p.target      # RGB -> BGR, como o cv2 le


def tela_yunet(cv2, img):
    h, w = img.shape[:2]
    e = min(YUNET_HW[1] / w, YUNET_HW[0] / h)
    nw, nh = int(round(w * e)), int(round(h * e))
    t = np.zeros((YUNET_HW[0], YUNET_HW[1], 3), np.uint8)
    t[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return t


def mosaico(cv2, rostos, rng):
    """Uma tela 1280x736 com rostos do LFW espalhados em tamanhos de arena
    (de ~40 a ~250 px), em cima de uma foto do coco128 como fundo."""
    t = np.full((YUNET_HW[0], YUNET_HW[1], 3), rng.integers(30, 200), np.uint8)
    for _ in range(rng.integers(2, 9)):
        r = rostos[rng.integers(len(rostos))]
        lado = int(rng.integers(60, 360))
        r = cv2.resize(r, (lado, lado))
        y = int(rng.integers(0, YUNET_HW[0] - lado))
        x = int(rng.integers(0, YUNET_HW[1] - lado))
        t[y:y + lado, x:x + lado] = r
    return t


def gravar_lista(nome, arrays):
    d = os.path.join(TRAB, nome)
    os.makedirs(d, exist_ok=True)
    linhas = []
    for i, a in enumerate(arrays):
        f = os.path.join(d, f"{i:04d}.raw")
        np.ascontiguousarray(a, np.float32).tofile(f)
        linhas.append(f)
    lista = os.path.join(TRAB, nome + ".txt")
    open(lista, "w").write("\n".join(linhas) + "\n")
    return lista


def quantizar(dlc, lista, saida, a16, saidas=None, extra=()):
    """Quantiza e ja deixa pronto o "cache" do HTP V68 (o grafo compilado para
    a NPU), para a caixa nao compilar na hora. O cache guarda QUAIS saidas
    existem: sem --set_output_tensors ele so tem a ultima camada, e o YuNet
    na caixa devolvia so o kps_32."""
    cmd = [binario("snpe-dlc-quantize"), "--input_dlc", dlc, "--input_list", lista,
           "--output_dlc", saida]
    if a16:
        cmd += ["--act_bitwidth", "16"]
    cmd += list(extra)
    if not saidas:
        cmd += ["--enable_htp", "--htp_socs", "qcs6490"]
    rodar(*cmd)
    if saidas:
        try:
            rodar(binario("snpe-dlc-graph-prepare"), "--input_dlc", saida, "--output_dlc", saida,
                  "--htp_socs", "qcs6490", "--set_output_tensors", ",".join(saidas))
        except SystemExit:
            diga(f"[{os.path.basename(saida)}] sem cache do HTP: a caixa compila na hora (so demora mais para abrir)")


# ---------------------------------------------------------- comparacoes ---

def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    i = max(0, x2 - x1) * max(0, y2 - y1)
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def comparar_yunet(cv2, npu, telas, dlcs):
    ref = cv2.FaceDetectorYN.create(MOD["yunet"], "", (YUNET_HW[1], YUNET_HW[0]),
                                    score_threshold=0.7, nms_threshold=0.3, top_k=50)
    for dlc in dlcs:
        det = npu.DetectorNPU(dlc)
        diga(f"\n[yunet] {os.path.basename(dlc)} rodando na {'NPU' if det.rede.na_npu else 'CPU do SNPE'}")
        achou = total = extra = 0
        erro_pontos = []
        for t in telas:
            _, a = ref.detect(t)
            a = a if a is not None else np.empty((0, 15))
            b = det.detect(t)
            total += len(a)
            usados = set()
            for la in a:
                melhor = max(range(len(b)), key=lambda j: iou(la, b[j]), default=None)
                if melhor is not None and iou(la, b[melhor]) >= 0.5:
                    achou += 1
                    usados.add(melhor)
                    erro_pontos.append(np.abs(la[4:14] - b[melhor][4:14]).mean() / max(la[2], 1))
            extra += len(b) - len(usados)
        diga(f"[yunet] rostos do original achados: {achou}/{total}; a mais: {extra}; "
             f"erro medio dos 5 pontos: {100 * np.mean(erro_pontos or [0]):.1f}% do tamanho do rosto")


def alinhados(cv2, imgs):
    from aibox.arcface import MOLDE
    det = cv2.FaceDetectorYN.create(MOD["yunet"], "", (250, 250), score_threshold=0.7)
    out = []
    for im in imgs:
        det.setInputSize((im.shape[1], im.shape[0]))
        _, f = det.detect(im)
        if f is None:
            out.append(None)
            continue
        l = f[np.argmax(f[:, 2] * f[:, 3])]
        m, _ = cv2.estimateAffinePartial2D(l[4:14].reshape(5, 2), MOLDE, method=cv2.LMEDS)
        out.append(cv2.warpAffine(im, m, (112, 112), borderValue=0))
    return out


def arc_entrada(r):
    return (r[:, :, ::-1].astype(np.float32) - 127.5) / 127.5   # HWC RGB


def comparar_arcface(npu, ort_s, pares, alvo, dlcs):
    a = alinhados(CV2, pares[:, 0])
    b = alinhados(CV2, pares[:, 1])
    ok = [i for i in range(len(alvo)) if a[i] is not None and b[i] is not None]
    nome_in = ort_s.get_inputs()[0].name

    def ref(r):
        v = ort_s.run(None, {nome_in: arc_entrada(r).transpose(2, 0, 1)[None]})[0].ravel()
        return v / np.linalg.norm(v)

    def acc(sims):
        sims, y = np.array(sims), alvo[ok]
        melhor = max(((sims >= t) == y).mean() for t in np.arange(0, 1, 0.01))
        return 100 * melhor

    ra = [ref(a[i]) for i in ok]
    rb = [ref(b[i]) for i in ok]
    diga(f"\n[arcface] {len(ok)} pares do LFW. Original (ONNX): acerto {acc([x @ y for x, y in zip(ra, rb)]):.1f}%")
    for dlc in dlcs:
        n = npu.ArcFaceNPU(dlc)

        def q(r):
            x = arc_entrada(r)
            if not npu._nhwc(n.rede.forma()):
                x = x.transpose(2, 0, 1)
            v = next(iter(n.rede(entrada=x).values())).ravel()
            return v / np.linalg.norm(v)
        qa = [q(a[i]) for i in ok]
        qb = [q(b[i]) for i in ok]
        cos = [x @ y for x, y in zip(ra + rb, qa + qb)]
        diga(f"[arcface] {os.path.basename(dlc)} ({'NPU' if n.rede.na_npu else 'CPU do SNPE'}): "
             f"cosseno com o original medio {np.mean(cos):.4f}, pior {np.min(cos):.4f}; "
             f"acerto {acc([x @ y for x, y in zip(qa, qb)]):.1f}%; "
             f"galeria antiga serve? {'SIM' if np.percentile(cos, 5) >= 0.98 else 'NAO, recadastrar'}")


def comparar_pose(npu, ort_s, fotos, dlcs):
    nome_in = ort_s.get_inputs()[0].name
    for dlc in dlcs:
        rede = npu.Rede(dlc)
        erros, conf = [], []
        for f in fotos[:64]:
            x = CALIB_POSE(f)
            r = ort_s.run(None, {nome_in: x.transpose(2, 0, 1)[None]})[0][0].T   # 2100x56
            xin = x if npu._nhwc(rede.forma()) else x.transpose(2, 0, 1)
            q = next(iter(rede(entrada=xin).values()))
            q = q.reshape(-1, 56) if q.shape[-1] == 56 else q.reshape(56, -1).T
            boas = r[:, 4] > 0.5
            if boas.any():
                kr, kq = r[boas, 5:].reshape(-1, 17, 3), q[boas, 5:].reshape(-1, 17, 3)
                vis = kr[:, :, 2] > 0.5
                if not vis.any():
                    continue
                erros.append(np.abs(kr[:, :, :2] - kq[:, :, :2])[vis].mean() / POSE)
                conf.append(np.abs(r[boas, 4] - q[boas, 4]).mean())
        diga(f"\n[pose] {os.path.basename(dlc)} ({'NPU' if rede.na_npu else 'CPU do SNPE'}): "
             f"erro medio dos pontos {100 * np.mean(erros or [0]):.2f}% da imagem; "
             f"diferenca na nota da pessoa {np.mean(conf or [0]):.3f}")


def comparar_olho(npu, fotos):
    """O caminho inteiro da sala: OlhoNPU (letterbox, rede, NMS, ByteTrack)
    contra o Ultralytics de sempre, nos mesmos pontos do corpo."""
    import cv2
    from ultralytics import YOLO
    ref = YOLO(os.path.join(TRAB, "yolo11n-pose.pt"))
    for dlc in (os.path.join(TRAB, "pose_f.dlc"), os.path.join(SAIDA, "pose.dlc")):
        erros, pessoas_ref, pessoas_npu = [], 0, 0
        for f in fotos[:40]:
            img = cv2.imread(f)
            h, w = img.shape[:2]
            r = ref.predict(img, imgsz=POSE, conf=0.35, classes=[0], verbose=False)[0]
            kr = r.keypoints.xyn.cpu().numpy() if r.keypoints is not None else np.zeros((0, 17, 2))
            olho = npu.OlhoNPU(dlc)
            olho.ver(img)
            saida = olho.ver(img)          # 2a vez: trilhas ja confirmadas
            kq = np.array([[p[:2] for p in kp] for _, kp in saida]).reshape(-1, 17, 2)
            pessoas_ref += len(kr)
            pessoas_npu += len(kq)
            for a in kr:
                if len(kq):
                    d = np.abs(kq - a[None]).mean(axis=(1, 2))
                    erros.append(d.min())
        diga(f"[sala] {os.path.basename(dlc)}: pessoas Ultralytics {pessoas_ref}, NPU {pessoas_npu}; "
             f"erro medio dos pontos {100 * np.mean(erros or [0]):.2f}% da imagem")


# ------------------------------------------------------------------ main ---

if __name__ == "__main__":
    import cv2
    import onnxruntime as ort
    from aibox import npu
    CV2 = cv2
    MOD, NOMES = modelos()
    rng = np.random.default_rng(11)

    dlc = {}
    converter(MOD["yunet"], os.path.join(TRAB, "yunet_f.dlc"), NOMES["yunet"], (1, 3) + YUNET_HW)
    converter(MOD["arcface"], os.path.join(TRAB, "arcface_f.dlc"), NOMES["arcface"], (1, 3, 112, 112))
    try:
        converter(MOD["pose"], os.path.join(TRAB, "pose_f.dlc"), NOMES["pose"], (1, 3, POSE, POSE))
        TEM_POSE = True
    except SystemExit:
        TEM_POSE = False
        diga("[pose] o conversor recusou o YOLO-pose; pacote sai so com rosto")
        mostrar_slices(MOD["pose"])

    # O layout que o .dlc pede (NHWC ou NCHW) sai da propria rede, pelo npu.py
    # rodando no CPU do SNPE x86: isso tambem testa o ctypes antes da caixa.
    os.environ["NPU_RUNTIME"] = "cpu"
    lay = {k: npu._nhwc(npu.Rede(os.path.join(TRAB, f"{k}_f.dlc")).forma())
           for k in (("yunet", "arcface", "pose") if TEM_POSE else ("yunet", "arcface"))}
    diga("layout NHWC:", json.dumps(lay))

    def L(k, x_hwc):
        return x_hwc if lay[k] else x_hwc.transpose(2, 0, 1)

    coco = fotos_coco()
    pares, alvo = fotos_lfw()
    rostos = list(pares[:300, 0]) + list(pares[:300, 1])

    telas = [tela_yunet(cv2, cv2.imread(f)) for f in coco[:40]] + \
            [mosaico(cv2, rostos, rng) for _ in range(60)]
    validar_telas = [mosaico(cv2, rostos[::-1], np.random.default_rng(5)) for _ in range(30)] + \
                    [tela_yunet(cv2, cv2.imread(f)) for f in coco[100:128]]
    lista_y = gravar_lista("cal_yunet", [L("yunet", t.astype(np.float32)) for t in telas])

    arc_cal = [r for r in alinhados(cv2, rostos[:400:2]) if r is not None]
    lista_a = gravar_lista("cal_arcface", [L("arcface", arc_entrada(r)) for r in arc_cal])

    def CALIB_POSE(f):
        im = cv2.imread(f)
        h, w = im.shape[:2]
        e = min(POSE / w, POSE / h)
        nw, nh = int(round(w * e)), int(round(h * e))
        t = np.full((POSE, POSE, 3), 114, np.uint8)
        dx, dy = (POSE - nw) // 2, (POSE - nh) // 2
        t[dy:dy + nh, dx:dx + nw] = cv2.resize(im, (nw, nh))
        return t[:, :, ::-1].astype(np.float32) / 255.0
    globals()["CALIB_POSE"] = CALIB_POSE
    listas = [("yunet", lista_y), ("arcface", lista_a)]
    if TEM_POSE:
        listas.append(("pose", gravar_lista("cal_pose", [L("pose", CALIB_POSE(f)) for f in coco[:100]])))

    for k, lista in listas:
        f = os.path.join(TRAB, f"{k}_f.dlc")
        sai = [f"{t}_{p}" for t in ("cls", "obj", "bbox", "kps") for p in (8, 16, 32)] \
            if k == "yunet" else None
        quantizar(f, lista, os.path.join(SAIDA, f"{k}_a8.dlc"), a16=False, saidas=sai)
        if k != "yunet":
            quantizar(f, lista, os.path.join(SAIDA, f"{k}.dlc"), a16=True)
        else:
            # A RESERVA DO YUNET: 16 bits nas ativacoes. O yunet.dlc (8 bits)
            # e o rapido, mas rosto pequeno e o primeiro a perder nota com 8
            # bits, e isso so aparece na NPU (aqui a CPU do SNPE faz em float).
            # Na caixa: NPU_YUNET=yunet_a16.dlc e o npu_teste.py compara.
            try:
                quantizar(f, lista, os.path.join(SAIDA, "yunet_a16.dlc"), a16=True, saidas=sai)
            except SystemExit:
                diga("[yunet_a16.dlc] o quantizador recusou 16 bits; fica so o de 8")
        if k == "arcface":
            # Tentativas de chegar mais perto do original (cosseno >= ~0.99),
            # para a galeria que ja existe continuar valendo sem recadastro.
            for suf, ext in (("pc", ["--use_per_channel_quantization"]),
                             ("pce", ["--use_per_channel_quantization", "--use_enhanced_quantizer"])):
                try:
                    quantizar(f, lista, os.path.join(SAIDA, f"arcface_{suf}.dlc"), a16=True, extra=ext)
                except SystemExit:
                    diga(f"[arcface_{suf}.dlc] o quantizador recusou {ext}")
    shutil.copy(os.path.join(SAIDA, "yunet_a8.dlc"), os.path.join(SAIDA, "yunet.dlc"))

    # Comparacoes. Primeiro com NPU_RUNTIME=dsp (no x86 o SNPE pode emular o
    # HTP; se nao puder, ele cai para a CPU e o relatorio diz qual foi).
    os.environ["NPU_RUNTIME"] = os.environ.get("CONFERIR_RUNTIME", "dsp")
    diga("\n==== conferencia: o .dlc contra o ONNX original, nas mesmas fotos ====")
    for nome, func in (
            ("yunet", lambda: comparar_yunet(cv2, npu, validar_telas,
                                             [os.path.join(TRAB, "yunet_f.dlc"),
                                              os.path.join(SAIDA, "yunet_a8.dlc")] +
                                             [os.path.join(SAIDA, "yunet_a16.dlc")]
                                             * os.path.exists(os.path.join(SAIDA, "yunet_a16.dlc")))),
            ("arcface", lambda: comparar_arcface(npu, ort.InferenceSession(MOD["arcface"]), pares, alvo,
                                                 [os.path.join(TRAB, "arcface_f.dlc"),
                                                  os.path.join(SAIDA, "arcface.dlc"),
                                                  os.path.join(SAIDA, "arcface_a8.dlc")] +
                                                 [os.path.join(SAIDA, f"arcface_{x}.dlc") for x in ("pc", "pce")
                                                  if os.path.exists(os.path.join(SAIDA, f"arcface_{x}.dlc"))])),
            ("sala", lambda: TEM_POSE and comparar_olho(npu, coco[100:])),
            ("pose", lambda: TEM_POSE and comparar_pose(npu, ort.InferenceSession(MOD["pose"]), coco[100:],
                                           [os.path.join(TRAB, "pose_f.dlc"),
                                            os.path.join(SAIDA, "pose.dlc"),
                                            os.path.join(SAIDA, "pose_a8.dlc")]))):
        try:
            func()
        except Exception as e:
            import traceback
            traceback.print_exc()
            diga(f"[{nome}] conferencia falhou: {e}")
    open(os.path.join(SAIDA, "relatorio.txt"), "w").write("\n".join(REL) + "\n")
    shutil.rmtree(TRAB, ignore_errors=True)
