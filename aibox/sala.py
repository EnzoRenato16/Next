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

from aibox import custo, olho as olho_mod, trilhas, vivo as vivo_mod  # noqa: E402

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
    """RTSP vai pelo GStreamer; webcam e arquivo continuam no OpenCV.

    A escolha e pelo endereco e nao por configuracao: quem instala nao deveria
    precisar saber que esta caixa tem um OpenCV sem suporte a camera IP. Ver o
    porque inteiro, com as mensagens medidas, no topo de aibox/gstcam.py."""
    if str(url).startswith("rtsp"):
        from aibox.gstcam import Gst
        return Gst(url)
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


# A entrega mora em aibox/entrega.py: fila, thread e reenvio sem duplicar.
# O laco daqui so ENTREGA e segue — nunca espera a rede.
from aibox.entrega import Fala  # noqa: E402


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
    # A janela ao vivo. Sem imagem ninguem confia no que o sistema diz — e com
    # razao: "3 corpos" numa linha de texto pode ser tres pessoas ou tres
    # cadeiras. 0 desliga.
    p.add_argument("--web", type=int, default=int(os.environ.get("WEB", "8080")),
                   help="porta da imagem ao vivo no navegador (0 desliga)")
    # DESLIGADO POR PADRAO, e de proposito. O reconhecimento custa CPU numa
    # caixa que ja esta apertada de quadros por segundo, e a analise de queda —
    # que e o que o desafio pede — nao pode piorar porque um extra foi ligado
    # sem ninguem decidir. Quem liga, decide.
    p.add_argument("--rosto", action="store_true",
                   help="reconhece quem esta cadastrado (usa o motor de daten/)")
    a = p.parse_args()

    if not a.camera:
        print("falta a camera. ponha CAMERA_RTSP=... no .env, ou use --camera.\n"
              "para testar sem camera IP, --camera 0 abre a webcam do PC.")
        return 2
    fonte = int(a.camera) if str(a.camera).isdigit() else a.camera

    # A ORIGEM SAI NA TELA, sem senha. A primeira versao escrevia sempre
    # "(rtsp do .env)", inclusive quando a origem era um arquivo de video —
    # mentira pequena que faz perder tempo procurando defeito na camera errada.
    if isinstance(fonte, int):
        de_onde = f"webcam {fonte}"
    elif str(fonte).startswith("rtsp"):
        de_onde = "rtsp " + str(fonte).split("@")[-1].split("?")[0]
    else:
        de_onde = str(fonte)
    print(f"[aibox] olho: {a.olho}   camera: {de_onde}")
    vis = olho_mod.abrir(a.olho, a.modelo)
    fala = Fala(a.servidor, a.local)
    rebanho = trilhas.Rebanho()
    calib_ligada = os.environ.get("CALIBRACAO", "0").strip().lower() in ("1", "sim", "true")
    fila, ultimo_envio = [], time.monotonic()

    cara = None
    if a.rosto:
        try:
            from aibox import rosto as rosto_mod
            cara = rosto_mod.Rosto(a.servidor)
            print(f"[aibox] rosto: {cara.motor.backend}, "
                  f"olhando a cada {cara.espera:.0f}s")
        except FileNotFoundError:
            # Seguir SEM rosto e melhor que nao subir: a analise de queda nao
            # depende disto. Mas a mensagem diz o CONSERTO, e nao so o erro —
            # quem le isto esta na frente da caixa, sem internet.
            print("[aibox] rosto DESLIGADO: faltam os modelos em daten/models/.\n"
                  "         no PC, na pasta do projeto:  pc modelos")
        except ImportError as e:
            print(f"[aibox] rosto DESLIGADO: {e}\n"
                  "         falta o codigo de daten/app na caixa. no PC:  pc enviar")
        except Exception as e:
            print(f"[aibox] rosto DESLIGADO: {e}")

    janela = None
    if a.web:
        janela = vivo_mod.Vivo(a.web)
        print(f"[aibox] imagem ao vivo em http://<ip-da-caixa>:{a.web}")

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
            if ok is None:
                # NAO e camera caida: e "ainda nao chegou quadro novo". A
                # distincao importa — tratar isso como queda reabriria a camera
                # varias vezes por segundo, e cada reabertura custa 1 a 2
                # segundos de RTSP. O laco simplesmente espera um pouco.
                time.sleep(0.002)
                continue
            if not ok:
                perdidos += 1
                # Camera de escola cai. Reabrir e barato; deixar o processo
                # morrer no meio da aula nao e.
                cap.release()
                time.sleep(RECONECTA_S)
                cap = abrir_camera(fonte)
                continue

            # O relogio do alerta comeca AQUI, quando o quadro chegou a analise.
            # Nao inclui o caminho da camera ate a caixa (RTSP e buffer da
            # camera), que daqui nao da para medir — e a tela diz isso.
            t_quadro = time.monotonic()
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

            if cara is not None:
                # Entrega e segue: quem espera e a outra thread, nunca este
                # laco. O tempo gasto aqui e o de uma copia de quadro.
                cara.ver(img, list(rebanho.trilhas.values()))
                for t in rebanho.trilhas.values():
                    t.nome = cara.nome_de(t.id)

            for al in alertas:
                # O NOME VAI NO EVENTO quando existe. "Enzo caiu" e uma frase
                # que quem le entende; "corpo-7 caiu" obriga a ir procurar quem
                # era o 7. Sem cadastro continua indo o numero — e la ninguem
                # consentiu com nada, que e a razao de o numero existir.
                quem = cara.nome_de(al["corpo"]) if cara is not None else None
                # Entrega e segue. Se o PC nao responder, quem guarda e reenvia
                # e a thread de entrega — e ela avisa na tela quando isso acontece.
                # A PROVA SEM ROSTO vai junto: os ultimos segundos do corpo,
                # em numeros. Sem ela o alerta da caixa chegava ao painel sem
                # evidencia nenhuma — a caixa nao manda foto.
                dono = rebanho.trilhas.get(al["corpo"])
                poses = (trilhas.poses_da_prova(dono, agora, asp)
                         if dono is not None else None)
                fala.evento(al["tipo"], al["corpo"], quem, poses=poses,
                            t_quadro=t_quadro)
                print(f"[{al['tipo'].upper()}] {quem or 'corpo #' + str(al['corpo'])}"
                      f" — {al['porque']}")

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
                    # Entrega o lote e segue; nao espera o servidor. Lote de
                    # medicao que nao chega e descartado — ele nao pode ficar na
                    # frente de um alerta de queda esperando a rede voltar.
                    fala.calibracao(fila[:LOTE_CALIB])
                    fila = fila[LOTE_CALIB:]
                    ultimo_envio = time.monotonic()
                if fala.calib_recusada:
                    calib_ligada, fila = False, []

            # A JANELA SO CUSTA COM ALGUEM OLHANDO. Sem navegador conectado
            # nao ha copia, nao ha desenho e nao ha JPEG — detectar queda vale
            # mais que exibi-la, e numa caixa a 8 quadros por segundo essa
            # diferenca e a demonstracao inteira.
            if janela is not None and janela.clientes:
                pintado = vivo_mod.desenhar(cv2, img.copy(),
                                            list(rebanho.trilhas.values()))
                feito, buf = cv2.imencode(".jpg", pintado,
                                          [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                if feito:
                    janela.publicar(buf.tobytes(), dict(
                        fps=quadros / max(time.monotonic() - t0, 1e-6),
                        rede=ms_rede, analise=ms_analise,
                        cpu=custo.cpu_pct(), ram=custo.memoria_mb(),
                        corpos=len(rebanho.trilhas), enviados=fala.enviados,
                        falhas=fala.falhas, pendentes=fala.pendentes,
                        ultimo_ms=fala.ultimo_ms, servidor=fala.base))

            if a.mostrar and time.monotonic() - ultima_linha >= 1.0:
                ultima_linha = time.monotonic()
                seg = max(time.monotonic() - t0, 1e-6)
                fps = quadros / seg
                # A TAXA DA CAMERA vem ao lado da taxa de analise, e nao e
                # enfeite: se a camera entrega 15/s, 30/s e impossivel por mais
                # que o modelo melhore. Sem este numero, otimizar o modelo pode
                # ser trabalho jogado fora contra um teto que nao e dele.
                cam = getattr(cap, "lidos", 0) / seg
                print(f"  {fps:5.1f} fps | camera {cam:4.1f}/s | "
                      f"rede {ms_rede:5.1f}ms | "
                      f"analise {ms_analise:5.1f}ms | cpu {custo.cpu_pct():5.1f}% | "
                      f"ram {custo.memoria_mb():6.1f}MB | "
                      f"{len(rebanho.trilhas)} corpo(s) | "
                      f"{fala.enviados} enviados, {fala.pendentes} na fila, "
                      f"{fala.falhas} falhas")
    except KeyboardInterrupt:
        print("\n[aibox] encerrando.")
    finally:
        # O que sobrou na fila vai embora antes de fechar: perder os ultimos
        # 15s de medicao por causa do encerramento seria perder justamente o
        # trecho que alguem estava olhando quando resolveu parar.
        if calib_ligada and fila:
            fala.calibracao(fila[:LOTE_CALIB])
        # Alerta que ficou na fila e dito em voz alta, nunca engolido.
        sobrou = fala.fechar(prazo=8.0)
        if sobrou:
            print(f"[aibox] ATENCAO: {sobrou} alerta(s) NAO chegaram ao servidor "
                  f"(ultimo erro: {fala.ultimo_erro})")
        if cara is not None:
            cara.fechar()
        cap.release()
        getattr(vis, "fechar", lambda: None)()
        if janela is not None:
            janela.fechar()
        seg = max(time.monotonic() - t0, 1e-6)
        print(f"[aibox] {quadros} quadros analisados em {seg:.0f}s "
              f"({quadros / seg:.1f} fps), {perdidos} reconexoes, "
              f"{fala.enviados} eventos enviados "
              f"({fala.atrasados} depois de reenvio, {fala.repetidos} ja estavam la), "
              f"{fala.falhas} falharam")
        lidos = getattr(cap, "lidos", 0)
        if lidos:
            # O DESCARTE SAI NO RELATORIO. Quadro perdido em silencio faz
            # parecer que a camera e lenta quando quem esta lenta e a analise.
            print(f"[aibox] a camera entregou {lidos} quadros "
                  f"({lidos / seg:.1f}/s); {getattr(cap, 'perdidos', 0)} foram "
                  f"descartados por a analise nao alcancar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
