#!/usr/bin/env bash
# Preparar a AIBOX para rodar o Auditix IA.  bash aibox/instalar.sh
#
# NAO INSTALA NADA SEM PRECISAR. Primeiro olha o que ja existe: o professor do
# desafio disse que a caixa ja vem com OpenCV, ONNX Runtime, Ultralytics e NumPy
# num venv. Se estiver tudo la, este script so confere e escreve o .env.
#
# E DIZ O QUE FALTA EM VOZ ALTA, com o comando de conserto do lado. Script de
# instalacao que falha calado e o jeito mais rapido de perder uma tarde.
set -u
cd "$(dirname "$0")/.." || exit 1
RAIZ="$PWD"
PY="${PY:-python3}"

echo "=============================================="
echo " Auditix IA na AIBOX"
echo "=============================================="
echo
echo "-- maquina --"
echo "  nucleos: $(nproc)"
free -m 2>/dev/null | awk '/Mem:/{print "  memoria: "$2" MB total, "$7" MB livres"}'
echo "  disco:   $(df -h "$RAIZ" | tail -1 | awk '{print $4" livres de "$2}')"
echo "  kernel:  $(uname -srm)"
echo
echo "-- python --"
"$PY" -V 2>&1 | sed 's/^/  /'

falta=""
ver() {
  if "$PY" -c "import $1" 2>/dev/null; then
    printf '  %-14s ok   %s\n' "$1" "$("$PY" -c "import $1;print(getattr($1,'__version__',''))" 2>/dev/null)"
  else
    printf '  %-14s FALTA\n' "$1"
    falta="$falta $2"
  fi
}
echo
echo "-- o que o Auditix precisa --"
ver numpy numpy
ver cv2 opencv-python-headless
ver requests requests

echo
echo "-- quem enxerga o corpo (basta UM) --"
olho=""
if "$PY" -c "import ultralytics" 2>/dev/null; then
  echo "  ultralytics    ok   -> OLHO=yolo"; olho=yolo
elif "$PY" -c "import mediapipe" 2>/dev/null; then
  echo "  mediapipe      ok   -> OLHO=mediapipe"; olho=mediapipe
else
  echo "  ultralytics    FALTA"
  echo "  mediapipe      FALTA"
  falta="$falta ultralytics"
fi
"$PY" -c "import onnxruntime as o;print('  onnxruntime    ok  ',o.get_available_providers())" 2>/dev/null \
  || echo "  onnxruntime    FALTA (so importa se for usar modelo .onnx)"

echo
if [ -n "$falta" ]; then
  echo "!! FALTAM PACOTES:$falta"
  echo
  echo "   com internet na caixa:"
  echo "       $PY -m pip install --user$falta"
  echo
  echo "   sem internet: baixe no PC e copie para ca. No PC (com internet):"
  echo "       pip download --only-binary=:all: --platform manylinux2014_aarch64 \\"
  echo "            --python-version 3.8 -d rodas$falta"
  echo "       scp -r rodas grupo11@<ip-da-caixa>:~/"
  echo "   e aqui:"
  echo "       $PY -m pip install --user --no-index --find-links ~/rodas$falta"
  echo
else
  echo ">> nao falta nada. a caixa ja tem tudo."
fi

if [ ! -f "$RAIZ/.env" ]; then
  cat > "$RAIZ/.env" <<'ENV'
# A SENHA DA CAMERA MORA AQUI E EM MAIS LUGAR NENHUM.
# Este arquivo nao vai para o git — e para isso que ele existe.
CAMERA_RTSP=rtsp://USUARIO:SENHA@192.168.50.108:554/stream2
SERVIDOR=http://192.168.50.72:8000
LOCAL_CAMERA=sala-12
OLHO=AQUI_O_OLHO
MODELO=yolo11n-pose.pt
CALIBRACAO=1
ENV
  [ -n "$olho" ] && sed -i "s/AQUI_O_OLHO/$olho/" "$RAIZ/.env"
  chmod 600 "$RAIZ/.env"
  echo
  echo ">> criei o .env. FALTA VOCE POR usuario, senha e o IP certo da camera:"
  echo "       nano $RAIZ/.env"
else
  echo
  echo ">> o .env ja existe, nao mexi nele."
fi

echo
echo "-- alcance da rede --"
ip_de() { echo "$1" | sed -E 's#.*@##; s#[:/].*##'; }
cam=$(grep -E '^CAMERA_RTSP=' "$RAIZ/.env" 2>/dev/null | cut -d= -f2-)
srv=$(grep -E '^SERVIDOR=' "$RAIZ/.env" 2>/dev/null | sed -E 's#.*//##; s#/.*##')
if [ -n "$cam" ]; then
  h=$(ip_de "$cam")
  timeout 4 bash -c "</dev/tcp/$h/554" 2>/dev/null \
    && echo "  camera  $h:554   responde" \
    || echo "  camera  $h:554   NAO responde (ip errado, cabo, ou camera desligada)"
fi
if [ -n "$srv" ]; then
  timeout 4 bash -c "</dev/tcp/${srv%:*}/${srv##*:}" 2>/dev/null \
    && echo "  servidor $srv   responde" \
    || echo "  servidor $srv   NAO responde (suba com HOST=0.0.0.0 no PC)"
fi

echo
echo "=============================================="
echo " proximo passo:"
echo "   nano .env                     (usuario e senha da camera)"
echo "   $PY aibox/sala.py --mostrar --segundos 30"
echo "=============================================="
