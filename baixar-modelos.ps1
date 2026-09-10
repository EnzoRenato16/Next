# Baixa o que a camada de objeto suspeito precisa. Rode UMA vez, com internet.
#   powershell -ExecutionPolicy Bypass -File baixar-modelos.ps1
#
# Nada disso vai para o repositorio: sao ~23 MB e o modelo carrega AGPL-3.0.
# Sem estes arquivos a Sala continua funcionando, so nao liga esta camada.

param([ValidateSet('coco','armas')][string]$Modelo = 'coco')

# Qual modelo. "coco" e o padrao e a aposta mais segura para LAMINA: YOLOv8 do
# COCO, treinado em 118 mil imagens revisadas, com desempenho publicado. Nao tem
# classe de arma de fogo.
# "armas" traz pistola E faca, mas e um treino de Colab sem metrica publicada.
# Trocar de um para o outro e so apagar o arquivo e rodar de novo.

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$ort  = Join-Path $raiz 'modelos\ort'
New-Item -ItemType Directory -Force -Path $ort | Out-Null

$alvos = @(
  @{ url = $(if ($Modelo -eq 'coco') {
       'https://huggingface.co/unity/inference-engine-yolo/resolve/main/models/yolov8n.onnx'
     } else {
       'https://huggingface.co/Hadi959/weapon-detection-yolov8/resolve/main/best.onnx' })
     dest = Join-Path $raiz 'modelos\objeto_suspeito_yolov8.onnx' },
  @{ url = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort.wasm.min.js'
     dest = Join-Path $ort 'ort.wasm.min.js' },
  @{ url = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort-wasm-simd-threaded.mjs'
     dest = Join-Path $ort 'ort-wasm-simd-threaded.mjs' },
  @{ url = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort-wasm-simd-threaded.wasm'
     dest = Join-Path $ort 'ort-wasm-simd-threaded.wasm' }
)

foreach ($a in $alvos) {
  $nome = Split-Path $a.dest -Leaf
  if (Test-Path $a.dest) { Write-Host "ja tenho  $nome"; continue }
  Write-Host "baixando  $nome ..."
  Invoke-WebRequest -Uri $a.url -OutFile $a.dest
}
Write-Host ''
Write-Host "modelo: $Modelo"
Write-Host 'Pronto. Suba o servidor com:  uv run servidor.py'
