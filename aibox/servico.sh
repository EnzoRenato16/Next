#!/usr/bin/env bash
# O Auditix como servico: sobe sozinho quando a caixa liga.
#
#   bash aibox/servico.sh instalar    liga a partida automatica (e ja inicia)
#   bash aibox/servico.sh estado      esta rodando? desde quando?
#   bash aibox/servico.sh log         as ultimas linhas, ao vivo (Ctrl+C sai)
#   bash aibox/servico.sh parar       para agora (continua instalado)
#   bash aibox/servico.sh iniciar     inicia agora
#   bash aibox/servico.sh remover     desliga a partida automatica e para
#
# COMO SOBE SOZINHO. O usuario grupo11 nao e root, entao nao da para criar um
# servico de sistema (/etc/systemd). O caminho que nao pede senha de ninguem e
# o @reboot do cron do proprio usuario: quando a caixa liga, o cron chama
# `servico.sh rodar`. Se o cron da caixa nao existir, `instalar` diz isso.
#
# O QUE O `rodar` FAZ:
#   - espera a rede (a camera e o PC precisam responder antes);
#   - roda a sala.py SEM o ir.sh: o ir.sh pergunta "rodar assim mesmo?" quando
#     o banco falha, e um servico nao tem ninguem para responder;
#   - se ela cair, sobe de novo, mas ESPERANDO: 60 s, ou 10 min se a camera
#     respondeu 403. Reabrir em laco apertado mantem a Intelbras bloqueando o
#     IP da caixa (CLAUDE.md, armadilha 5);
#   - um so por vez (trava em arquivo): o cron e alguem no ssh nao sobem dois.
#
# Argumentos da sala.py vem de SERVICO_ARGS no .env (ex.: SERVICO_ARGS=--rosto).
set -u
cd "$(dirname "$0")/.." || exit 1
RAIZ=$(pwd)
P=/opt/eduvision/venv/bin/python
LOG="$RAIZ/auditix.log"
TRAVA="$RAIZ/.servico.trava"
PIDF="$RAIZ/.servico.pid"
EU="$RAIZ/aibox/servico.sh"
LINHA="@reboot bash $EU rodar >/dev/null 2>&1"

vivo() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }

case "${1:-}" in
rodar)
  exec 9>"$TRAVA"
  if ! flock -n 9; then echo "ja esta rodando"; exit 0; fi
  echo $$ > "$PIDF"
  export PYTHONPATH="$HOME/pylibs"
  ARGS=$("$P" -c "import os,sys;sys.path.insert(0,'.');from aibox.sala import carregar_env;carregar_env();print(os.environ.get('SERVICO_ARGS',''))" 2>/dev/null)
  SERV=$("$P" -c "import os,sys;sys.path.insert(0,'.');from aibox.sala import carregar_env;carregar_env();print(os.environ.get('SERVIDOR',''))" 2>/dev/null)
  echo "[servico] $(date '+%F %T') subindo. args: ${ARGS:-(nenhum)}" >> "$LOG"
  # A rede demora a acordar depois do boot: ate 2 min esperando o PC responder.
  for _ in $(seq 1 24); do
    "$P" -c "import urllib.request,sys;urllib.request.urlopen(sys.argv[1]+'/api/saude',timeout=3)" "$SERV" 2>/dev/null && break
    sleep 5
  done
  # INT, e nao TERM, para a sala: com INT ela fecha direito e avisa o servidor
  # "parada de proposito" (sem sirene). TERM a mataria sem o aviso, e trinta
  # segundos depois o painel tocaria "sem sinal" por um desligamento normal.
  filho=""
  trap '[ -n "$filho" ] && kill -INT "$filho" 2>/dev/null; wait "$filho" 2>/dev/null; rm -f "$PIDF"; exit 0' TERM INT
  while true; do
    sed -i 's/\r$//' aibox/*.py aibox/*.sh 2>/dev/null
    # shellcheck disable=SC2086
    "$P" aibox/sala.py --mostrar $ARGS >> "$LOG" 2>&1 &
    filho=$!
    wait "$filho"
    cod=$?
    espera=60
    if tail -40 "$LOG" | grep -q "Forbidden (403)"; then espera=600; fi
    echo "[servico] $(date '+%F %T') a sala parou (codigo $cod); de novo em ${espera}s" >> "$LOG"
    # Log que cresce sem fim enche o disco da caixa: guarda so as ultimas linhas.
    tail -5000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    sleep "$espera" &
    filho=$!
    wait "$filho"
  done
  ;;
instalar)
  if ! command -v crontab >/dev/null 2>&1; then
    echo "  !! esta caixa nao tem o cron. Sem ele nao ha partida automatica"
    echo "     para um usuario que nao e root: peca ao professor um servico"
    echo "     de sistema, ou rode  bash aibox/servico.sh iniciar  a cada boot."
    exit 1
  fi
  ( crontab -l 2>/dev/null | grep -v "aibox/servico.sh rodar"; echo "$LINHA" ) | crontab -
  echo "  ok  partida automatica instalada (cron @reboot do usuario $(whoami)):"
  crontab -l | grep "servico.sh" | sed 's/^/        /'
  "$0" iniciar
  ;;
iniciar)
  if vivo; then echo "  ja esta rodando (pid $(cat "$PIDF"))"; exit 0; fi
  setsid nohup bash "$EU" rodar >/dev/null 2>&1 < /dev/null &
  sleep 2
  if vivo; then echo "  ok  rodando em segundo plano (pid $(cat "$PIDF")). Log: bash aibox/servico.sh log"
  else echo "  !! nao subiu. Veja: tail -30 $LOG"; fi
  ;;
parar)
  if vivo; then kill "$(cat "$PIDF")"; sleep 2; echo "  ok  parado"; else echo "  nao estava rodando"; fi
  ;;
remover)
  "$0" parar
  crontab -l 2>/dev/null | grep -v "aibox/servico.sh rodar" | crontab - 2>/dev/null
  echo "  ok  partida automatica removida"
  ;;
estado)
  if crontab -l 2>/dev/null | grep -q "servico.sh rodar"; then
    echo "  partida automatica: LIGADA (cron @reboot)"
  else
    echo "  partida automatica: desligada"
  fi
  if vivo; then
    echo "  agora: RODANDO (pid $(cat "$PIDF"), desde $(ps -o lstart= -p "$(cat "$PIDF")"))"
  else
    echo "  agora: parado"
  fi
  [ -f "$LOG" ] && { echo "  ultimas linhas do log:"; tail -4 "$LOG" | sed 's/^/    /'; }
  ;;
log)
  tail -n 30 -f "$LOG"
  ;;
*)
  sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
  ;;
esac
