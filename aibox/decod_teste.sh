#!/bin/bash
# VERSAO NPU: procura um jeito do decodificador de HARDWARE (qtivdec) entregar
# imagem. So le a camera por 15 s em cada tentativa, nao grava nada, nao mexe
# no .env. Depois da NPU, o que sobra de CPU na arena e decodificar a camera.
#
#   bash aibox/decod_teste.sh            (usa CAMERA_ARENA do .env)
#
# Para cada cano: quantos quadros BGR 1280x720 sairam em 15 s e a CPU do gst.
cd "$(dirname "$0")/.." || exit 1
URL=$(grep -E '^CAMERA_ARENA=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')
[ -n "$URL" ] || { echo "sem CAMERA_ARENA no .env"; exit 1; }
QUADRO=$((1280 * 720 * 3))
FONTE="rtspsrc location=$URL protocols=tcp latency=0 ! rtph264depay ! h264parse"
FIM="videoscale ! video/x-raw,format=BGR,width=1280,height=720 ! fdsink"

tentar() {
  nome="$1"; shift
  log=$(mktemp)
  ( timeout 15 gst-launch-1.0 -q $FONTE ! "$@" 2>"$log" | wc -c > "$log.n" ) &
  sleep 12
  cpu=$(ps -u "$USER" -o pcpu=,comm= | grep gst-launch | awk '{s+=$1} END {printf "%.0f", s}')
  wait
  n=$(cat "$log.n"); q=$((n / QUADRO))
  awk -v a="$nome" -v q="$q" -v c="$cpu" 'BEGIN {printf "%-28s %4d quadros em 15 s (%.1f/s)  CPU do gst ~%s%%\n", a, q, q/15, c}'
  [ "$q" -eq 0 ] && head -c 400 "$log" | sed 's/^/      /'
  rm -f "$log" "$log.n"
}

echo "camera: $(echo "$URL" | grep -oE "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" | head -1) (senha escondida)"
tentar "software (avdec_h264)"      avdec_h264 ! videoconvert ! $FIM
tentar "qtivdec NV12 comum"         qtivdec ! video/x-raw,format=NV12 ! videoconvert ! $FIM
tentar "qtivdec sem filtro"         qtivdec ! videoconvert ! $FIM
tentar "qtivdec + qtivtransform"    qtivdec ! qtivtransform ! video/x-raw,format=BGR,width=1280,height=720 ! fdsink
tentar "qtivdec + qtivtransform RGB" qtivdec ! qtivtransform ! video/x-raw,format=RGB,width=1280,height=720 ! videoconvert ! video/x-raw,format=BGR ! fdsink
tentar "qtivdec turbo + transform"  qtivdec turbo=true ! qtivtransform ! video/x-raw,format=BGR,width=1280,height=720 ! fdsink
