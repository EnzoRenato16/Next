#!/bin/bash
# VERSAO NPU: POR QUE o qtivdec da 0 quadros (21/10: 0 em todos os canos,
# com so ~16% de CPU, ou seja, ele nem chega a decodificar). So olha.
#   bash aibox/decod_qti.sh
cd "$(dirname "$0")/.." || exit 1
URL=$(grep -E '^CAMERA_ARENA=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')
esconde() { sed -E 's/(password=)[^&" ]*/\1***/g; s#(rtsp://[^:/]*:)[^@]*@#\1***@#g'; }

echo "== quem pode abrir o decodificador de video (venus / v4l2) =="
id
ls -l /dev/video* /dev/media* /dev/dma_heap 2>&1 | head -20

echo; echo "== decodificadores que o GStreamer conhece =="
gst-inspect-1.0 2>/dev/null | grep -iE "dec|qtic2|v4l2" | grep -iE "h26|qti|v4l2|c2" | head -20

echo; echo "== qtivdec: o que ele aceita e entrega =="
gst-inspect-1.0 qtivdec 2>/dev/null | sed -n '/Pad Templates/,/Element has no clocking/p' | head -40

echo; echo "== 8 s do qtivdec com o log ligado (so avisos e erros) =="
GST_DEBUG=2,qtivdec:5,*c2*:4,*v4l2*:4 timeout 8 gst-launch-1.0 \
  rtspsrc location="$URL" protocols=tcp latency=0 ! rtph264depay ! h264parse ! \
  video/x-h264,stream-format=byte-stream,alignment=au ! qtivdec ! fakesink num-buffers=30 2>&1 |
  esconde | grep -vE "^$" | tail -40

echo; echo "== o mesmo com v4l2h264dec, se existir =="
if gst-inspect-1.0 v4l2h264dec >/dev/null 2>&1; then
  GST_DEBUG=2 timeout 8 gst-launch-1.0 rtspsrc location="$URL" protocols=tcp latency=0 ! \
    rtph264depay ! h264parse ! v4l2h264dec ! fakesink num-buffers=30 2>&1 | esconde | tail -15
else
  echo "nao existe"
fi
