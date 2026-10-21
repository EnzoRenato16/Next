#!/bin/bash
# Grava o fluxo da camera da arena SEM decodificar: o H.264 vai do RTSP direto
# para um .mp4. Custo de CPU ~zero, resolucao da camera, nada reencodado.
#
#   bash aibox/gravar.sh 300            5 min (o ensaio inteiro)
#   bash aibox/gravar.sh 60 lucas-lado  1 min, com um nome no arquivo
#
# PARA QUE SERVE. Com o ensaio gravado, o limiar, o ARENA_FRENTE e o juntar
# desconhecidos rodam de novo no PC, quantas vezes for preciso, sem a caixa e
# sem ninguem na sala:
#   python aibox\arena.py --camera arena\gravacoes\ARQUIVO.mp4 --como-caixa --calibrar
# No PC e o caminho da CPU: o PC nao tem NPU, e o OpenCV da caixa nao abre
# video. NPU contra CPU so na caixa (npu_rodada2.sh).
# Na caixa, o mesmo arquivo isola o qtivdec da rede:
#   gst-launch-1.0 filesrc location=ARQUIVO.mp4 ! qtdemux ! h264parse ! qtivdec ! fakesink
#
# TEM ROSTO DE GENTE: so com quem concordou, fica em arena/ (fora do Git) e e
# apagado junto com a galeria depois do evento.
#
# UMA conexao com a camera, como todo teste (armadilha 5): nunca com a arena
# ligada. Ctrl+C fecha o arquivo direito (o -e manda fim de fluxo). E se o SSH
# cair no meio, o .mp4 vai em pedacos de 1 s (fragment-duration): o que foi
# gravado ate ali ainda abre.
cd "$(dirname "$0")/.." || exit 1
S=${1:-60}
NOME=${2:-ensaio}
URL=$(grep -E '^CAMERA_ARENA=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')
[ -n "$URL" ] || { echo "sem CAMERA_ARENA no .env"; exit 1; }
CODEC=$(grep -E '^CAM_CODEC=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r' | tr A-Z a-z)
if [ "$CODEC" = "h265" ] || [ "$CODEC" = "hevc" ]; then
  DEPAY="rtph265depay ! h265parse"
else
  DEPAY="rtph264depay ! h264parse"
fi
# Usuario e senha: os do proprio endereco (HAIZ, password=...) ou, se nao
# houver, CAM_USER/CAM_PW do .env (Intelbras), como o gstcam faz.
CRED=()
if [[ "$URL" != *"password="* && "$URL" != rtsp://*@* ]]; then
  U=$(grep -E '^CAM_USER=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')
  W=$(grep -E '^CAM_PW=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')
  CRED=("user-id=$U" "user-pw=$W")
fi
mkdir -p arena/gravacoes
# A caixa e de todos os grupos e o video tem rosto: a pasta e so do grupo11.
chmod 700 arena arena/gravacoes 2>/dev/null
ARQ="arena/gravacoes/$(date +%Y%m%d-%H%M%S)-$NOME.mp4"
echo "gravando ${S} s em $ARQ (Ctrl+C para antes)"
# --foreground: sem ele o timeout tira o gst do alcance do Ctrl+C, e a
# gravacao so parava no fim do tempo.
timeout --foreground -s INT "$S" gst-launch-1.0 -e -q rtspsrc location="$URL" "${CRED[@]}" protocols=tcp latency=200 ! \
  $DEPAY ! mp4mux fragment-duration=1000 ! filesink location="$ARQ"
ls -la "$ARQ" 2>/dev/null && echo "pronto. No PC: scp grupo11@IP_DA_CAIXA:$(pwd)/$ARQ ."
echo "replay no PC: python aibox\\arena.py --camera ARQUIVO.mp4 --como-caixa --calibrar"
