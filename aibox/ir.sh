#!/usr/bin/env bash
# Comecar a trabalhar na AIBOX.   bash aibox/ir.sh [argumentos da sala.py]
#
# POR QUE ISTO EXISTE. Toda sessao nova de SSH perde $P e $PYTHONPATH, e todo
# scp vindo do Windows deixa \r no fim das linhas. Sao duas coisas que ninguem
# lembra e que falham de um jeito que nao parece com a causa: "python: command
# not found" e "$'\r': command not found". As duas ja custaram tempo aqui.
#
# Este script faz as duas, confere se o banco do PC esta alcancavel, e so entao
# roda. Qualquer argumento extra vai direto para a sala.py:
#
#   bash aibox/ir.sh                        roda ate o Ctrl+C
#   bash aibox/ir.sh --segundos 30          para sozinho
#   bash aibox/ir.sh --mostrar --segundos 60
set -u
cd "$(dirname "$0")/.." || exit 1

P=/opt/eduvision/venv/bin/python
export PYTHONPATH="$HOME/pylibs"

echo "=============================================="
echo " Auditix IA na AIBOX"
echo "=============================================="

# ---- o python certo -------------------------------------------------------
if [ ! -x "$P" ]; then
  echo "  !! nao achei $P"
  echo "     este e o venv que ja vem na caixa, com OpenCV, NumPy, Ultralytics"
  echo "     e ONNX Runtime. O python3 do sistema NAO tem nada disso."
  exit 1
fi
echo "  python:  $("$P" -V 2>&1)"

# ---- os \r do Windows -----------------------------------------------------
# Rodar sempre e de graca e evita a pergunta "sera que precisa desta vez?".
sujos=$(grep -rlc $'\r' aibox/*.py aibox/*.sh 2>/dev/null | wc -l)
sed -i 's/\r$//' aibox/*.py aibox/*.sh 2>/dev/null
if [ "$sujos" -gt 0 ]; then
  echo "  limpei o fim de linha do Windows em $sujos arquivo(s)"
fi

# ---- deixar $P valendo nas PROXIMAS sessoes -------------------------------
# Idempotente: so escreve se ainda nao estiver la.
if ! grep -q "AUDITIX" "$HOME/.bashrc" 2>/dev/null; then
  {
    echo ""
    echo "# AUDITIX - o venv da caixa e o lap, que o rastreador exige"
    echo "export P=/opt/eduvision/venv/bin/python"
    echo "export PYTHONPATH=\$HOME/pylibs"
  } >> "$HOME/.bashrc"
  echo "  escrevi \$P e \$PYTHONPATH no ~/.bashrc — a partir da PROXIMA sessao"
  echo "  de ssh eles ja vem prontos."
fi

# ---- o PC esta alcancavel? ------------------------------------------------
echo
"$P" aibox/conferir.py
estado=$?
if [ "$estado" -ne 0 ]; then
  echo
  echo "  !! o caminho ate o banco esta quebrado (veja acima)."
  echo "     A analise ate roda, mas nada do que ela vir vai parar no painel."
  echo
  printf "     rodar assim mesmo? [s/N] "
  read -r resposta
  case "$resposta" in
    s|S|sim|SIM) ;;
    *) exit 1 ;;
  esac
fi

# ---- rodar ----------------------------------------------------------------
echo
echo "=============================================="
echo " imagem ao vivo:  http://192.168.50.10:8080"
echo " (com http:// na frente, senao o Chrome tenta HTTPS e da erro de SSL)"
echo "=============================================="
echo
exec "$P" aibox/sala.py --mostrar "$@"
