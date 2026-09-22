"""Cadastrar um rosto pela camera da AIBOX.

  $P aibox/cadastrar.py --nome "Enzo Renato"

POR QUE EXISTE UM CADASTRO SEPARADO. O cadastro do navegador (/cadastro) mede o
rosto com o face-api.js; a caixa mede com o SFace. Os dois devolvem 128 numeros
e NAO SAO COMPARAVEIS — misturar nao estoura nada, so faz o reconhecimento
virar sorteio. Por isso cada cadastro carrega o tipo, e a mesma pessoa pode (e
deve) estar cadastrada nos dois: um vale na tela do PC, o outro na caixa.

O QUE ELE FAZ: abre a camera, espera aparecer UM rosto, colhe algumas amostras
espacadas no tempo e manda os 128 numeros para o servidor. A imagem nao e
gravada em lugar nenhum — nem em disco, nem no banco.

AS AMOSTRAS SAO ESPACADAS DE PROPOSITO. Seis fotos do mesmo instante sao a mesma
foto seis vezes: nao ensinam nada sobre o rosto de lado, de cabeca baixa ou com
outra luz. O intervalo existe para dar tempo de a pessoa mexer a cabeca — e o
programa pede isso em voz alta.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from aibox.sala import abrir_camera, carregar_env  # noqa: E402


def mandar(base, nome, vetores):
    corpo = json.dumps({"nome": nome, "tipo": "sface",
                        "descritores": vetores}).encode("utf-8")
    pedido = urllib.request.Request(
        base.rstrip("/") + "/api/cadastro", data=corpo,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"erro": f"{e.code} {e.read().decode('utf-8', 'replace')[:200]}"}
    except Exception as e:
        return {"erro": str(e)}


def main():
    carregar_env()
    p = argparse.ArgumentParser(description="Cadastrar um rosto pela camera da AIBOX")
    p.add_argument("--nome", required=True)
    p.add_argument("--camera", default=os.environ.get("CAMERA_RTSP"))
    p.add_argument("--servidor",
                   default=os.environ.get("SERVIDOR", "http://127.0.0.1:8000"))
    p.add_argument("--amostras", type=int, default=6)
    p.add_argument("--intervalo", type=float, default=1.5,
                   help="segundos entre uma amostra e a seguinte")
    a = p.parse_args()

    from daten.app.recognizer import FaceEngine
    motor = FaceEngine()
    print(f"[cadastro] motor: {motor.backend}")

    fonte = int(a.camera) if str(a.camera).isdigit() else a.camera
    cap = abrir_camera(fonte)
    if not cap.isOpened():
        print("[cadastro] nao consegui abrir a camera.")
        return 3

    print(f"\n  Cadastrando: {a.nome}")
    print(f"  Vou colher {a.amostras} amostras, uma a cada {a.intervalo:.1f}s.")
    print("  MEXA A CABECA DEVAGAR entre uma e outra: um pouco para cada lado,")
    print("  um pouco para baixo. Rosto sempre de frente da um cadastro que so")
    print("  reconhece de frente.\n")

    vetores, proxima, comecou = [], 0.0, time.monotonic()
    try:
        while len(vetores) < a.amostras:
            if time.monotonic() - comecou > 120:
                print("[cadastro] dois minutos sem completar. Desisti.")
                break
            ok, img = cap.read()
            if ok is None:
                time.sleep(0.01)
                continue
            if not ok:
                print("[cadastro] a camera caiu.")
                break
            if time.monotonic() < proxima:
                continue

            # Resolucao cheia: foto de cadastro nao tem pressa, e ponto melhor
            # marcado gera embedding melhor.
            linhas = motor.detect(img, full_res=True)
            if len(linhas) == 0:
                continue
            if len(linhas) > 1:
                # DOIS ROSTOS E MOTIVO PARA PARAR, nao para escolher o maior:
                # cadastrar a pessoa errada e um erro que ninguem percebe
                # depois, porque o nome fica certo e a cara e de outro.
                print("  ... mais de um rosto no quadro; fique sozinho na frente")
                proxima = time.monotonic() + 1.0
                continue

            vetores.append([float(v) for v in motor.embedding(img, linhas[0])])
            proxima = time.monotonic() + a.intervalo
            print(f"  amostra {len(vetores)} de {a.amostras}   (mexa a cabeca)")
    finally:
        cap.release()

    if len(vetores) < 3:
        print(f"\n[cadastro] so {len(vetores)} amostra(s). Poucas demais para "
              "cadastrar — o reconhecimento sairia fragil. Tente de novo.")
        return 1

    r = mandar(a.servidor, a.nome.strip(), vetores)
    if r.get("erro"):
        print(f"\n[cadastro] o servidor recusou: {r['erro']}")
        return 1
    print(f"\n[cadastro] PRONTO. {r['nome']} — {r['amostras']} amostras, "
          f"tipo {r['tipo']}, vence em {r['vence']}.")
    print("  Agora rode a sala com --rosto e ele aparece pelo nome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
