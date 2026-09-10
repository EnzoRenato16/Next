#!/usr/bin/env bash
# Baixa o que a camada de objeto suspeito precisa. Rode UMA vez, com internet.
#   bash baixar-modelos.sh
#
# Nada disso vai para o repositorio: sao ~23 MB e o modelo carrega AGPL-3.0.
# Sem estes arquivos a Sala continua funcionando, so nao liga esta camada.
set -euo pipefail
raiz="$(cd "$(dirname "$0")" && pwd)"
ort="$raiz/modelos/ort"
mkdir -p "$ort"

base=https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist

pegar(){   # url destino
  local nome; nome="$(basename "$2")"
  if [ -s "$2" ]; then echo "ja tenho  $nome"; return; fi
  echo "baixando  $nome ..."
  curl -fL --progress-bar -o "$2" "$1"
}

# Qual modelo. "coco" e o padrao e a aposta mais segura para LAMINA: YOLOv8 do
# COCO, treinado em 118 mil imagens revisadas, com desempenho publicado. Nao tem
# classe de arma de fogo.
# "armas" traz pistola E faca, mas e um treino de Colab sem metrica publicada.
# Trocar de um para o outro e so apagar o arquivo e rodar de novo.
qual="${1:-coco}"
case "$qual" in
  coco)  url=https://huggingface.co/unity/inference-engine-yolo/resolve/main/models/yolov8n.onnx ;;
  armas) url=https://huggingface.co/Hadi959/weapon-detection-yolov8/resolve/main/best.onnx ;;
  *) echo "uso: bash baixar-modelos.sh [coco|armas]"; exit 1 ;;
esac
echo "modelo: $qual"
pegar "$url" "$raiz/modelos/objeto_suspeito_yolov8.onnx"
for f in ort.wasm.min.js ort-wasm-simd-threaded.mjs ort-wasm-simd-threaded.wasm; do
  pegar "$base/$f" "$ort/$f"
done
echo
echo "Pronto. Suba o servidor com:  uv run servidor.py"
