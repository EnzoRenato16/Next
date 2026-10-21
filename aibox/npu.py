"""A NPU (Hexagon V68 / HTP) da AIBOX, pelo SNPE 2.12 que ja vem na caixa.

VERSAO NPU (ramo npu/divisao-npu-cpu). A versao da final e a outra pasta.

QUEM FAZ O QUE:
    NPU  -> as redes: YuNet (acha rosto), ArcFace (numeros do rosto), YOLO-pose
    CPU  -> decodificar a camera, redimensionar, decodificar a saida da rede,
            rastrear, o juiz, as regras, a pagina.
As redes eram ~todo o custo de CPU da arena e da sala; o resto e barato.

COMO O PYTHON FALA COM A NPU. O ONNX Runtime da caixa (1.16.3) nao tem o
provedor da NPU, e o SNPE 2.x nao tem modulo Python. Mas o libSNPE.so tem um
C API (as funcoes Snpe_*), e o ctypes chama C direto, sem compilar nada. O
modelo vai como .dlc quantizado (8 bits), convertido no GitHub Actions com o
MESMO SNPE 2.12 da caixa (.github/workflows/npu-modelos.yml).

NADA QUEBRA SE A NPU FALTAR. Qualquer erro aqui (lib que nao abre, sem
permissao no /dev/adsprpc-smd, .dlc que falta) vira um aviso e o chamador
volta para a CPU, que e o caminho de hoje. NPU=0 no .env forca a CPU.

Variaveis:
    NPU=1|0              liga/desliga (padrao 1: tenta, e cai para CPU)
    SNPE_LIB=...         caminho do libSNPE.so (padrao: npu-lib/ do pacote,
                         que e do mesmo SNPE que gerou os .dlc; depois /root/lib)
    NPU_RUNTIME=dsp      dsp (a NPU), gpu ou cpu; a ordem cai para cpu no fim
    NPU_DIR=...          onde ficam os .dlc (padrao: daten/models/npu)
"""
import ctypes
import os
import time

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPU_DIR = os.environ.get("NPU_DIR") or os.path.join(RAIZ, "daten", "models", "npu")

# enum Snpe_Runtime_t e Snpe_PerformanceProfile_t do SNPE 2.x
RUNTIME = {"cpu": 0, "gpu": 1, "dsp": 2}
BURST = 5

_lib = None


def ligada():
    return os.environ.get("NPU", "1").strip() not in ("0", "nao", "false", "")


def _abrir_lib():
    global _lib
    if _lib is not None:
        return _lib
    candidatos = [os.environ.get("SNPE_LIB"), os.path.join(RAIZ, "npu-lib", "libSNPE.so"),
                  "/root/lib/libSNPE.so",
                  "/usr/lib/libSNPE.so", "libSNPE.so"]
    erros = []
    for c in candidatos:
        if not c:
            continue
        try:
            lib = ctypes.CDLL(c)
        except OSError as e:
            erros.append(f"{c}: {e}")
            continue
        _tipos(lib)
        _lib = lib
        return lib
    raise OSError("libSNPE.so nao abriu: " + " | ".join(erros))


def _tipos(lib):
    H, P, S, I = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int
    sig = {
        "Snpe_DlContainer_Open": (H, [P]),
        "Snpe_DlContainer_Delete": (I, [H]),
        "Snpe_SNPEBuilder_Create": (H, [H]),
        "Snpe_SNPEBuilder_Delete": (I, [H]),
        "Snpe_SNPEBuilder_SetRuntimeProcessorOrder": (I, [H, H]),
        "Snpe_SNPEBuilder_SetPerformanceProfile": (I, [H, I]),
        "Snpe_SNPEBuilder_SetOutputTensors": (I, [H, H]),
        "Snpe_SNPEBuilder_Build": (H, [H]),
        "Snpe_RuntimeList_Create": (H, []),
        "Snpe_RuntimeList_Add": (I, [H, I]),
        "Snpe_RuntimeList_Delete": (I, [H]),
        "Snpe_StringList_Create": (H, []),
        "Snpe_StringList_Append": (I, [H, P]),
        "Snpe_StringList_Size": (S, [H]),
        "Snpe_StringList_At": (P, [H, S]),
        "Snpe_StringList_Delete": (I, [H]),
        "Snpe_SNPE_GetInputTensorNames": (H, [H]),
        "Snpe_SNPE_GetOutputTensorNames": (H, [H]),
        "Snpe_SNPE_GetInputDimensions": (H, [H, P]),
        "Snpe_SNPE_ExecuteITensors": (I, [H, H, H]),
        "Snpe_SNPE_Delete": (I, [H]),
        "Snpe_TensorShape_Rank": (S, [H]),
        "Snpe_TensorShape_At": (S, [H, S]),
        "Snpe_TensorShape_Delete": (I, [H]),
        "Snpe_Util_CreateITensor": (H, [H]),
        "Snpe_Util_IsRuntimeAvailable": (I, [I]),
        "Snpe_ITensor_GetData": (ctypes.c_void_p, [H]),
        "Snpe_ITensor_GetSize": (S, [H]),
        "Snpe_ITensor_GetShape": (H, [H]),
        "Snpe_ITensor_Delete": (I, [H]),
        "Snpe_TensorMap_Create": (H, []),
        "Snpe_TensorMap_Add": (None, [H, P, H]),
        "Snpe_TensorMap_GetTensorNames": (H, [H]),
        "Snpe_TensorMap_GetTensor_Ref": (H, [H, P]),
        "Snpe_TensorMap_Clear": (None, [H]),
        "Snpe_TensorMap_Delete": (I, [H]),
        "Snpe_ErrorCode_getLastErrorString": (P, []),
    }
    for nome, (res, args) in sig.items():
        f = getattr(lib, nome, None)
        if f is None:
            continue            # quem precisar dela reclama com o nome certo
        f.restype, f.argtypes = res, args


def _erro(lib, onde):
    f = getattr(lib, "Snpe_ErrorCode_getLastErrorString", None)
    msg = f().decode(errors="replace") if f else "?"
    return RuntimeError(f"SNPE: {onde}: {msg}")


def _lista(lib, h):
    nomes = [lib.Snpe_StringList_At(h, i).decode()
             for i in range(lib.Snpe_StringList_Size(h))]
    lib.Snpe_StringList_Delete(h)
    return nomes


def _forma(lib, h):
    return tuple(int(lib.Snpe_TensorShape_At(h, i))
                 for i in range(lib.Snpe_TensorShape_Rank(h)))


class Rede:
    """Um .dlc carregado na NPU. Os tensores de entrada sao criados UMA vez
    (forma fixa) e reaproveitados a cada quadro: so os numeros mudam."""

    def __init__(self, dlc, runtime=None, saidas=None):
        lib = _abrir_lib()
        self.lib = lib
        if not os.path.exists(dlc):
            raise FileNotFoundError(f"falta {dlc} (sai do workflow npu-modelos)")
        runtime = (runtime or os.environ.get("NPU_RUNTIME", "dsp")).lower()
        self.pedido = runtime
        cont = lib.Snpe_DlContainer_Open(dlc.encode())
        if not cont:
            raise _erro(lib, f"abrir {dlc}")
        b = lib.Snpe_SNPEBuilder_Create(cont)
        rl = lib.Snpe_RuntimeList_Create()
        ordem = [runtime] + (["cpu"] if runtime != "cpu" else [])
        for r in ordem:
            lib.Snpe_RuntimeList_Add(rl, RUNTIME[r])
        lib.Snpe_SNPEBuilder_SetRuntimeProcessorOrder(b, rl)
        lib.Snpe_SNPEBuilder_SetPerformanceProfile(b, BURST)
        if saidas:
            sl = lib.Snpe_StringList_Create()
            for s in saidas:
                lib.Snpe_StringList_Append(sl, s.encode())
            lib.Snpe_SNPEBuilder_SetOutputTensors(b, sl)
        self.snpe = lib.Snpe_SNPEBuilder_Build(b)
        lib.Snpe_RuntimeList_Delete(rl)
        lib.Snpe_SNPEBuilder_Delete(b)
        lib.Snpe_DlContainer_Delete(cont)
        if not self.snpe:
            raise _erro(lib, f"montar {os.path.basename(dlc)} no {runtime}")
        # Quem realmente roda: a NPU so "existe" para o SNPE se o processo
        # abriu o /dev/adsprpc-smd. Sem permissao, ele cai para a CPU calado,
        # e e por isso que isto e conferido e impresso.
        self.na_npu = bool(lib.Snpe_Util_IsRuntimeAvailable(RUNTIME[runtime])) \
            if runtime != "cpu" else False

        self.entradas = {}
        self.mapa_in = lib.Snpe_TensorMap_Create()
        for nome in _lista(lib, lib.Snpe_SNPE_GetInputTensorNames(self.snpe)):
            fh = lib.Snpe_SNPE_GetInputDimensions(self.snpe, nome.encode())
            forma = _forma(lib, fh)
            t = lib.Snpe_Util_CreateITensor(fh)
            lib.Snpe_TensorShape_Delete(fh)
            buf = np.ctypeslib.as_array(
                ctypes.cast(lib.Snpe_ITensor_GetData(t), ctypes.POINTER(ctypes.c_float)),
                shape=(int(lib.Snpe_ITensor_GetSize(t)),))
            lib.Snpe_TensorMap_Add(self.mapa_in, nome.encode(), t)
            self.entradas[nome] = (forma, buf, t)
        self.mapa_out = lib.Snpe_TensorMap_Create()

    def forma(self, nome=None):
        nome = nome or next(iter(self.entradas))
        return self.entradas[nome][0]

    def __call__(self, **dados):
        lib = self.lib
        if len(dados) == 1 and len(self.entradas) == 1:
            dados = {next(iter(self.entradas)): next(iter(dados.values()))}
        for nome, arr in dados.items():
            forma, buf, _ = self.entradas[nome]
            buf[:] = np.asarray(arr, np.float32).ravel()
        lib.Snpe_TensorMap_Clear(self.mapa_out)
        if not lib.Snpe_SNPE_ExecuteITensors(self.snpe, self.mapa_in, self.mapa_out) == 0:
            raise _erro(lib, "executar")
        saida = {}
        for nome in _lista(lib, lib.Snpe_TensorMap_GetTensorNames(self.mapa_out)):
            t = lib.Snpe_TensorMap_GetTensor_Ref(self.mapa_out, nome.encode())
            fh = lib.Snpe_ITensor_GetShape(t)
            forma = _forma(lib, fh)
            lib.Snpe_TensorShape_Delete(fh)
            n = int(lib.Snpe_ITensor_GetSize(t))
            ptr = ctypes.cast(lib.Snpe_ITensor_GetData(t), ctypes.POINTER(ctypes.c_float))
            saida[nome] = np.ctypeslib.as_array(ptr, shape=(n,)).copy().reshape(forma)
        return saida

    def fechar(self):
        if self.snpe:
            self.lib.Snpe_SNPE_Delete(self.snpe)
            self.snpe = None


def _pegar(saida, chave):
    """Saida pelo nome do ONNX. O conversor as vezes acrescenta sufixo
    (':0', '_permute'), entao vale o nome que COMECA igual."""
    if chave in saida:
        return saida[chave]
    for k, v in saida.items():
        if k.split(":")[0] == chave or k.startswith(chave):
            return v
    raise KeyError(f"a rede nao devolveu {chave!r} (tem: {sorted(saida)})")


def _nhwc(forma):
    """O SNPE guarda imagem como NHWC; o ONNX era NCHW. Diz qual veio."""
    return len(forma) == 4 and forma[-1] == 3


def _imagem(rede, img_bgr):
    forma = rede.forma()
    x = img_bgr.astype(np.float32)
    if not _nhwc(forma):
        x = x.transpose(2, 0, 1)
    return x


# ---------------------------------------------------------------- YuNet ----

class DetectorNPU:
    """O YuNet na NPU, com a mesma saida do cv2.FaceDetectorYN: linhas de 15
    numeros (caixa x,y,w,h; 5 pontos x,y; nota), na escala do quadro.

    A rede tem tamanho FIXO (o .dlc nao muda de tamanho como o ONNX). O quadro
    e reduzido para caber nela e o que sobra embaixo/a direita fica preto,
    exatamente o que o OpenCV faz para arredondar para multiplo de 32."""

    def __init__(self, dlc=None, nota=0.7, nms=0.3, top_k=50):
        import cv2
        self.cv2 = cv2
        self.rede = Rede(dlc or os.path.join(NPU_DIR, "yunet.dlc"))
        f = self.rede.forma()
        self.alt, self.larg = (f[1], f[2]) if _nhwc(f) else (f[2], f[3])
        self.nota, self.nms, self.top_k = nota, nms, top_k

    def detect(self, frame, full_res=False):
        cv2 = self.cv2
        h, w = frame.shape[:2]
        escala = min(self.larg / w, self.alt / h)
        nw, nh = int(round(w * escala)), int(round(h * escala))
        tela = np.zeros((self.alt, self.larg, 3), np.uint8)
        tela[:nh, :nw] = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
        saida = self.rede(entrada=_imagem(self.rede, tela))
        linhas = decodificar_yunet(saida, self.larg, self.alt, self.nota,
                                   self.nms, self.top_k, cv2)
        if len(linhas):
            linhas[:, :14] /= escala
        return linhas


def decodificar_yunet(saida, larg, alt, nota, nms, top_k, cv2):
    """O pos-processamento do YuNet (face_detect.cpp do OpenCV 4.10) em numpy."""
    caixas, pontos, notas = [], [], []
    for passo in (8, 16, 32):
        cols, lins = larg // passo, alt // passo
        cls = _pegar(saida, f"cls_{passo}").reshape(-1)
        obj = _pegar(saida, f"obj_{passo}").reshape(-1)
        bb = _pegar(saida, f"bbox_{passo}").reshape(-1, 4)
        kp = _pegar(saida, f"kps_{passo}").reshape(-1, 10)
        s = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        ok = np.nonzero(s >= nota)[0]
        if not len(ok):
            continue
        c = (ok % cols).astype(np.float32)
        r = (ok // cols).astype(np.float32)
        cx = (c + bb[ok, 0]) * passo
        cy = (r + bb[ok, 1]) * passo
        bw = np.exp(bb[ok, 2]) * passo
        bh = np.exp(bb[ok, 3]) * passo
        caixas.append(np.stack([cx - bw / 2, cy - bh / 2, bw, bh], 1))
        k = kp[ok].reshape(-1, 5, 2)
        k = np.stack([(k[:, :, 0] + c[:, None]) * passo,
                      (k[:, :, 1] + r[:, None]) * passo], 2).reshape(-1, 10)
        pontos.append(k)
        notas.append(s[ok])
        del lins
    if not caixas:
        return np.empty((0, 15), np.float32)
    caixas = np.concatenate(caixas)
    pontos = np.concatenate(pontos)
    notas = np.concatenate(notas)
    fica = cv2.dnn.NMSBoxes(caixas.tolist(), notas.tolist(), nota, nms, top_k=top_k)
    fica = np.asarray(fica, int).reshape(-1)
    return np.concatenate([caixas[fica], pontos[fica], notas[fica, None]],
                          1).astype(np.float32)


# -------------------------------------------------------------- ArcFace ----

class ArcFaceNPU:
    """O ArcFace (w600k_mbf) na NPU. Mesma entrada do aibox/arcface.py: rosto
    alinhado 112x112, (x - 127,5) / 127,5, RGB.

    ATENCAO: 8 bits muda um pouco os numeros. A galeria do ArcFace da CPU so
    vale aqui se aibox/npu_conferir.py mostrar cosseno alto entre os dois
    (>= 0,98); se nao, cadastre de novo com este motor ("arcface-npu")."""

    def __init__(self, dlc=None):
        import cv2
        from aibox.arcface import MOLDE
        self.cv2, self.molde = cv2, MOLDE
        self.rede = Rede(dlc or os.path.join(NPU_DIR, "arcface.dlc"))

    def embedding(self, img, linha):
        cv2 = self.cv2
        p = np.asarray(linha[4:14], np.float32).reshape(5, 2)
        m, _ = cv2.estimateAffinePartial2D(p, self.molde, method=cv2.LMEDS)
        rosto = cv2.warpAffine(img, m, (112, 112), borderValue=0)
        x = (rosto[:, :, ::-1].astype(np.float32) - 127.5) / 127.5
        if not _nhwc(self.rede.forma()):
            x = x.transpose(2, 0, 1)
        out = self.rede(entrada=x)
        return next(iter(out.values())).ravel().astype(np.float32)


# ------------------------------------------------------------ YOLO pose ----

class _Deteccoes:
    """O minimo que o BYTETracker do Ultralytics le de um Results.boxes."""

    def __init__(self, xyxy, conf):
        self.xyxy = xyxy.astype(np.float32)
        self.conf = conf.astype(np.float32)
        self.cls = np.zeros(len(conf), np.float32)
        xy = (self.xyxy[:, :2] + self.xyxy[:, 2:]) / 2
        wh = self.xyxy[:, 2:] - self.xyxy[:, :2]
        self.xywh = np.concatenate([xy, wh], 1)

    def __len__(self):
        return len(self.conf)

    def __getitem__(self, i):
        d = _Deteccoes.__new__(_Deteccoes)
        d.xyxy, d.conf, d.cls, d.xywh = self.xyxy[i], self.conf[i], self.cls[i], self.xywh[i]
        return d


class OlhoNPU:
    """YOLO11-pose na NPU + o MESMO ByteTrack do Ultralytics. A saida e igual
    a do OlhoYolo: [(id, [(x/w, y/h, conf) x 17]), ...]."""

    def __init__(self, dlc=None, conf=None):
        import cv2
        self.cv2 = cv2
        self.rede = Rede(dlc or os.path.join(NPU_DIR, "pose.dlc"))
        f = self.rede.forma()
        self.lado = f[1] if _nhwc(f) else f[2]
        self.conf = float(os.environ.get("CAM_CONF", conf or 0.35))
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import IterableSimpleNamespace, yaml_load
        from ultralytics.utils.checks import check_yaml
        cfg = IterableSimpleNamespace(**yaml_load(check_yaml("bytetrack.yaml")))
        self.trilhas = BYTETracker(cfg, frame_rate=30)

    def ver(self, img):
        cv2 = self.cv2
        h, w = img.shape[:2]
        # letterbox do Ultralytics: cabe no quadrado, centralizado, cinza 114
        e = min(self.lado / w, self.lado / h)
        nw, nh = int(round(w * e)), int(round(h * e))
        dx, dy = (self.lado - nw) // 2, (self.lado - nh) // 2
        tela = np.full((self.lado, self.lado, 3), 114, np.uint8)
        tela[dy:dy + nh, dx:dx + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = tela[:, :, ::-1].astype(np.float32) / 255.0
        if not _nhwc(self.rede.forma()):
            x = x.transpose(2, 0, 1)
        y = next(iter(self.rede(entrada=x).values()))
        y = y.reshape(-1, y.shape[-1]) if y.shape[-1] == 56 else y.reshape(56, -1).T
        boa = y[:, 4] >= self.conf
        y = y[boa]
        if not len(y):
            self.trilhas.update(_Deteccoes(np.zeros((0, 4)), np.zeros(0)), img)
            return []
        cx, cy, bw, bh = y[:, 0], y[:, 1], y[:, 2], y[:, 3]
        xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
        fica = cv2.dnn.NMSBoxes(np.stack([xyxy[:, 0], xyxy[:, 1], bw, bh], 1).tolist(),
                                y[:, 4].tolist(), self.conf, 0.7)
        fica = np.asarray(fica, int).reshape(-1)
        y, xyxy = y[fica], xyxy[fica]
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - dx) / e
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - dy) / e
        kp = y[:, 5:].reshape(-1, 17, 3).copy()
        kp[:, :, 0] = (kp[:, :, 0] - dx) / e / w
        kp[:, :, 1] = (kp[:, :, 1] - dy) / e / h
        rast = self.trilhas.update(_Deteccoes(xyxy, y[:, 4]), img)
        saida = []
        for linha in np.asarray(rast).reshape(-1, 8) if len(rast) else []:
            i = int(linha[7])
            saida.append((int(linha[4]),
                          [(float(a), float(b), float(c)) for a, b, c in kp[i]]))
        return saida

    def fechar(self):
        self.rede.fechar()


def tentar(fabrica, nome):
    """Sobe na NPU ou devolve None (e o chamador fica na CPU). Imprime o
    porque, para a falta da NPU nunca ser silenciosa."""
    if not ligada():
        print(f"[npu] {nome}: NPU=0, fica na CPU", flush=True)
        return None
    try:
        t0 = time.monotonic()
        obj = fabrica()
        rede = getattr(obj, "rede", None)
        onde = "NPU" if rede is not None and rede.na_npu else "CPU (pelo SNPE)"
        print(f"[npu] {nome}: carregado em {time.monotonic() - t0:.1f} s, rodando na {onde}",
              flush=True)
        return obj
    except Exception as e:
        print(f"[npu] {nome}: NAO subiu ({e}). Fica na CPU, como na versao atual.",
              flush=True)
        return None
