"""Deteccao de objeto suspeito (arma de fogo e arma branca) — YOLOv8 em ONNX.

O NOME IMPORTA, e nao e preciosismo. Isto nao e um "detector de armas": e um
detector de OBJETO SUSPEITO, que pede conferencia humana. A diferenca aparece
no evento gravado, no painel e na tela, e existe porque a literatura de campo e
dura com esta tecnologia:

  - sistemas em producao ja confundiram uma clarineta e um saco de salgadinho
    com arma de fogo;
  - em 2023, num colegio no Texas, a SOMBRA DO BRACO de um aluno disparou o
    alarme e a escola entrou em lockdown;
  - a FTC processou um fornecedor em 2024 por alegar deteccao que o produto nao
    entregava.

Faca e o caso que funciona PIOR, e e justamente o mais pedido numa escola.
Entao aqui a postura e a mesma do resto do projeto: alerta nao e acusacao.
O sistema levanta a mao; quem decide e uma pessoa.

Duas travas contra falso positivo, e as duas custam pouco:

1. LIMIAR ALTO por padrao (ARMA_CONF). Um detector de arma calibrado como
   detector de gato enche a escola de alarme.
2. PERSISTENCIA (ARMA_HITS). O objeto tem que aparecer em varias leituras
   seguidas antes de virar evento. Reflexo de luz e sombra piscam; um objeto
   de verdade fica. E a mesma ideia do PRESENCE_MIN_HITS do reconhecimento.

Sobre o modelo: e um YOLOv8 exportado para ONNX, com duas classes (pistol,
knife). A saida vem CRUA, sem NMS embutida, entao a decodificacao e a supressao
estao aqui, escritas a mao — de proposito, para nao arrastar a dependencia do
Ultralytics (AGPL) para dentro do projeto so para ler um tensor.
"""

import numpy as np
import cv2

from . import config

# O que o modelo devolve, na ordem dos indices de classe.
CLASSES = ("pistol", "knife")

# Como isso aparece para uma pessoa. Nunca "arma detectada".
ROTULO = {"pistol": "objeto tipo arma de fogo", "knife": "objeto tipo lamina"}


class DetectorArmas:
    """YOLOv8 ONNX, com pre e pos-processamento proprios."""

    def __init__(self):
        if not config.ARMAS_MODEL.exists():
            raise FileNotFoundError(
                f"Modelo de objeto suspeito ausente em {config.ARMAS_MODEL}. "
                "Veja models/README.md."
            )
        self.backend = "opencv"
        self.sess = None
        self.entrada = None
        try:
            import onnxruntime as ort

            ort.set_default_logger_severity(3)
            opts = ort.SessionOptions()
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            if config.ORT_THREADS > 0:
                opts.intra_op_num_threads = config.ORT_THREADS
            self.sess = ort.InferenceSession(
                str(config.ARMAS_MODEL), opts, providers=["CPUExecutionProvider"])
            self.entrada = self.sess.get_inputs()[0].name
            self.backend = "onnxruntime"
        except ImportError:
            # Sem onnxruntime, o proprio OpenCV le o ONNX. Mais lento, mas o
            # sistema nao deixa de funcionar por causa de um pacote a menos.
            self.rede = cv2.dnn.readNetFromONNX(str(config.ARMAS_MODEL))

        self.lado = config.ARMAS_LADO

    # ---- pre-processamento -------------------------------------------------
    def _encaixar(self, frame):
        """Letterbox: encolhe mantendo a proporcao e preenche o resto de cinza.

        Esticar a imagem para o quadrado deformaria o objeto, e um cano de arma
        achatado deixa de parecer um cano de arma. Devolve tambem a escala e o
        deslocamento, para as caixas voltarem ao frame original depois.
        """
        h, w = frame.shape[:2]
        escala = min(self.lado / w, self.lado / h)
        nw, nh = int(round(w * escala)), int(round(h * escala))
        redim = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)

        tela = np.full((self.lado, self.lado, 3), 114, dtype=np.uint8)
        dx, dy = (self.lado - nw) // 2, (self.lado - nh) // 2
        tela[dy:dy + nh, dx:dx + nw] = redim
        return tela, escala, dx, dy

    # ---- pos-processamento -------------------------------------------------
    @staticmethod
    def _nms(caixas, scores, limiar):
        """Supressao de nao-maximos. Sem isto, um objeto vira cinco alertas."""
        if len(caixas) == 0:
            return []
        x1 = caixas[:, 0]; y1 = caixas[:, 1]
        x2 = caixas[:, 0] + caixas[:, 2]; y2 = caixas[:, 1] + caixas[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        ordem = scores.argsort()[::-1]

        ficam = []
        while ordem.size > 0:
            i = ordem[0]
            ficam.append(int(i))
            if ordem.size == 1:
                break
            xx1 = np.maximum(x1[i], x1[ordem[1:]])
            yy1 = np.maximum(y1[i], y1[ordem[1:]])
            xx2 = np.minimum(x2[i], x2[ordem[1:]])
            yy2 = np.minimum(y2[i], y2[ordem[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[ordem[1:]] - inter + 1e-9)
            ordem = ordem[1:][iou <= limiar]
        return ficam

    def detectar(self, frame) -> list:
        """Devolve [{classe, rotulo, conf, box:(x,y,w,h)}] na escala do frame."""
        tela, escala, dx, dy = self._encaixar(frame)
        # YOLOv8 espera RGB normalizado em 0..1, NCHW.
        blob = cv2.dnn.blobFromImage(tela, 1 / 255.0, (self.lado, self.lado),
                                     (0, 0, 0), swapRB=True, crop=False)

        if self.sess is not None:
            saida = self.sess.run(None, {self.entrada: blob})[0]
        else:
            self.rede.setInput(blob)
            saida = self.rede.forward()

        # (1, 4+nc, 8400) -> (8400, 4+nc). O 4 e cx,cy,w,h na escala 640.
        pred = np.squeeze(saida, 0).T
        if pred.shape[1] < 5:
            return []
        classes_pred = pred[:, 4:]
        melhor = classes_pred.argmax(axis=1)
        conf = classes_pred.max(axis=1)

        vale = conf >= config.ARMA_CONF
        if not vale.any():
            return []
        pred, melhor, conf = pred[vale], melhor[vale], conf[vale]

        cx, cy, w, h = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
        # Desfaz o letterbox: tira o deslocamento, depois desfaz a escala.
        x = (cx - w / 2 - dx) / escala
        y = (cy - h / 2 - dy) / escala
        caixas = np.stack([x, y, w / escala, h / escala], axis=1)

        achados = []
        for i in self._nms(caixas, conf, config.ARMA_NMS):
            nome = CLASSES[int(melhor[i])] if int(melhor[i]) < len(CLASSES) else "?"
            bx, by, bw, bh = caixas[i]
            achados.append({
                "classe": nome,
                "rotulo": ROTULO.get(nome, nome),
                "conf": round(float(conf[i]), 3),
                "box": (int(bx), int(by), int(bw), int(bh)),
            })
        return achados


class Confirmador:
    """Exige o objeto em varias leituras seguidas antes de virar evento.

    E a trava que separa "reflexo piscou" de "tem alguma coisa ali". Sombra e
    brilho aparecem num quadro e somem no seguinte; um objeto de verdade
    persiste. Sem isto, o alerta de arma vira ruido e a escola aprende a
    ignorar — que e o pior desfecho possivel para um alerta de seguranca.
    """

    def __init__(self):
        self._seguidas = {}     # classe -> leituras seguidas
        self._avisado = {}      # classe -> quando ja alertamos (segundos)

    def passo(self, achados: list, agora: float) -> list:
        """Devolve so o que ACABOU de cruzar o limiar de persistencia."""
        vistos = {a["classe"] for a in achados}
        novos = []

        for classe in vistos:
            self._seguidas[classe] = self._seguidas.get(classe, 0) + 1
            if self._seguidas[classe] != config.ARMA_HITS:
                continue
            # Um objeto parado na mesa nao pode alertar a cada frame.
            if agora - self._avisado.get(classe, -1e9) < config.ARMA_SILENCIO:
                continue
            self._avisado[classe] = agora
            melhor = max((a for a in achados if a["classe"] == classe),
                         key=lambda a: a["conf"])
            novos.append(melhor)

        # Some do quadro, o contador desce em vez de zerar: uma leitura ruim no
        # meio de uma sequencia boa nao apaga a evidencia acumulada.
        for classe in list(self._seguidas):
            if classe not in vistos:
                self._seguidas[classe] = max(0, self._seguidas[classe] - 1)
        return novos
