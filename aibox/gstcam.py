"""Ler RTSP por GStreamer, porque o OpenCV desta caixa nao le.

DE ONDE ISTO VEIO, medido na AIBOX do desafio (Qualcomm QCS6490, Ubuntu 20.04):

    cv2.getBuildInformation()  ->  FFMPEG: YES   GStreamer: NO
    cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
        VIDEOIO(FFMPEG): backend is generally available but can't be used
                         to capture by name
        abriu: False

O FFmpeg aparece na lista mas o plugin nao carrega, e sem GStreamer compilado
nao ha segunda opcao dentro do OpenCV. O `ffprobe` do sistema tambem nao ajuda:
responde "Protocol not found" para rtsp://. A caixa, pelo OpenCV, e cega para
camera IP.

O que ELA TEM e o `gst-launch-1.0` como programa, e esse funciona. Entao a
saida e chamar o GStreamer por fora e ler os quadros crus pela saida padrao.
Confirmado na mesma caixa: 2.000.000 bytes de BGR em 10 segundos.

A classe imita a interface do cv2.VideoCapture — `isOpened`, `read`, `release`,
`set` — de proposito. Assim o laco em sala.py nao muda NEM UMA LINHA: ele nao
precisa saber que o motor por baixo e outro. Trocar o mundo em volta de um
codigo que funciona e melhor que reescreve-lo.
"""
import os
import subprocess
import threading

import numpy as np

# Fixos, e nao descobertos do fluxo: video cru nao tem cabecalho dizendo o
# tamanho, entao quem le precisa saber de antemao quantos bytes valem um
# quadro. Forcar a escala aqui resolve isso e ainda economiza CPU — 640x360 e
# resolucao de sobra para achar corpo, e a camera entrega bem mais que isso.
LARG = int(os.environ.get("CAM_LARG", "640"))
ALT = int(os.environ.get("CAM_ALT", "360"))


def _comando(url):
    return [
        "gst-launch-1.0", "-q",          # -q cala o status: a saida e binaria
        "rtspsrc", "location=" + url,
        "user-id=" + os.environ.get("CAM_USER", ""),
        "user-pw=" + os.environ.get("CAM_PW", ""),
        # TCP e nao UDP: em rede de escola o UDP perde pacote e o quadro chega
        # rasgado, o que o detector le como corpo torto — alarme falso com
        # causa na rede, que e o pior tipo para diagnosticar.
        "protocols=tcp", "latency=100",
        "!", "rtph264depay", "!", "h264parse", "!", "avdec_h264",
        # A FILA VAZA DE PROPOSITO (leaky=downstream, 2 quadros). Sem ela, o
        # GStreamer BLOQUEIA quando o cano enche, e como a analise e mais lenta
        # que a camera o cano vive cheio: o que se analisa passa a ser o
        # passado, e o atraso cresce sem parar. Melhor perder quadro velho que
        # acusar uma queda que ja terminou.
        "!", "queue", "leaky=downstream", "max-size-buffers=2",
        "!", "videoconvert", "!", "videoscale",
        "!", f"video/x-raw,format=BGR,width={LARG},height={ALT}",
        "!", "fdsink",
    ]


class Gst:
    """Um cv2.VideoCapture que por dentro e um processo do GStreamer."""

    def __init__(self, url):
        self.n = LARG * ALT * 3
        # stderr NAO e silenciado de proposito. Se a senha estiver errada, o
        # GStreamer escreve "Unauthorized (401)" ali — e quem esta instalando
        # precisa VER isso. Um leitor que falha calado faz a pessoa procurar o
        # defeito no lugar errado por vinte minutos.
        # Com NUCLEOS=grandes, o Python fica nos nucleos grandes (o modelo) e
        # este filho nasce nos pequenos: decodificar e leve e cabe neles, e nao
        # disputa com a inferencia. Sem a variavel, nao muda nada.
        from aibox import nucleos
        self.p = subprocess.Popen(_comando(url), stdout=subprocess.PIPE,
                                  preexec_fn=(nucleos.soltar_nos_pequenos
                                              if os.name == "posix" else None))

        # O QUADRO E LIDO NUMA THREAD PROPRIA, e so o MAIS NOVO e guardado.
        #
        # Sem isto, a analise puxava um quadro do cano por vez: com a camera a
        # 15/s e a analise a 8/s, metade se acumulava, e o que o modelo via era
        # cada vez mais velho. Numa deteccao de queda isso e pior que perder
        # quadro — o alerta chega depois de a pessoa ja ter levantado.
        #
        # Aqui o descarte e explicito e o atraso fica limitado a um quadro.
        self.ultimo = None
        self.vivo = True
        self.lidos = 0          # quantos a camera entregou
        self.perdidos = 0       # quantos foram descartados por atraso
        self._trava = threading.Lock()
        self._t = threading.Thread(target=self._puxar, daemon=True)
        self._t.start()

    def _puxar(self):
        while self.vivo:
            b = b""
            while len(b) < self.n:
                # Le ATE COMPLETAR: um cano nao promete entregar tudo de uma
                # vez, e um `read` curto viraria meia imagem colada na metade
                # do quadro anterior — que o detector leria como corpo torto,
                # sem nenhum aviso de que algo deu errado.
                pedaco = self.p.stdout.read(self.n - len(b))
                if not pedaco:
                    self.vivo = False
                    return
                b += pedaco
            q = np.frombuffer(b, np.uint8).reshape(ALT, LARG, 3)
            with self._trava:
                if self.ultimo is not None:
                    self.perdidos += 1
                self.ultimo = q
                self.lidos += 1

    def isOpened(self):
        return self.p.poll() is None

    def read(self):
        """O quadro MAIS NOVO, e o consome. Devolve (False, None) quando nao ha
        nada novo ainda — o laco trata isso como 'espera um pouco', nao como
        camera caida, porque a camera pode simplesmente ser mais lenta que a
        volta do laco."""
        with self._trava:
            q, self.ultimo = self.ultimo, None
        if q is None:
            return (False, None) if not self.vivo else (None, None)
        return True, q

    def release(self):
        self.vivo = False
        try:
            self.p.kill()
            self.p.wait(timeout=2)
        except Exception:
            pass

    def set(self, *_):
        """Existe so para o laco poder chamar sem saber quem esta do outro
        lado. O tamanho do buffer aqui e do GStreamer, nao nosso."""
        return False
