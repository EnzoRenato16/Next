#!/usr/bin/env bash
# Mostrar, sozinho, o caminho AIBOX -> camera IP -> stream.
#
#   bash aibox/camera_teste.sh            a camera da sala (CAMERA_RTSP)
#   bash aibox/camera_teste.sh cadastro   a camera de cadastro (CAMERA_CADASTRO)
#
# POR QUE ISTO EXISTE. A sala.py faz isso o tempo todo, mas misturado com
# modelo, rede e painel. Para a banca, "a caixa abre o RTSP da camera e recebe
# video" precisa ser visto em 5 segundos, sem mais nada em volta.
#
# Usa o MESMO cano da sala.py (gstcam: rtspsrc por TCP, h264, BGR 640x360) e o
# login do .env, lido pelo mesmo carregar_env. A senha nao aparece na tela.
#
# UMA tentativa so, e nao em laco: a Intelbras bloqueia o IP da caixa (403)
# depois de varias tentativas seguidas. Ver CLAUDE.md, armadilha 5.
set -u
cd "$(dirname "$0")/.." || exit 1
P=/opt/eduvision/venv/bin/python
export PYTHONPATH="$HOME/pylibs"
SEG=5

qual=CAMERA_RTSP
[ "${1:-}" = "cadastro" ] && qual=CAMERA_CADASTRO

ler() {
  "$P" -c "import os,sys;sys.path.insert(0,'.');from aibox.sala import carregar_env;carregar_env();print(os.environ.get('$1',''))"
}
URL=$(ler "$qual")
U=$(ler CAM_USER)
W=$(ler CAM_PW)
if [ -z "$URL" ]; then
  echo "  !! $qual nao esta no .env da caixa"
  exit 1
fi

echo "=============================================="
echo " AIBOX -> camera IP -> stream"
echo "=============================================="
echo "  caixa:   $(hostname)  ($(hostname -I 2>/dev/null | awk '{print $1}'))"
echo "  camera:  $URL"
echo "  usuario: $U   (senha lida do .env, nao exibida)"
echo "  cano:    rtspsrc (TCP) ! rtph264depay ! h264parse ! avdec_h264 ! BGR 640x360"
echo "  lendo $SEG segundos de video..."
echo

ERR=$(mktemp)
BYTES=$(timeout "$SEG" gst-launch-1.0 -q rtspsrc location="$URL" user-id="$U" user-pw="$W" \
          protocols=tcp latency=100 ! rtph264depay ! h264parse ! avdec_h264 \
          ! videoconvert ! videoscale ! video/x-raw,format=BGR,width=640,height=360 \
          ! fdsink 2>"$ERR" | wc -c)
QUADRO=$((640 * 360 * 3))
N=$((BYTES / QUADRO))

if [ "$N" -gt 0 ]; then
  echo "  ok  recebidos $N quadros em ${SEG}s  (~$((N / SEG)) por segundo, $BYTES bytes)"
  echo "      a caixa abriu o RTSP da camera e decodificou o video."
  rm -f "$ERR"
  exit 0
fi
echo "  !! nenhum quadro chegou."
if grep -q "403" "$ERR"; then
  echo "     403 Forbidden: a camera BLOQUEOU o IP da caixa por tentativas seguidas."
  echo "     Nao tente de novo agora: espere uns 30 minutos."
elif grep -q "401" "$ERR"; then
  echo "     401: login recusado, ou caminho errado (/cam/realmonitor?channel=1&subtype=1)."
else
  echo "     mensagem do GStreamer:"
  tail -5 "$ERR" | sed 's/^/       /'
fi
rm -f "$ERR"
exit 1
