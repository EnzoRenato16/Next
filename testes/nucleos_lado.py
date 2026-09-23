"""Nucleos grandes e pequenos — roda pelo testes/nucleos.mjs.

A maquina que roda os testes nao tem nucleos de dois tamanhos. Uma pasta falsa
imita o /sys da QCS6490 da AIBOX: 4 nucleos A55 a 1,96 GHz, 3 A78 a 2,4 GHz e
1 A78 a 2,7 GHz. E contra ela que a separacao e cobrada.
"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from aibox import nucleos  # noqa: E402

falhas = 0


def ok(nome, cond, det=""):
    global falhas
    if cond:
        print(f"  ok   {nome}" + (f"   {det}" if det else ""))
    else:
        falhas += 1
        print(f"  FALHA {nome}   {det}")


def falso_sys(freqs):
    d = tempfile.mkdtemp()
    for n, f in freqs.items():
        os.makedirs(os.path.join(d, f"cpu{n}", "cpufreq"))
        with open(os.path.join(d, f"cpu{n}", "cpufreq", "cpuinfo_max_freq"), "w") as h:
            h.write(f"{f}\n")
    # o /sys de verdade tem pastas cpuidle e cpufreq no mesmo nivel: nao podem
    # ser confundidas com nucleos
    os.makedirs(os.path.join(d, "cpufreq"))
    os.makedirs(os.path.join(d, "cpuidle"))
    return d


qcs6490 = {0: 1958400, 1: 1958400, 2: 1958400, 3: 1958400,
           4: 2400000, 5: 2400000, 6: 2400000, 7: 2707200}
d = falso_sys(qcs6490)
ok("le a frequencia dos 8 nucleos", nucleos.frequencias(d) == qcs6490,
   str(sorted(nucleos.frequencias(d))))
g, p = nucleos.grupos(d)
ok("grandes = os tres A78 e o A78 mais rapido (4 a 7)", g == (4, 5, 6, 7), str(g))
ok("pequenos = os quatro A55 (0 a 3)", p == (0, 1, 2, 3), str(p))

iguais = falso_sys({n: 2000000 for n in range(8)})
ok("numa maquina de nucleos iguais, nao ha o que separar",
   nucleos.grupos(iguais) == ((), ()))
ok("sem /sys legivel (Windows, container), tambem nao",
   nucleos.grupos(tempfile.mkdtemp()) == ((), ()))

# Prender de verdade precisa de pelo menos 2 nucleos nesta maquina. Os grupos
# falsos apontam para nucleos que EXISTEM aqui, para o sched_setaffinity aceitar.
aqui = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
if len(aqui) >= 2:
    original = nucleos.grupos
    nucleos.grupos = lambda raiz=None: ((aqui[-1],), (aqui[0],))
    try:
        txt = nucleos.prender_nos_grandes()
        ok("prender_nos_grandes prende o processo so no grupo grande",
           os.sched_getaffinity(0) == {aqui[-1]}, txt)
        # o filho (gst-launch) nasce nos pequenos, mesmo com o pai preso nos grandes
        import subprocess
        os.environ["NUCLEOS"] = "grandes"
        filho = subprocess.run([sys.executable, "-c",
                                "import os; print(sorted(os.sched_getaffinity(0)))"],
                               capture_output=True, text=True,
                               preexec_fn=nucleos.soltar_nos_pequenos)
        ok("o filho (a decodificacao) nasce nos nucleos PEQUENOS",
           filho.stdout.strip() == str([aqui[0]]), filho.stdout.strip())
        del os.environ["NUCLEOS"]
        filho2 = subprocess.run([sys.executable, "-c",
                                 "import os; print(sorted(os.sched_getaffinity(0)))"],
                                capture_output=True, text=True,
                                preexec_fn=nucleos.soltar_nos_pequenos)
        ok("sem NUCLEOS=grandes, o filho nao e mexido",
           filho2.stdout.strip() != str([aqui[0]]), filho2.stdout.strip())
    finally:
        os.sched_setaffinity(0, set(aqui))
        nucleos.grupos = original
else:
    print("  (so 1 nucleo nesta maquina: o teste de prender de verdade foi pulado)")

print(f"\n{'FALHOU' if falhas else 'a separacao de nucleos passou'}")
sys.exit(1 if falhas else 0)
