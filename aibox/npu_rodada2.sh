#!/bin/bash
# VERSAO NPU, rodada 2: por que o qtivdec nao entrega imagem, e a HAIZ para
# 1080p/12 pela API "Hikvision" (a porta Xiongmai nao respondeu). Depois,
# a arena NPU por 40 s. Tudo em ~/auditix-npu/rodada2.txt.
cd "$(dirname "$0")/.." || exit 1
sed -i 's/\r$//' aibox/*.sh aibox/*.py 2>/dev/null
P=/opt/eduvision/venv/bin/python
export PYTHONPATH="$HOME/pylibs"
{
  echo "===== 1. qtivdec por dentro ====="
  bash aibox/decod_qti.sh
  echo; echo "===== 2. HAIZ para 1080p a 12/s ====="
  $P aibox/camera_haiz.py --mudar
  sleep 5
  echo; echo "===== 3. decodificacao por software com a camera como ficou ====="
  bash aibox/decod_teste.sh 2>&1 | head -3
  echo; echo "===== 4. arena NPU, 40 s ====="
  timeout 70 bash aibox/arena.sh --segundos 40 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -14
} 2>&1 | tee rodada2.txt
echo; echo "Salvo em ~/auditix-npu/rodada2.txt"
