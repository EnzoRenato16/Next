# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python-headless", "requests"]
# ///
"""O laco da Sala rodando DENTRO da AIBOX, sem navegador.

    camera --RTSP--> OpenCV --> YOLO11-pose (ONNX Runtime) --> 17 pontos COCO
           --> as 12 caracteristicas --> a rede de queda --> POST /api/evento

E o mesmo desenho que o professor do desafio descreveu, com o nosso cerebro no
meio. O cerebro nao foi reescrito: as 12 caracteristicas vem de treino/extrair.py
e os 113 pesos de treino/modelo.json — os mesmos arquivos que o navegador usa e
os mesmos que o treino produziu.

O QUE SAI DE CENA: o go2rtc. O navegador precisava dele porque o Chrome nao abre
RTSP; o OpenCV abre. Um pedaco a menos para dar errado na hora da apresentacao.

    uv run aibox/sala.py --olho mediapipe      # no PC, para ver funcionando
    uv run aibox/sala.py                       # na caixa, com YOLO em ONNX

Configuracao no .env, ao lado do servidor.py:
    CAMERA_RTSP=rtsp://usuario:senha@192.168.0.50:554/stream2
    SERVIDOR=http://127.0.0.1:8000
    LOCAL_CAMERA=sala-12
    OLHO=yolo                 (ou mediapipe)
    MODELO=yolo11n-pose.onnx
    CALIBRACAO=1

A SENHA DA CAMERA MORA NO .env E EM MAIS LUGAR NENHUM. O .env nao vai para o
git, e e por isso que ele existe.

Sobre o fluxo: use o SUBSTREAM da camera (resolucao menor) e nao o principal.
Abrir conexao a mais numa camera que ja esta servindo a plataforma e pedir para
ela engasgar no meio da demonstracao, e a analise nao ganha nada com 4K — os
pontos do corpo saem iguais.
"""
import argparse
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from aibox import custo, olho as olho_mod, trilhas  # noqa: E402

LOTE_CALIB = 200           # o servidor recusa acima de 500
ENVIA_CALIB_S = 15.0
RECONECTA_S = 3.0


def carregar_env():
    """O mesmo .env do servidor.py, lido do mesmo jeito e sem dependencia."""
    caminho = os.path.join(RAIZ, ".env")
    if not os.path.exists(caminho):
        return
    for linha in open(caminho, encoding="utf-8"):
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def abrir_camera(url):
    import cv2
    # TCP em vez de UDP: numa rede de escola o UDP perde pacote e o quadro
    # chega rasgado, o que o detector le como corpo torto — alarme falso com
    # causa na rede, que e o pior tipo de alarme falso para diagnosticar.
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    cap = cv2.VideoCapture(url)
    try:
        # Buffer de 1: com fila, o que se analisa e o passado. Alerta de queda
        # atrasado 2s e alerta que chega depois de a pessoa ja ter levantado.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


class Fala:
    """Conversa com o servidor. Falha em silencio para nao derrubar o laco, mas
    CONTA as falhas — um enviador que erra calado e indistinguivel de um que
    funciona, e foi assim que a foto do alerta ficou um dia sem subir."""

    def __init__(self, base, camera):
        import requests
        self.req = requests
        self.base = base.rstrip("/")
        self.camera = camera
        self.enviados = 0
        self.falhas = 0

    def evento(self, tipo, corpo):
        try:
            r = self.req.post(f"{self.base}/api/evento", timeout=4, json=dict(
                aluno_id=f"corpo-{corpo}"[:50], tipo_evento=tipo,
                localizacao=self.camera))
            if r.ok:
                self.enviados += 1
                return True
        except Exception:
            pass
        self.falhas += 1
        return False

    def calibracao(self, amostras):
        try:
            r = self.req.post(f"{self.base}/api/calibracao", timeout=6,
                              json=dict(camera=self.camera, amostras=amostras))
            return r.status_code            # 403 = registro desligado la
        except Exception:
            return 0


def amostra_de(t, alertou, ms_rede, ms_analise):
    return dict(
        corpo=t.id, fps=float(t.fps), analisavel=1 if t.analisavel else 0,
        nota=round(t.notaQueda, 4), fora=round(t.foraDoTreino, 2),
        geo=1 if t.quedaDesde else 0, vel=round(t.velocidade, 3),
        ang=round(t.ang, 1), baixo=round(t.baixo, 3), prop=round(t.prop, 3),
        alertou=alertou,
        ms_rede=round(ms_rede, 2), ms_analise=round(ms_analise, 2),
        heap=custo.memoria_mb(), cpu=custo.cpu_pct())


def main():
    carregar_env()
    p = argparse.ArgumentParser(description="Auditix IA dentro da AIBOX")
    p.add_argument("--camera", default=os.environ.get("CAMERA_RTSP"))
    p.add_argument("--olho", default=os.environ.get("OLHO", "yolo"))
    p.add_argument("--modelo", default=os.environ.get("MODELO"))
    p.add_argument("--servidor", default=os.environ.get("SERVIDOR", "http://127.0.0.1:8000"))
    p.add_argument("--local", default=os.environ.get("LOCAL_CAMERA", "sala-12"))
    p.add_argument("--mostrar", action="store_true",
                   help="imprime uma linha de estado por segundo")
    # Para a sessao de medicao: "roda meia hora e para sozinho" e melhor do que
    # depender de alguem lembrar de apertar Ctrl+C na hora certa.
    p.add_argument("--segundos", type=float, default=0,
                   help="para sozinho depois deste tempo (0 = roda ate Ctrl+C)")
    a = p.parse_args()

    if not a.camera:
        print("falta a camera. ponha CAMERA_RTSP=... no .env, ou use --camera.\n"
              "para testar sem camera IP, --camera 0 abre a webcam do PC.")
        return 2
    fonte = int(a.camera) if str(a.camera).isdigit() else a.camera

    print(f"[aibox] olho: {a.olho}   camera: "
          f"{'webcam ' + str(fonte) if isinstance(fonte, int) else '(rtsp do .env)'}")
    vis = olho_mod.abrir(a.olho, a.modelo)
    fala = Fala(a.servidor, a.local)
    rebanho = trilhas.Rebanho()
    calib_ligada = os.environ.get("CALIBRACAO", "0").strip().lower() in ("1", "sim", "true")
    fila, ultimo_envio = [], time.monotonic()

    import cv2
    cap = abrir_camera(fonte)
    # FALHA CEDO E EM VOZ ALTA. Sem isto, uma URL errada entra no laco de
    # reconexao e fica tentando para sempre, calada — e quem esta instalando
    # passa vinte minutos achando que a camera e que esta ruim.
    if not cap.isOpened():
        print(f"\n[aibox] NAO CONSEGUI ABRIR A CAMERA.\n"
              f"  o que tentei: {'webcam ' + str(fonte) if isinstance(fonte, int) else fonte}\n"
              f"  confira, nesta ordem:\n"
              f"   1. a caixa alcanca a camera?   ping -c2 <ip-da-camera>\n"
              f"   2. a porta 554 responde?       nc -vz <ip-da-camera> 554\n"
              f"   3. o caminho do stream esta certo? (costuma ser /stream1 ou /stream2)\n"
              f"   4. usuario e senha estao no CAMERA_RTSP do .env?\n")
        # Fecha o detector tambem AQUI. Estava fechado so no `finally` do
        # laco, que este `return` nunca alcanca — e o traceback de
        # encerramento do MediaPipe voltava a aparecer justamente no
        # caminho de erro, logo abaixo da mensagem que explica o erro de
        # verdade. Duas coisas vermelhas na tela, e a que importa e a de cima.
        getattr(vis, "fechar", lambda: None)()
        return 3
    t0 = time.monotonic()
    quadros, perdidos, ultima_linha = 0, 0, t0
    custo.cpu_pct()                      # primeira leitura, so para ancorar

    try:
        while True:
            if a.segundos and time.monotonic() - t0 >= a.segundos:
                print(f"[aibox] {a.segundos:.0f}s cumpridos, encerrando.")
                break
            ok, img = cap.read()
            if not ok:
                perdidos += 1
                # Camera de escola cai. Reabrir e barato; deixar o processo
                # morrer no meio da aula nao e.
                cap.release()
                time.sleep(RECONECTA_S)
                cap = abrir_camera(fonte)
                continue

            alt, larg = img.shape[:2]
            asp = larg / max(alt, 1)
            agora = (time.monotonic() - t0) * 1000.0

            m0 = time.perf_counter()
            det = vis.ver(img)
            m1 = time.perf_counter()
            alertas = rebanho.quadro(det, asp, agora)
            m2 = time.perf_counter()
            ms_rede, ms_analise = (m1 - m0) * 1000, (m2 - m1) * 1000
            quadros += 1

            for al in alertas:
                ok_env = fala.evento(al["tipo"], al["corpo"])
                print(f"[{al['tipo'].upper()}] corpo #{al['corpo']} — "
                      f"{al['porque']}" + ("" if ok_env else "   (NAO REGISTRADO)"))

            if calib_ligada:
                agora_por_corpo = {al["corpo"]: al["tipo"] for al in alertas}
                for t in rebanho.trilhas.values():
                    if t.visto != agora or not t.firme:
                        continue
                    # Uma amostra por corpo por segundo, igual ao navegador.
                    if agora - getattr(t, "calibEm", -1e9) < 1000:
                        continue
                    t.calibEm = agora
                    fila.append(amostra_de(t, agora_por_corpo.get(t.id, ""),
                                           ms_rede, ms_analise))
                if fila and time.monotonic() - ultimo_envio > ENVIA_CALIB_S:
                    st = fala.calibracao(fila[:LOTE_CALIB])
                    if st == 403:
                        print("[aibox] o servidor esta com CALIBRACAO=0; parei de medir")
                        calib_ligada, fila = False, []
                    elif st:
                        fila = fila[LOTE_CALIB:]
                    ultimo_envio = time.monotonic()
                    # Teto de seguranca: servidor mudo nao pode encher a memoria
                    if len(fila) > 2000:
                        fila = fila[-500:]

            if a.mostrar and time.monotonic() - ultima_linha >= 1.0:
                ultima_linha = time.monotonic()
                fps = quadros / max(time.monotonic() - t0, 1e-6)
                print(f"  {fps:5.1f} fps | rede {ms_rede:5.1f}ms | "
                      f"analise {ms_analise:5.1f}ms | cpu {custo.cpu_pct():5.1f}% | "
                      f"ram {custo.memoria_mb():6.1f}MB | "
                      f"{len(rebanho.trilhas)} corpo(s) | "
                      f"{fala.enviados} enviados, {fala.falhas} falhas")
    except KeyboardInterrupt:
        print("\n[aibox] encerrando.")
    finally:
        # O que sobrou na fila vai embora antes de fechar: perder os ultimos
        # 15s de medicao por causa do encerramento seria perder justamente o
        # trecho que alguem estava olhando quando resolveu parar.
        if calib_ligada and fila:
            fala.calibracao(fila[:LOTE_CALIB])
        cap.release()
        getattr(vis, "fechar", lambda: None)()
        seg = max(time.monotonic() - t0, 1e-6)
        print(f"[aibox] {quadros} quadros em {seg:.0f}s "
              f"({quadros / seg:.1f} fps), {perdidos} reconexoes, "
              f"{fala.enviados} eventos enviados, {fala.falhas} falharam")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
