"""Deteccao + reconhecimento facial com OpenCV (YuNet + SFace).

Por que YuNet + SFace (OpenCV Zoo) e nao dlib/face_recognition:
  - Sao modelos ONNX pequenos, rodam em CPU/ARM64 (o AIBOX nao tem GPU CUDA).
  - Ja vem suportados pelo opencv-contrib-python (cv2.FaceDetectorYN /
    cv2.FaceRecognizerSF) — nao precisa compilar dlib no Python 3.8 ARM.
  - Nao dependem do modelo YOLO do professor; sao "nossos" e leves.

YuNet detecta o rosto e 5 pontos (olhos, nariz, cantos da boca). SFace usa
esses pontos para alinhar e gerar um embedding de 128 dimensoes. Comparamos
por distancia de cosseno com o cadastro (data/embeddings.npz).

Duas coisas aqui existem por causa de medicao, nao de palpite:

1. A deteccao roda no frame REDUZIDO (config.DETECT_WIDTH) e as coordenadas
   voltam para a escala real antes do recorte. Em 1280x720 isso derrubou o
   YuNet de 36.9 ms para 8.7 ms por frame, e o embedding do mesmo rosto
   continua batendo a 0.91 de cosseno (o limiar de identidade e 0.363).

2. O SFace pode rodar no ONNX Runtime em vez do OpenCV DNN. O padrao continua
   OpenCV porque foi o mais rapido no que deu para medir; veja app/bench.py.
   Ao trocar de backend o embedding TEM que continuar o mesmo, senao o cadastro
   feito num backend nao vale no outro — por isso existe a conferencia de
   paridade em _SFaceORT.
"""

import numpy as np
import cv2

from . import config


class _SFaceORT:
    """SFace no ONNX Runtime, com o mesmo pre-processamento do OpenCV.

    O detalhe que quebra tudo em silencio: o SFace espera **RGB**, nao BGR.
    Alimentado com BGR ele ainda devolve 128 numeros com cara de embedding, e o
    cosseno contra o OpenCV da 0.877 — alto o bastante para passar despercebido
    e baixo o bastante para estragar reconhecimento no limite. O swapRB=True
    abaixo e o que leva a paridade para 1.000000.
    """

    def __init__(self, model_path: str, threads: int = 0):
        import onnxruntime as ort

        # O SFace do Zoo declara os pesos como entradas do grafo, e o ORT avisa
        # sobre isso uma vez por tensor. Sao centenas de linhas que escondem a
        # saida util; 3 = so erro para cima.
        ort.set_default_logger_severity(3)

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if threads > 0:
            opts.intra_op_num_threads = threads
            opts.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(
            model_path, opts, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name

    def feature(self, aligned) -> np.ndarray:
        blob = cv2.dnn.blobFromImage(
            aligned, 1.0, (112, 112), (0, 0, 0), True, False)  # True = swapRB
        return self.sess.run(None, {self.input_name: blob})[0]


class FaceEngine:
    def __init__(self):
        if not config.YUNET_MODEL.exists() or not config.SFACE_MODEL.exists():
            raise FileNotFoundError(
                "Modelos ONNX ausentes em models/. Veja models/README.md "
                "(YuNet + SFace do OpenCV Zoo)."
            )
        # input_size real e definido por frame em detect(), ja na escala reduzida.
        self.detector = cv2.FaceDetectorYN.create(
            str(config.YUNET_MODEL), "", (320, 320),
            score_threshold=0.7, nms_threshold=0.3, top_k=50,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(config.SFACE_MODEL), "")

        self.ort = None
        self.backend = "opencv"
        self._setup_backend()

        # Cadastro: matriz de embeddings + labels alinhados.
        self.known_embeddings = np.empty((0, 128), dtype=np.float32)
        self.known_ids: list = []
        self.known_names: list = []
        self.load_enrollment()

    # ---- Backend do SFace --------------------------------------------------
    def _setup_backend(self) -> None:
        escolha = config.SFACE_BACKEND
        if escolha not in ("ort", "auto"):
            return
        try:
            candidato = _SFaceORT(str(config.SFACE_MODEL), config.ORT_THREADS)
        except ImportError:
            if escolha == "ort":
                print("[AVISO] SFACE_BACKEND=ort mas onnxruntime nao esta "
                      "instalado. Seguindo com OpenCV.")
            return
        except Exception as e:
            print(f"[AVISO] ONNX Runtime nao subiu ({e}). Seguindo com OpenCV.")
            return

        cos = self._conferir_paridade(candidato)
        if cos >= 0.9999:
            self.ort = candidato
            self.backend = "onnxruntime"
            print(f"[OK] SFace no ONNX Runtime (paridade {cos:.6f}).")
        else:
            # Backend que devolve outro embedding invalidaria o cadastro
            # inteiro. Melhor ficar no lento e certo do que no rapido e errado.
            print(f"[AVISO] ONNX Runtime divergiu do OpenCV (cosseno {cos:.6f}, "
                  "esperado 1.000000). Mantendo OpenCV para nao invalidar o "
                  "cadastro.")

    def _conferir_paridade(self, candidato) -> float:
        """Passa a MESMA imagem pelos dois backends e compara o embedding."""
        rng = np.random.default_rng(7)
        amostra = rng.integers(0, 255, (112, 112, 3), dtype=np.uint8)
        a = self.recognizer.feature(amostra).flatten().astype(np.float32)
        b = candidato.feature(amostra).flatten().astype(np.float32)
        a = a / (np.linalg.norm(a) + 1e-9)
        b = b / (np.linalg.norm(b) + 1e-9)
        return float(a @ b)

    # ---- Cadastro ----------------------------------------------------------
    def load_enrollment(self) -> int:
        if config.EMBEDDINGS_PATH.exists():
            data = np.load(config.EMBEDDINGS_PATH, allow_pickle=True)
            self.known_embeddings = data["embeddings"].astype(np.float32)
            self.known_ids = list(data["ids"])
            self.known_names = list(data["names"])
        else:
            self.known_embeddings = np.empty((0, 128), dtype=np.float32)
            self.known_ids, self.known_names = [], []
        return len(self.known_ids)

    # ---- Deteccao ----------------------------------------------------------
    def detect(self, frame, full_res: bool = False):
        """Detecta rostos e devolve as linhas do YuNet na escala do frame.

        `full_res=True` roda na resolucao cheia. E o que o cadastro usa: foto
        parada nao tem pressa, e landmark melhor gera embedding melhor.
        """
        h, w = frame.shape[:2]
        largura = w if full_res else min(config.DETECT_WIDTH, w)

        if largura >= w:
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(frame)
            return faces if faces is not None else np.empty((0, 15), dtype=np.float32)

        escala = largura / w
        menor = cv2.resize(frame, (largura, int(round(h * escala))),
                           interpolation=cv2.INTER_AREA)
        self.detector.setInputSize((menor.shape[1], menor.shape[0]))
        _, faces = self.detector.detect(menor)
        if faces is None:
            return np.empty((0, 15), dtype=np.float32)

        # Colunas 0-13 sao coordenadas (caixa x,y,w,h + 5 pontos x,y); a 14 e o
        # score e nao pode ser mexida. Voltando para a escala real, o alignCrop
        # recorta do frame cheio e o embedding nao perde qualidade.
        faces = faces.copy()
        faces[:, :14] /= escala
        return faces

    def embedding(self, frame, face_row) -> np.ndarray:
        """Alinha o rosto (usando os landmarks da linha do YuNet) e extrai o embedding."""
        aligned = self.recognizer.alignCrop(frame, face_row)
        feat = self.ort.feature(aligned) if self.ort else self.recognizer.feature(aligned)
        return feat.flatten().astype(np.float32)

    # ---- Matching ----------------------------------------------------------
    def identify(self, feat: np.ndarray):
        """Retorna (student_id, name, score) do melhor match, ou (None, 'Desconhecido', score)."""
        if len(self.known_ids) == 0:
            return None, "Desconhecido", 0.0
        # Cosseno: embeddings do SFace nao sao normalizados; normalizamos aqui.
        a = feat / (np.linalg.norm(feat) + 1e-9)
        b = self.known_embeddings / (
            np.linalg.norm(self.known_embeddings, axis=1, keepdims=True) + 1e-9
        )
        scores = b @ a
        idx = int(np.argmax(scores))
        best = float(scores[idx])
        if best >= config.COSINE_THRESHOLD:
            return self.known_ids[idx], self.known_names[idx], best
        return None, "Desconhecido", best
