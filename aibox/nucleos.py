"""Quem roda em qual nucleo. Feito para a QCS6490 da AIBOX, e medido antes.

A QCS6490 tem nucleos de DOIS tamanhos: quatro pequenos (Cortex-A55) e quatro
grandes (Cortex-A78). O ONNX Runtime, sem ninguem dizer nada, divide o modelo
IGUALMENTE entre os oito — e numa divisao igual o trabalho so termina quando o
mais lento termina. Os pequenos viram o gargalo do modelo inteiro.

A divisao que faz sentido neste hardware:

    modelo de pose  ->  nucleos GRANDES   (e o trabalho pesado, ~110 ms)
    decodificar RTSP -> nucleos PEQUENOS  (gst-launch; leve, e cabe neles)

O detalhe que custou pensar: prender o Python com `taskset` no terminal prende
tambem os FILHOS dele, e o gst-launch e filho. A decodificacao iria disputar os
mesmos nucleos grandes com o modelo. Por isso isto e feito por dentro: o Python
se prende nos grandes ANTES de carregar o modelo (as threads do ONNX Runtime
herdam), e o gst-launch nasce solto nos pequenos.

DESLIGADO ATE SER MEDIDO. Liga com NUCLEOS=grandes no .env, e so depois de o
`aibox/medir.py` mostrar que ganha nesta caixa. Palpite sobre desempenho que
ninguem mediu e como os 30 quadros por segundo: bonito no slide.

Nao quebra fora da caixa: sem as frequencias em /sys, ou sem
os.sched_setaffinity (Windows, macOS), tudo aqui vira "nao faz nada".
"""
import glob
import os


RAIZ_CPU = "/sys/devices/system/cpu"


def frequencias(raiz=None):
    """{nucleo: frequencia maxima em kHz}, lida do proprio kernel."""
    saida = {}
    raiz = raiz or RAIZ_CPU
    for f in glob.glob(os.path.join(raiz, "cpu[0-9]*", "cpufreq", "cpuinfo_max_freq")):
        try:
            n = int(os.path.basename(os.path.dirname(os.path.dirname(f)))[3:])
            with open(f) as h:
                saida[n] = int(h.read().strip())
        except (ValueError, OSError, IndexError):
            continue
    return saida


def grupos(raiz=None):
    """(grandes, pequenos). Grandes = acima da menor frequencia da caixa.

    Numa maquina de nucleos todos iguais, nao ha "grandes": devolve ((), ())
    e quem chamar entende que nao ha o que separar."""
    fq = frequencias(raiz)
    if len(set(fq.values())) < 2:
        return (), ()
    menor = min(fq.values())
    grandes = tuple(sorted(n for n, v in fq.items() if v > menor))
    pequenos = tuple(sorted(n for n, v in fq.items() if v == menor))
    return grandes, pequenos


def prender_nos_grandes():
    """Prende ESTE processo (e as threads que ele criar depois) nos grandes.
    Tem que ser chamado ANTES de carregar o modelo. Devolve o que fez, em texto."""
    if not hasattr(os, "sched_setaffinity"):
        return "este sistema nao permite escolher nucleo"
    grandes, pequenos = grupos()
    if not grandes:
        return "nucleos todos iguais (ou frequencias ilegiveis): nada a separar"
    os.sched_setaffinity(0, set(grandes))
    return (f"modelo nos nucleos grandes {list(grandes)}, "
            f"decodificacao nos pequenos {list(pequenos)}")


def soltar_nos_pequenos():
    """Para o preexec_fn do gst-launch: o filho nasce nos nucleos pequenos,
    mesmo com o pai preso nos grandes. Sem separacao, nao faz nada."""
    if not hasattr(os, "sched_setaffinity"):
        return
    _, pequenos = grupos()
    if pequenos and os.environ.get("NUCLEOS", "").strip().lower() == "grandes":
        try:
            os.sched_setaffinity(0, set(pequenos))
        except OSError:
            pass
