#!/bin/bash
# VERSAO NPU: a rodada de acerto do atraso, num comando so.
#   bash ~/auditix-npu/aibox/npu_rodada.sh
#
# 1. testa os canos de decodificacao (software x qtivdec) com a camera de hoje
# 2. muda a HAIZ para 1920x1080 a 12/s (guarda o antes; desfazer:
#    $P aibox/camera_haiz.py --voltar)
# 3. testa os canos de novo, ja com a camera nova
# 4. roda a arena NPU por 40 s para medir o tempo por quadro
# Tudo vai para ~/auditix-npu/rodada.txt. Nao mexe em ~/auditix.
cd "$(dirname "$0")/.." || exit 1
sed -i 's/\r$//' aibox/*.sh aibox/*.py 2>/dev/null
P=/opt/eduvision/venv/bin/python
export PYTHONPATH="$HOME/pylibs"
{
  echo "===== 1. decodificacao, camera como esta ====="
  bash aibox/decod_teste.sh
  echo; echo "===== 2. HAIZ para 1080p a 12/s ====="
  $P aibox/camera_haiz.py
  $P aibox/camera_haiz.py --mudar
  sleep 5
  echo; echo "===== 3. decodificacao, camera nova ====="
  bash aibox/decod_teste.sh
  echo; echo "===== 4. arena NPU, 40 s ====="
  timeout 70 bash aibox/arena.sh --segundos 40 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -25
} 2>&1 | tee rodada.txt
echo; echo "Salvo em ~/auditix-npu/rodada.txt"
