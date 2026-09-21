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

    Pode passar de 100 numa caixa de varios nucleos, e deve mesmo: 180% quer
    dizer quase dois nucleos ocupados. Normalizar por nucleo esconderia
    exatamente o que interessa saber sobre quanto sobra.
    """
    global _ANTES
    agora = _tempos()
    if agora is None:
        return 0.0
    if _ANTES is None:
        _ANTES = agora
        return 0.0
    dc, dt = agora[0] - _ANTES[0], agora[1] - _ANTES[1]
    _ANTES = agora
    return round(100.0 * dc / dt, 1) if dt > 0 else 0.0


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
