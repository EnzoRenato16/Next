"""Quem enxerga o corpo. Duas fontes, o MESMO formato de saida: COCO-17.

A escolha de padronizar em COCO-17 nao e estetica. A rede de queda foi treinada
no Fall Vision, que e COCO-17; o YOLO-pose devolve COCO-17; e dos 33 pontos do
MediaPipe a Sala ja usava justamente esses 17. Entao COCO-17 e o formato NATIVO
do modelo, e as duas fontes convergem para ele em vez de cada uma inventar o seu.

    OlhoYolo        -> para a AIBOX. Aceita .pt e tambem .onnx, e com .onnx quem
                       executa e o ONNX Runtime, que e o caminho recomendado
                       para o hardware Qualcomm (Kryo + Adreno). Traz ByteTrack
                       junto, entao a identidade vem de graca.
    OlhoMediaPipe   -> para o PC, com o MESMO arquivo de modelo que o navegador
                       usa. Serve para rodar e depurar o laco inteiro ANTES de
                       ter a caixa na mao, que e a diferenca entre chegar la com
                       codigo testado e chegar com codigo escrito.

As bibliotecas sao importadas DENTRO das classes de proposito: assim o resto do
pacote — medidas, rede, regras, trilhas — continua importavel e testavel numa
maquina que nao tem nem ultralytics nem mediapipe instalados.
"""
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELO_MP = os.path.join(RAIZ, "vendor", "mediapipe", "pose_landmarker_lite.task")


class OlhoYolo:
    """YOLO11-pose pelo Ultralytics, com ByteTrack."""

    def __init__(self, modelo="yolo11n-pose.onnx", conf=0.35, imgsz=640):
        from ultralytics import YOLO          # noqa: PLC0415
        self.m = YOLO(modelo)
        self.conf = conf
        self.imgsz = imgsz

    def ver(self, img):
        # classes=[0] e "so pessoa". Sem isso o rastreador gasta identidade com
        # cadeira e mochila, e o laco de briga passa a comparar pares de movel.
        r = self.m.track(img, persist=True, verbose=False, classes=[0],
                         conf=self.conf, imgsz=self.imgsz)
        if not r:
            return []
        r = r[0]
        k = getattr(r, "keypoints", None)
        if k is None or k.xyn is None:
            return []
        xyn = k.xyn.cpu().numpy()
        cfs = k.conf.cpu().numpy() if k.conf is not None else None
        ids = None
        if r.boxes is not None and r.boxes.id is not None:
            ids = r.boxes.id.cpu().numpy()
        saida = []
        for i in range(len(xyn)):
            c = cfs[i] if cfs is not None else [1.0] * len(xyn[i])
            kp = [(float(xyn[i][j][0]), float(xyn[i][j][1]), float(c[j]))
                  for j in range(len(xyn[i]))]
            saida.append((int(ids[i]) if ids is not None else None, kp))
        return saida

    def fechar(self):
        pass


class OlhoMediaPipe:
    """O mesmo detector do navegador, em Python. Sem identidade propria — quem
    casa as pessoas entre quadros e o Rebanho."""

    def __init__(self, modelo=MODELO_MP, pessoas=4):
        import mediapipe as mp                # noqa: PLC0415
        from mediapipe.tasks.python import vision, BaseOptions  # noqa: PLC0415
        self.mp = mp
        if not os.path.exists(modelo):
            raise FileNotFoundError(f"nao achei o modelo de pose em {modelo}")
        self.det = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=modelo),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=pessoas))
        self.ms = 0

    def ver(self, img):
        import cv2                            # noqa: PLC0415
        from . import medidas                 # noqa: PLC0415
        # O modo VIDEO exige carimbo sempre crescente, igual ao navegador.
        self.ms += 33
        m = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                          data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        r = self.det.detect_for_video(m, self.ms)
        return [(None, medidas.de_mediapipe(lm)) for lm in (r.pose_landmarks or [])]

    def fechar(self):
        """Fechar na mao, e nao deixar para o coletor de lixo.

        Sem isto o MediaPipe tenta se desmontar durante o encerramento do
        interpretador, quando os modulos de que ele precisa ja foram apagados, e
        cospe um traceback de 6 linhas DEPOIS da mensagem de encerramento. Nao
        quebra nada — mas quem esta apresentando ve um erro vermelho na tela na
        hora exata em que acabou de dizer que deu tudo certo."""
        try:
            self.det.close()
        except Exception:
            pass


def abrir(qual=None, modelo=None):
    """Escolhe a fonte. `qual` vem do .env (OLHO=yolo|mediapipe)."""
    qual = (qual or os.environ.get("OLHO", "yolo")).strip().lower()
    if qual in ("yolo", "yolo11", "ultralytics"):
        return OlhoYolo(modelo or os.environ.get("MODELO", "yolo11n-pose.onnx"))
    if qual in ("mediapipe", "mp"):
        return OlhoMediaPipe(modelo or MODELO_MP)
    raise ValueError(f"OLHO desconhecido: {qual!r} (use yolo ou mediapipe)")
