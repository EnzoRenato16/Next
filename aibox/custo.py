"""Quanto este processo esta custando: CPU e memoria, sem biblioteca nova.

O professor do desafio disse que medir CPU, RAM, FPS e latencia antes e depois
de ativar o modelo pode fazer parte da avaliacao. No navegador tres desses dao
para medir e CPU nao — pagina nenhuma le isso. Aqui na AIBOX da para medir os
quatro, e e por isso que este arquivo existe.

Le direto de /proc, que e o que o `psutil` faz por baixo. Sem dependencia nova
numa caixa onde instalar pacote e trabalho e cada megabyte conta.
"""
import os
import time

_TICKS = float(os.sysconf("SC_CLK_TCK")) if hasattr(os, "sysconf") else 100.0
_ANTES = None
_ULTIMO = 0.0
# Abaixo disto a leitura nao e refeita: devolve a anterior.
#
# ISTO E CONSERTO DE UM DEFEITO MEDIDO NA AIBOX, e o defeito era sutil. Havia
# DOIS consumidores desta funcao no mesmo laco — a amostra de calibracao e a
# linha de estado — e o primeiro a chamar consumia o intervalo inteiro. O
# segundo pegava um dt de microssegundos, em que o contador do /proc nem tinha
# avancado um tique, e recebia 0,0%. Na tela saiu uma coluna de `cpu 0.0%` com
# um 496% perdido no meio, que e a assinatura exata de dois leitores brigando
# por uma medida que so existe entre duas chamadas.
#
# Com a janela minima, os dois passam a ver O MESMO numero, e ele e verdadeiro.
_MINIMO_S = 0.5


def _tempos():
    """(cpu em segundos, relogio em segundos). None onde nao houver /proc."""
    try:
        with open("/proc/self/stat", "rb") as f:
            campos = f.read().split(b")")[-1].split()
        # utime e stime sao o 12o e o 13o campos depois do ")"
        return (int(campos[11]) + int(campos[12])) / _TICKS, time.monotonic()
    except Exception:
        return None


def cpu_pct():
    """Uso de CPU deste processo desde a chamada anterior, em porcento.

    A PRIMEIRA chamada devolve 0, e isso nao e um bug escondido: nao existe
    "uso de CPU agora", so "uso entre dois instantes". Devolver um numero na
    primeira leitura seria inventar o instante de tras.

    Chamadas seguidas demais devolvem a MEDIDA ANTERIOR em vez de uma nova. Ver
    _MINIMO_S acima para o defeito que isso conserta.

    Pode passar de 100 numa caixa de varios nucleos, e deve mesmo: 180% quer
    dizer quase dois nucleos ocupados. Normalizar por nucleo esconderia
    exatamente o que interessa saber sobre quanto sobra.
    """
    global _ANTES, _ULTIMO
    agora = _tempos()
    if agora is None:
        return 0.0
    if _ANTES is None:
        _ANTES = agora
        return 0.0
    dc, dt = agora[0] - _ANTES[0], agora[1] - _ANTES[1]
    if dt < _MINIMO_S:
        return _ULTIMO          # cedo demais para medir de novo
    _ANTES = agora
    _ULTIMO = round(100.0 * dc / dt, 1)
    return _ULTIMO


def memoria_mb():
    """Memoria residente do processo, em MB. A de verdade, nao a do montinho
    de uma linguagem: conta o modelo carregado, os buffers de video e tudo."""
    try:
        for linha in open("/proc/self/status", encoding="utf-8"):
            if linha.startswith("VmRSS:"):
                return round(int(linha.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return 0.0
