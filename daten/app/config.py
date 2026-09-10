"""Configuracao central do EduVision.

Regra do roteiro: NENHUMA senha no codigo-fonte. As credenciais da camera
vem de variaveis de ambiente carregadas de config/camera.env (chmod 600,
fora do git). Aqui so lemos os valores.
"""

import os
from pathlib import Path

# ----- Caminhos do projeto (tudo relativo a ~/eduvision) --------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FACES_DIR = DATA_DIR / "faces"          # subpastas por pessoa: data/faces/enzo/*.jpg
MODELS_DIR = BASE_DIR / "models"
LOGS_DIR = BASE_DIR / "logs"

DB_PATH = DATA_DIR / "eduvision.db"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npz"   # cadastro pronto (gerado pelo enroll)

# ----- Modelos ONNX (OpenCV Zoo — pequenos, rodam em CPU/ARM) ----------------
# Baixe UMA vez antes do laboratorio e coloque em models/ (ver models/README.md).
YUNET_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# ----- Camera (RTSP) --------------------------------------------------------
# Preferimos a variavel CAMERA_RTSP inteira (como no roteiro). Se nao existir,
# montamos a URL a partir das partes (compat com o camera_stream.py de exemplo).
def _build_rtsp_url() -> str:
    url = os.environ.get("CAMERA_RTSP")
    if url:
        return url
    from urllib.parse import quote
    ip = os.environ.get("CAMERA_IP", "192.168.50.108")
    port = os.environ.get("CAMERA_PORT", "554")
    user = os.environ.get("CAMERA_USER", "FIAP")
    pwd = quote(os.environ.get("CAMERA_PASS", ""), safe="")
    subtype = os.environ.get("CAMERA_SUBTYPE", "1")  # 1 = sub-stream (mais leve p/ CPU)
    return (
        f"rtsp://{user}:{pwd}@{ip}:{port}"
        f"/cam/realmonitor?channel=1&subtype={subtype}"
    )

RTSP_URL = _build_rtsp_url()

# Forca RTSP sobre TCP (mais estavel que UDP na rede do lab).
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

ROOM_ID = os.environ.get("ROOM_ID", "SALA_01")
CAMERA_ID = os.environ.get("CAMERA_ID", "CAM_01")
GROUP_ID = os.environ.get("GROUP_ID", "grupo11")

# ----- Largura de deteccao (o maior ganho de FPS no AIBOX) ------------------
# O YuNet roda no frame REDUZIDO; o recorte do rosto continua saindo do frame
# em resolucao cheia, entao a qualidade do embedding nao cai junto com o custo.
#
# Medido neste projeto (frame 1280x720, 4 threads, OpenCV 4.10):
#     1280 -> 36.9 ms     960 -> 20.4 ms     640 -> 8.7 ms     320 -> 3.8 ms
#
# O limite e o TAMANHO DO ROSTO depois de reduzir: abaixo de ~40 px o YuNet
# simplesmente nao acha. Medido com a mesma cara em varios tamanhos:
#     rosto de  67 px no frame cheio -> so aparece a partir de W=960
#     rosto de  90 px                -> so aparece a partir de W=640
#     rosto de 117 px                -> so aparece a partir de W=480
# Numa sala com gente sentada o rosto costuma dar 60-120 px em 720p, por isso o
# padrao aqui e 640 e NAO os 320 do SVATech_Health.md: 320 serve para uma caixa
# de OPME a um metro da camera, nao para uma sala inteira.
#
# Regra pratica para calibrar: rosto_em_pixels * (DETECT_WIDTH / largura_do_frame)
# tem que dar mais de 40. Rode `python -m app.bench` no AIBOX para conferir.
DETECT_WIDTH = int(os.environ.get("DETECT_WIDTH", "640"))

# Tamanho minimo de rosto (em px, ja reduzido) que o YuNet ainda enxerga.
# Usado so para avisar quando DETECT_WIDTH esta agressivo demais.
MIN_FACE_PX = int(os.environ.get("MIN_FACE_PX", "40"))

# ----- Backend de inferencia do SFace ---------------------------------------
# "opencv" (padrao), "ort" (ONNX Runtime) ou "auto".
#
# O guia de reconhecimento facial sugere trocar para ONNX Runtime. Medimos, e
# em x86 o ORT ficou MAIS LENTO que o proprio OpenCV DNN:
#     OpenCV 4.10, 4 threads: OpenCV 11.6 ms/rosto  vs  ORT 18.2 ms/rosto
#     OpenCV 5.00, 4 threads: OpenCV  7.5 ms/rosto  vs  ORT 20.3 ms/rosto
# Em ARM64 pode inverter, e por isso o backend existe e e trocavel sem editar
# codigo. Mas o padrao e o que esta medido: opencv. Antes de mudar, rode
# `python -m app.bench` no AIBOX e decida com numero, nao com suposicao.
SFACE_BACKEND = os.environ.get("SFACE_BACKEND", "opencv").strip().lower()

# Threads do ONNX Runtime. 0 = deixa o ORT escolher.
ORT_THREADS = int(os.environ.get("ORT_THREADS", "0"))

# ----- Objeto suspeito (arma de fogo / arma branca) -------------------------
# YOLOv8 em ONNX, 2 classes: pistol e knife. Baixe o modelo antes; veja
# models/README.md. Sem o arquivo, o resto do sistema roda igual.
ARMAS_MODEL = MODELS_DIR / "objeto_suspeito_yolov8.onnx"

# Liga/desliga. Padrao DESLIGADO de proposito: e a unica camada do projeto que
# pode acusar uma pessoa de portar arma, e ligar isso tem que ser uma decisao
# consciente de quem instala, nao um efeito colateral de atualizar o codigo.
ARMAS_ATIVO = os.environ.get("ARMAS_ATIVO", "0").strip().lower() in ("1", "true", "sim")

ARMAS_LADO = int(os.environ.get("ARMAS_LADO", "640"))    # entrada do YOLOv8

# Limiar ALTO de proposito. Um detector de arma calibrado como detector de gato
# enche a escola de alarme, e alarme que erra sempre e alarme que se aprende a
# ignorar. Prefira deixar passar a acusar errado.
ARMA_CONF = float(os.environ.get("ARMA_CONF", "0.60"))
ARMA_NMS = float(os.environ.get("ARMA_NMS", "0.45"))

# Leituras seguidas antes de virar evento. Sombra e reflexo piscam; objeto fica.
ARMA_HITS = int(os.environ.get("ARMA_HITS", "4"))

# Segundos de silencio depois de alertar sobre a mesma classe, para um objeto
# parado na mesa nao gerar um evento por quadro.
ARMA_SILENCIO = float(os.environ.get("ARMA_SILENCIO", "30"))

# A deteccao e cara: roda 1x a cada N frames processados.
ARMA_CADA = int(os.environ.get("ARMA_CADA", "5"))

# ----- Ponte para a cadeia de hash do Auditix -------------------------------
# Onde o servidor.py esta escutando. Vazio = so grava local (padrao).
# Ex.: export AUDITIX_URL='http://192.168.50.5:8000'
AUDITIX_URL = os.environ.get("AUDITIX_URL", "").strip()
AUDITIX_TIMEOUT = float(os.environ.get("AUDITIX_TIMEOUT", "3"))

# ----- Retencao de biometria (LGPD Art. 14) ---------------------------------
# Biometria de crianca e adolescente nao pode ficar guardada para sempre. Duas
# tranchas independentes, e a que vencer primeiro apaga:
#
#   RETENCAO_DIAS    prazo do consentimento. Vence, apaga, tem que recadastrar
#                    com autorizacao nova. Padrao: 1 ano letivo.
#   INATIVIDADE_DIAS quem nao e visto ha muito tempo saiu da escola. Este e o
#                    unico jeito automatico de cumprir "apagar quando o aluno
#                    sai": ninguem vai lembrar de avisar o sistema.
#
# Apagar aqui significa apagar o EMBEDDING (data/embeddings.npz) e a linha em
# students. A presenca ja registrada continua, sem biometria, porque e registro
# escolar e nao dado biometrico.
RETENCAO_DIAS = int(os.environ.get("RETENCAO_DIAS", "365"))
INATIVIDADE_DIAS = int(os.environ.get("INATIVIDADE_DIAS", "90"))

# ----- Parametros de reconhecimento -----------------------------------------
# SFace usa distancia de cosseno. Acima do limiar = mesma pessoa.
# 0.363 (cosseno) e o valor recomendado pela OpenCV para SFace.
COSINE_THRESHOLD = float(os.environ.get("COSINE_THRESHOLD", "0.363"))

# Presenca so e confirmada apos ver a pessoa em N frames (nao confia em 1 frame).
PRESENCE_MIN_HITS = int(os.environ.get("PRESENCE_MIN_HITS", "5"))

# Roda o detector 1x a cada N frames (frame-skip) para aliviar a CPU do AIBOX.
DETECT_EVERY = int(os.environ.get("DETECT_EVERY", "3"))

# ----- API ------------------------------------------------------------------
API_HOST = os.environ.get("API_HOST", "127.0.0.1")   # rede so na validacao final
API_PORT = int(os.environ.get("API_PORT", "8000"))


def mask_secret(url: str) -> str:
    """Esconde a senha ao logar a URL RTSP."""
    import re
    return re.sub(r":([^:@/]+)@", ":****@", url)
