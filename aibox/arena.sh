#!/usr/bin/env bash
# O modo arena do NEXT, num comando.   bash aibox/arena.sh [argumentos da arena.py]
#
# A arena da cinco minutos com o setup dentro. Este script e o setup: confere
# o python, os modelos, a galeria e a camera, e ja comeca. Nada de servidor no
# notebook, nada de IP fixo: o notebook so abre a pagina da caixa.
#
#   bash aibox/arena.sh                     roda ate o Ctrl+C (que mostra o resultado)
#   bash aibox/arena.sh --segundos 180      para sozinho em 3 minutos
#   bash aibox/arena.sh --calibrar          imprime a nota de cada leitura
set -u
cd "$(dirname "$0")/.." || exit 1

P=/opt/eduvision/venv/bin/python
export PYTHONPATH="$HOME/pylibs"

echo "=============================================="
echo " Auditix IA, modo arena (identificacao na AIBOX)"
echo "=============================================="

if [ ! -x "$P" ]; then
  echo "  !! nao achei $P (o venv que ja vem na caixa)"
  exit 1
fi
sed -i 's/\r$//' aibox/*.py aibox/*.sh 2>/dev/null

falta=0
for m in daten/models/*.onnx; do [ -f "$m" ] || falta=1; done
if [ "$falta" -eq 1 ] || [ "$(ls daten/models/*.onnx 2>/dev/null | wc -l)" -lt 2 ]; then
  echo "  !! faltam os modelos de rosto em daten/models (no PC: pc modelos)"
  exit 1
fi
echo "  modelos: ok"

"$P" aibox/galeria.py || exit 1
if ! "$P" -c "from aibox import galeria; import sys; sys.exit(0 if galeria.ler()['pessoas'] else 1)" 2>/dev/null; then
  echo "  !! a galeria esta vazia: ninguem para reconhecer"
  exit 1
fi

# A camera vem do .env (CAMERA_ARENA, e CAMERA_ARENA2 se houver a segunda) ou
# de --camera. Sem teste de camera separado aqui de proposito: abrir duas vezes
# seguidas e o que faz a Intelbras bloquear o IP (armadilha 5). A propria
# arena.py diz "sem imagem" na tela se a camera nao responder.
if ! grep -q '^CAMERA_ARENA=' .env 2>/dev/null && [[ " $* " != *" --camera "* ]]; then
  echo "  !! falta CAMERA_ARENA no .env (ou passe --camera rtsp://...)"
  exit 1
fi

ip=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "  No notebook, abra:  http://${ip:-IP_DA_CAIXA}:8080"
echo "  Para encerrar e ver o resultado: Ctrl+C"
echo
exec "$P" aibox/arena.py "$@"
