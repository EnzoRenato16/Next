"""Liga a decodificacao de video por HARDWARE (qtivdec), se ela funcionar aqui.

    $P aibox/acelerar.py              testa uma vez e, se der imagem, liga no .env
    $P aibox/acelerar.py --desfazer   volta para a decodificacao na CPU

POR QUE EXISTE. O maior peso da caixa nao e o rosto nem o corpo: e decodificar
o video da camera na CPU (744% de 800% medidos na sala). A caixa tem um
decodificador de video proprio, o qtivdec, que tira esse trabalho da CPU e
deixa ela para os nossos modelos. Em 20/10 ele deu "sem imagem"; o gstcam
passou a pedir NV12 em memoria comum (21/10), e falta so este teste.

O TESTE E UMA CONEXAO SO, de proposito: a Intelbras bloqueia o IP da caixa
depois de tentativas seguidas (armadilha 5 do CLAUDE.md). Se der certo, grava
GST_DECODIFICADOR=qtivdec no .env e a arena e a sala passam a usar. Se nao,
nao muda nada. Rode com a arena e a sala PARADAS (a camera ja estaria em uso).

O teste ve se chegaram quadros e se eles nao sao lisos (preto, cinza). Imagem
embaralhada ele nao enxerga: confira na pagina da arena, e se estiver
estranha, --desfazer.
"""
import argparse
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

ENV = os.path.join(RAIZ, ".env")
CHAVE = "GST_DECODIFICADOR"
SEGUNDOS = 20.0
MINIMO_QUADROS = 10


def gravar_env(valor):
    """Tira a linha antiga e poe a nova no fim. Apagar-e-acrescentar, e nao
    `sed s///`: a URL da camera tem `&`, e o sed ja embaralhou o .env assim
    (armadilha 4). valor None so apaga."""
    linhas = []
    if os.path.exists(ENV):
        with open(ENV, encoding="utf-8") as f:
            linhas = [x for x in f.read().splitlines()
                      if not x.strip().startswith(CHAVE + "=")]
    if valor is not None:
        linhas.append(f"{CHAVE}={valor}")
    with open(ENV, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")


def cpu_do_filho(pid):
    """Segundos de CPU do gst-launch ate agora (de /proc, sem dependencia)."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            campos = f.read().split(b")")[-1].split()
        return (int(campos[11]) + int(campos[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def testar(url):
    # ANTES do import: o gstcam le o decodificador quando e importado.
    os.environ[CHAVE] = "qtivdec"
    import numpy as np
    from aibox.gstcam import Gst, sem_senha
    print(f"[acelerar] testando o qtivdec em {sem_senha(url)} por {SEGUNDOS:.0f} s")
    cap = Gst(url, 640, 360, fps=6, bordas=True)
    inicio, quadros, lisos = time.monotonic(), 0, 0
    try:
        while time.monotonic() - inicio < SEGUNDOS and cap.isOpened():
            ok, q = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            quadros += 1
            if float(np.std(q)) < 3.0:
                lisos += 1
        cpu = cpu_do_filho(cap.p.pid)
    finally:
        cap.release()
    dur = time.monotonic() - inicio
    pct = f"{100 * cpu / dur:.0f}%" if cpu is not None else "?"
    print(f"[acelerar] {quadros} quadros em {dur:.0f} s, {lisos} lisos, "
          f"decodificacao usando {pct} de CPU")
    return quadros >= MINIMO_QUADROS and lisos <= quadros // 2


def main():
    from aibox.sala import carregar_env
    carregar_env()
    p = argparse.ArgumentParser(description="liga o qtivdec se ele funcionar")
    p.add_argument("--camera", default=os.environ.get("CAMERA_ARENA")
                   or os.environ.get("CAMERA_RTSP"))
    p.add_argument("--desfazer", action="store_true",
                   help="volta para a decodificacao na CPU")
    a = p.parse_args()

    if a.desfazer:
        gravar_env(None)
        print("[acelerar] pronto: o video volta a ser decodificado na CPU")
        return 0
    if not a.camera or not str(a.camera).startswith("rtsp"):
        print("[acelerar] falta a camera: CAMERA_ARENA no .env ou --camera rtsp://...")
        return 2
    if testar(a.camera):
        gravar_env("qtivdec")
        print("[acelerar] FUNCIONOU: GST_DECODIFICADOR=qtivdec gravado no .env.\n"
              "           Rode a arena e confira se a imagem da pagina esta normal.\n"
              "           Se estiver estranha:  $P aibox/acelerar.py --desfazer")
        return 0
    print("[acelerar] nao funcionou nesta caixa: nada mudou, segue na CPU.\n"
          "           Se o terminal mostrou 403, a camera bloqueou o IP:\n"
          "           espere uns 30 min antes de rodar a arena.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
