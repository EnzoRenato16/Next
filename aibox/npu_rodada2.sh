#!/bin/bash
# VERSAO NPU, rodada 2. Tudo em ~/auditix-npu/rodada2.txt.
#
#   bash aibox/npu_rodada2.sh                 nao mexe na camera
#   MUDAR_CAMERA=1 bash aibox/npu_rodada2.sh  tambem testa a HAIZ em 1080p/12
#                                             e VOLTA a camera no fim, sempre
#
# ANTES DE RODAR: alguem da galeria em pe a 1-3 m da camera, olhando para ela,
# durante o passo 0 (~30 s). Sem rosto na imagem o ArcFace nao e comparado.
#
# A camera so muda com MUDAR_CAMERA=1, e volta sozinha no fim (trap), mesmo
# com Ctrl+C: calibrar a versao atual com a camera em 1080p e depois ir para a
# prova com ela em 2880x1620 (ou o contrario) e calibrar no escuro. E a camera
# e da organizacao.
cd "$(dirname "$0")/.." || exit 1
sed -i 's/\r$//' aibox/*.sh aibox/*.py 2>/dev/null
P=/opt/eduvision/venv/bin/python
export PYTHONPATH="$HOME/pylibs"

voltar_camera() {
  if [ "${MUDOU:-0}" -eq 1 ]; then
    echo; echo "===== camera de volta como estava ====="
    $P aibox/camera_haiz.py --voltar
    MUDOU=0
  fi
}

rodada() {
  # O trap mora AQUI DENTRO: o lado esquerdo do "| tee" e um subshell, e
  # subshell nao herda trap. EXIT cobre o fim normal e o Ctrl+C (INT -> exit).
  MUDOU=0
  trap voltar_camera EXIT
  trap 'exit 130' INT TERM
  echo "===== 0. NPU: tempo e qualidade contra a CPU, nos mesmos quadros ====="
  echo "(NPU_ESTRITO=1: sem a CPU do SNPE de reserva, para provar que roda na NPU)"
  ( source aibox/npu_env.sh && NPU_ESTRITO=1 $P aibox/npu_teste.py 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -40 )
  echo; echo "===== 1. qtivdec por dentro ====="
  bash aibox/decod_qti.sh
  if [ "${MUDAR_CAMERA:-0}" = "1" ]; then
    echo; echo "===== 2. HAIZ para 1080p a 12/s (volta no fim) ====="
    $P aibox/camera_haiz.py --mudar && MUDOU=1
    sleep 5
    echo; echo "===== 3. decodificacao por software com a camera como ficou ====="
    bash aibox/decod_teste.sh 2>&1 | head -3
  fi
  echo; echo "===== 4. arena NPU, 40 s, conferindo a NPU contra a CPU ====="
  NPU_CONFERIR=1 timeout 70 bash aibox/arena.sh --segundos 40 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -18
}

# O tee ignora o Ctrl+C: se ele morresse junto, o --voltar escreveria num cano
# fechado e morreria antes de devolver a camera.
rodada 2>&1 | ( trap '' INT; tee rodada2.txt )
echo; echo "Salvo em ~/auditix-npu/rodada2.txt"
