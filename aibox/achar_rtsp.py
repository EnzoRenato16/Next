"""Qual e o caminho RTSP desta camera?  Roda no PC, NAO na caixa.

  python aibox\\achar_rtsp.py 192.168.50.109 --usuario admin

(a senha e perguntada na hora e nao aparece na tela nem fica em lugar nenhum)

POR QUE NO PC. Camera bloqueia o IP de quem erra seguido (403; armadilha 5 do
CLAUDE.md). Testar caminhos pela caixa arriscaria bloquear justo a caixa,
que e quem precisa da camera na prova. O OpenCV do PC (pip) abre RTSP; o da
caixa nao abre, e por isso ela usa o gstcam.

Tenta os caminhos mais comuns UM DE CADA VEZ, com pausa entre eles, e para no
primeiro que entrega imagem: diz a resolucao e o codec. A camera HAIZ da
arena (20/10) tem a pagina em /doc/page/main.html, com cara de Hikvision, e
por isso o caminho da Hikvision vem primeiro.
"""
import argparse
import getpass
import sys
import time
from urllib.parse import quote

CAMINHOS = [
    ("Hikvision, fluxo principal", "{c}/Streaming/Channels/101"),
    ("Dahua e Intelbras, fluxo principal", "{c}/cam/realmonitor?channel=1&subtype=0"),
    ("Xiongmai (XMEye)", "/user={u}&password={s}&channel=1&stream=0.sdp"),
    ("ONVIF generico", "{c}/onvif1"),
    ("H.264 generico", "{c}/h264"),
    ("live generico", "{c}/live/ch00_0"),
]


def main():
    p = argparse.ArgumentParser(description="Descobre o caminho RTSP de uma camera")
    p.add_argument("ip")
    p.add_argument("--porta", type=int, default=554)
    p.add_argument("--usuario", default="admin")
    p.add_argument("--pausa", type=float, default=4.0,
                   help="segundos entre uma tentativa e outra (camera bloqueia quem insiste)")
    a = p.parse_args()
    senha = getpass.getpass(f"senha de {a.usuario}@{a.ip}: ")

    import os
    # TCP, como o gstcam da caixa: em rede de escola o UDP chega rasgado.
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    import cv2

    cred = f"{quote(a.usuario, safe='')}:{quote(senha, safe='')}@"
    for i, (nome, molde) in enumerate(CAMINHOS):
        if i:
            time.sleep(a.pausa)
        caminho = molde.format(c="", u=a.usuario, s=senha)
        if molde.startswith("/user="):
            url = f"rtsp://{a.ip}:{a.porta}{caminho}"
        else:
            url = f"rtsp://{cred}{a.ip}:{a.porta}{caminho}"
        mostrar = molde.format(c="", u=a.usuario, s="***")
        print(f"- {nome}: {mostrar} ... ", end="", flush=True)
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        ok, quadro = cap.read() if cap.isOpened() else (False, None)
        if not ok:
            cap.release()
            print("nao")
            continue
        cc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((cc >> 8 * k) & 0xFF) for k in range(4)).strip() or "?"
        alt, larg = quadro.shape[:2]
        cap.release()
        print("ABRIU")
        print(f"\n  caminho:  {mostrar}")
        print(f"  imagem:   {larg}x{alt}")
        print(f"  codec:    {codec}  (hevc/h265 = precisa de CAM_CODEC=h265 na caixa)")
        print("\n  Na caixa, no .env (aspas simples, e troque SENHA pela senha):")
        if molde.startswith("/user="):
            print(f"  CAMERA_ARENA2=rtsp://{a.ip}:{a.porta}"
                  + molde.format(c="", u=a.usuario, s="SENHA"))
        else:
            print(f"  CAMERA_ARENA2=rtsp://{a.usuario}:SENHA@{a.ip}:{a.porta}{caminho}")
        return 0
    print("\nNenhum abriu. Confira usuario e senha na pagina da camera, e procure")
    print("o caminho em Config > Rede > Avancado (RTSP). Nao insista em seguida:")
    print("espere uns minutos antes de tentar de novo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
