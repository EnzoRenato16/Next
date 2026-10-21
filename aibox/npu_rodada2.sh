#!/bin/bash
# VERSAO NPU, rodada 2. Tudo em ~/auditix-npu/rodada2.txt.
#
#   bash aibox/npu_rodada2.sh                 nao mexe na camera
#   MUDAR_CAMERA=1 bash aibox/npu_rodada2.sh  tambem testa a HAIZ em 1080p/12
#                                             e VOLTA a camera no fim, sempre
#
# Se algo der muito errado, a volta na mao:
#   /opt/eduvision/venv/bin/python aibox/camera_haiz.py --voltar
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
URL=$(grep -E '^CAMERA_ARENA=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"'\r')
export PYTHONPATH="$HOME/pylibs"

voltar_camera() {
  if [ "${MUDOU:-0}" -eq 1 ]; then
    MUDOU=0
    # Tudo para um arquivo, e sem morrer por cano fechado: se o SSH caiu, o
    # terminal (e o tee) ja nao existem, e escrever neles mataria o --voltar
    # antes de devolver a camera.
    trap '' PIPE
    { echo; echo "===== camera de volta como estava ($(date +%H:%M:%S)) ====="
      $P aibox/camera_haiz.py --voltar; } >> camera_volta.txt 2>&1
    tail -3 camera_volta.txt 2>/dev/null
  fi
}

rodada() {
  # O trap mora AQUI DENTRO: o lado esquerdo do "| tee" e um subshell, e
  # subshell nao herda trap. EXIT cobre o fim normal; INT (Ctrl+C), TERM e
  # HUP (o SSH caiu) viram exit e passam por ele.
  MUDOU=0
  trap voltar_camera EXIT
  trap 'exit 130' INT TERM HUP
  echo "===== 0. NPU: tempo e qualidade contra a CPU, nos mesmos quadros ====="
  echo "(o que nao couber na NPU nao sobe: 'NAO subiu' = fica no OpenCV)"
  ( source aibox/npu_env.sh && $P aibox/npu_teste.py 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -44 )
  echo; echo "===== 1. qtivdec por dentro ====="
  bash aibox/decod_qti.sh
  if [ "${MUDAR_CAMERA:-0}" = "1" ]; then
    echo; echo "===== 2. HAIZ para 1080p a 12/s (volta no fim) ====="
    # MUDOU antes, e nao depois: um --mudar que muda metade e falha (o DVRIP
    # devolve 1 quando a resolucao nao pega) tambem precisa voltar.
    MUDOU=1
    $P aibox/camera_haiz.py --mudar
    # Camera que troca de resolucao costuma reiniciar o fluxo por 10 a 30 s.
    # Esperar ate ela entregar quadro, senao o passo 3 mede a reconexao.
    echo "esperando a camera voltar..."
    for i in $(seq 1 8); do
      sleep 5
      if timeout 6 gst-launch-1.0 -q rtspsrc location="$URL" protocols=tcp latency=0 ! rtph264depay ! h264parse ! fakesink num-buffers=5 >/dev/null 2>&1; then
        echo "camera respondeu depois de $((i * 5)) s"; break
      fi
    done
    echo; echo "===== 3. decodificacao por software com a camera como ficou ====="
    bash aibox/decod_teste.sh 2>&1 | head -3
  fi
  # Duas passadas: a conferencia mede tambem na CPU e deixa cada quadro mais
  # lento. Na mesma passada, o tempo por quadro nao seria o da NPU.
  echo; echo "===== 4a. arena NPU, 25 s: o TEMPO (sem conferir) ====="
  timeout 55 bash aibox/arena.sh --segundos 25 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -12
  echo; echo "===== 4b. arena NPU, 25 s: a QUALIDADE (NPU contra CPU; mais lento) ====="
  NPU_CONFERIR=1 timeout 55 bash aibox/arena.sh --segundos 25 2>&1 | grep -vE "rpcmem|^ +c1-" | tail -14
}

# O tee ignora o Ctrl+C e a queda do SSH: se ele morresse junto, o resto do
# relatorio se perderia (a volta da camera vai para camera_volta.txt).
rodada 2>&1 | ( trap '' INT HUP; tee rodada2.txt )
echo; echo "Salvo em ~/auditix-npu/rodada2.txt"
