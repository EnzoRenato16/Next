"""O balcao de cadastro: a camera de baixo, operada pela tela /cadastro do PC.

    GET  /video       a camera de cadastro em MJPEG, com o rosto marcado
    GET  /estado      em que pe esta: fase, amostras, mensagem
    POST /cadastrar   {"nome": "..."}  comeca a colher o rosto
    POST /cancelar

POR QUE EXISTE. O laboratorio tem duas cameras: a .108 no alto, que vigia a
sala, e a .109 na altura do rosto. A tela /cadastro do PC nao alcanca nenhuma
das duas: ela abre a webcam do proprio PC (que o laboratorio nao tem), e
navegador nenhum le RTSP. E mesmo que lesse, ela mede o rosto com o motor do
navegador (face-api), que a caixa NAO le: quem reconhece na sala e o SFace,
aqui dentro. Um cadastro medido pelo motor errado nao da erro nenhum, so nunca
reconhece ninguem.

Entao a tela PEDE e a caixa FAZ: abre a camera de cadastro, mostra a imagem na
tela do PC, colhe as amostras com o mesmo motor que vai reconhecer depois, e
manda os 128 numeros para o servidor. E o mesmo caminho do aibox/cadastrar.py,
so que operado por botao em vez de terminal.

A CAMERA SO ABRE QUANDO ALGUEM PEDE, e fecha sozinha DESLIGA_S depois que
ninguem mais olha. Cadastro e coisa de minutos por semana; a analise de queda e
o dia inteiro, e nao divide processador com um balcao vazio.

A IMAGEM NAO E GRAVADA EM LUGAR NENHUM. O quadro vira o MJPEG da tela e, na
hora de colher, os 128 numeros; depois some. So os numeros vao para o servidor,
que os gira com a chave antes de encostar no disco (ver `proteger` no
servidor.py).

O que NAO tem aqui, dito na tela tambem: prova de vida. A da webcam (abrir a
boca, virar a cabeca) usa os 68 pontos do face-api; o YuNet da caixa da 5, e
uma boca aberta nao se mede com os dois cantos dela.

Sozinho, sem a analise da sala:   $P aibox/balcao.py
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

PORTA = int(os.environ.get("BALCAO_PORTA", "8081"))
AMOSTRAS = 6
INTERVALO_S = 1.5          # entre amostras: tempo de a pessoa mexer a cabeca
DESISTE_S = 120.0          # colhendo ha dois minutos sem completar: desiste
DESLIGA_S = 20.0           # ninguem olhando por isto: fecha a camera
PREVIA_FPS = 8.0           # a imagem da tela; mais que isso e CPU jogada fora
# O rosto tem de ocupar pelo menos esta fracao da altura do quadro. Menor que
# isso, o SFace alinha um rosto de poucos pixels esticado para 112x112, e o
# cadastro sai pobre: reconhece mal depois, e ninguem sabe por que. Vem do .env
# porque a distancia da camera de baixo so se conhece no local.
ROSTO_MIN = float(os.environ.get("BALCAO_ROSTO_MIN", "0.15"))

FASES_OCUPADAS = ("colhendo", "gravando")


def _mandar(base, nome, vetores, espera=8):
    corpo = json.dumps({"nome": nome, "tipo": "sface",
                        "descritores": vetores}).encode("utf-8")
    pedido = urllib.request.Request(
        base.rstrip("/") + "/api/cadastro", data=corpo,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=espera) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"erro": f"{e.code} {e.read().decode('utf-8', 'replace')[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)}


def _motor_de_verdade():
    from daten.app.recognizer import FaceEngine
    return FaceEngine()


def _abrir_de_verdade(url):
    from aibox.sala import abrir_camera
    return abrir_camera(int(url) if str(url).isdigit() else url)


class Balcao:
    def __init__(self, camera, servidor, porta=PORTA, *, motor=None, abrir=None,
                 mandar=None, amostras=AMOSTRAS, intervalo=INTERVALO_S,
                 desliga=DESLIGA_S, desiste=DESISTE_S, previa_fps=PREVIA_FPS,
                 rosto_min=ROSTO_MIN):
        self.camera = camera
        self.servidor = servidor
        # As pecas de fora entram por parametro para o teste trocar por falsas:
        # o motor de verdade precisa de um rosto de verdade na frente de uma
        # camera de verdade, e isso nao se testa com codigo. O que se testa e
        # a cola, que e onde os defeitos moram.
        self._fab_motor = motor or _motor_de_verdade
        self._abrir = abrir or _abrir_de_verdade
        self._mandar = mandar or _mandar
        self.total = amostras
        self.intervalo = intervalo
        self.desliga = desliga
        self.desiste = desiste
        self.passo_previa = 1.0 / previa_fps
        self.rosto_min = rosto_min

        self.motor = None
        self.jpeg = None
        self._trava = threading.Lock()
        self._t = None
        self._parar = threading.Event()
        self._visto = 0.0
        self.estado = dict(fase="desligado", amostras=0, total=amostras,
                           rostos=0, perto=False, tamanho=None, nome=None,
                           mensagem="Câmera de cadastro desligada.", resultado=None)
        self._vetores = []
        self._proxima = 0.0
        self._comecou = 0.0

        self.porta = porta
        self._srv = None
        if porta:
            self._srv = ThreadingHTTPServer(("0.0.0.0", porta), _fabricar(self))
            self._srv.daemon_threads = True
            threading.Thread(target=self._srv.serve_forever, daemon=True,
                             name="balcao-http").start()

    # ------------------------------------------------------------ a tela pede
    def ligar(self):
        """Alguem esta olhando. Abre a camera se estiver fechada."""
        with self._trava:
            self._visto = time.monotonic()
            if self._t is not None and self._t.is_alive():
                return
            self._parar.clear()
            # NAO PISA num cadastro em andamento. O `cadastrar` marca "colhendo"
            # e SO DEPOIS liga a camera; sobrescrever aqui perdia o pedido, e o
            # proximo clique — de outra pessoa — era aceito no lugar dele. O
            # teste pegou isso cadastrando o nome errado.
            if self.estado["fase"] not in FASES_OCUPADAS:
                self.estado["fase"] = "abrindo"
            self.estado["mensagem"] = "Abrindo a câmera de cadastro…"
            self._t = threading.Thread(target=self._laco, daemon=True, name="balcao")
            self._t.start()

    def tocar(self):
        """Alguem continua olhando: adia o desligamento, mas NAO religa. Quem
        religa e so o `ligar`, chamado uma vez por pedido. Se o assistir
        religasse, uma camera que falha ao abrir viraria um laco de tentativas
        enquanto a aba estivesse aberta, cada uma subindo um GStreamer novo."""
        with self._trava:
            self._visto = time.monotonic()

    def cadastrar(self, nome):
        nome = (nome or "").strip()
        if not nome or len(nome) > 80:
            return 400, "o nome tem de ter de 1 a 80 letras"
        with self._trava:
            if self.estado["fase"] in FASES_OCUPADAS:
                return 409, f"ja cadastrando {self.estado['nome']}"
            self._vetores = []
            self._proxima = 0.0
            self._comecou = time.monotonic()
            self.estado.update(fase="colhendo", nome=nome, amostras=0, resultado=None,
                               mensagem=f"Colhendo o rosto de {nome}…")
        self.ligar()
        return 200, "ok"

    def cancelar(self):
        with self._trava:
            if self.estado["fase"] == "colhendo":
                self._vetores = []
                self.estado.update(fase="olhando", amostras=0, nome=None,
                                   mensagem="Cancelado. Nada foi gravado.")

    def ver_estado(self):
        with self._trava:
            return dict(self.estado)

    def fechar(self):
        self._parar.set()
        if self._t is not None:
            self._t.join(timeout=3)
        if self._srv is not None:
            try:
                self._srv.shutdown()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------- por dentro
    def _por(self, **campos):
        with self._trava:
            self.estado.update(campos)

    def _laco(self):
        try:
            self._laco_dentro()
        except Exception as e:  # noqa: BLE001
            # Um erro calado aqui deixaria a tela esperando imagem para sempre,
            # com a fase dizendo "olhando". Dito na tela, alguem le.
            self._por(fase="erro", mensagem=f"O balcão parou: {e}")

    def _laco_dentro(self):
        import cv2
        try:
            if self.motor is None:
                self._por(mensagem="Carregando o motor de rosto (só na primeira vez)…")
                self.motor = self._fab_motor()
        except FileNotFoundError:
            return self._por(fase="erro", mensagem=(
                "Faltam os modelos de rosto na caixa. No PC: pc modelos"))
        except Exception as e:  # noqa: BLE001
            return self._por(fase="erro", mensagem=f"O motor de rosto não subiu: {e}")

        cap = self._abrir(self.camera)
        if not cap.isOpened():
            return self._por(fase="erro", mensagem=(
                "A câmera de cadastro não abriu. Confira CAMERA_CADASTRO e o "
                "login da câmera (CAM_USER/CAM_PW) no .env da caixa."))
        with self._trava:
            if self.estado["fase"] not in FASES_OCUPADAS:
                self.estado["fase"] = "olhando"
            self.estado["mensagem"] = "Câmera ligada. Fique de frente, sozinho."
        ultima_previa = 0.0
        abriu = time.monotonic()
        try:
            while not self._parar.is_set():
                agora = time.monotonic()
                with self._trava:
                    ocupado = self.estado["fase"] in FASES_OCUPADAS
                    parado = agora - self._visto
                if not ocupado and parado > self.desliga:
                    break
                ok, img = cap.read()
                if ok is None or (ok is False and cap.isOpened()):
                    time.sleep(0.01)
                    continue
                if not ok:
                    # O ENDERECO VAI NA MENSAGEM. No laboratorio a primeira
                    # tentativa foi 192.168.109 (sem o "50."), e "caiu" sozinho
                    # nao deixava ver isso da tela. Credencial nunca vem na URL.
                    self._por(fase="erro", mensagem=(
                        f"A câmera de cadastro caiu ({self.camera}). Confira o "
                        "endereço em CAMERA_CADASTRO e o terminal da caixa."))
                    return
                if agora - ultima_previa < self.passo_previa:
                    continue
                ultima_previa = agora
                self._um_quadro(cv2, img, agora)
                # Sem quadro nenhum em 15 s e camera que nao entrega: dizer.
                if self.jpeg is None and agora - abriu > 15:
                    self._por(fase="erro", mensagem="A câmera de cadastro não entrega imagem.")
                    return
        finally:
            cap.release()
            with self._trava:
                self.jpeg = None
                if self.estado["fase"] not in ("erro", "pronto"):
                    self.estado.update(fase="desligado",
                                       mensagem="Câmera de cadastro desligada.")

    def _um_quadro(self, cv2, img, agora):
        alt = img.shape[0]
        rostos = self.motor.detect(img, full_res=True)
        n = len(rostos)
        tam = float(rostos[0][3]) / alt if n == 1 else None
        perto = tam is not None and tam >= self.rosto_min

        # O rosto marcado na imagem: verde se e UM e esta perto, ambar se nao.
        desenho = img.copy()
        for r in rostos:
            x, y, w, h = (int(v) for v in r[:4])
            cor = (160, 191, 95) if (n == 1 and perto) else (123, 192, 229)
            cv2.rectangle(desenho, (x, y), (x + w, y + h), cor, 2, cv2.LINE_AA)
        feito, buf = cv2.imencode(".jpg", desenho, [int(cv2.IMWRITE_JPEG_QUALITY), 75])

        with self._trava:
            if feito:
                self.jpeg = buf.tobytes()
            self.estado.update(rostos=n, perto=bool(n == 1 and perto),
                               tamanho=None if tam is None else round(tam, 2))
            colhendo = self.estado["fase"] == "colhendo"
            nome = self.estado["nome"]
        if not colhendo:
            if self.estado["fase"] == "olhando":
                self._por(mensagem=self._dica(n, perto, tam))
            return

        if agora - self._comecou > self.desiste:
            self._por(fase="erro", mensagem=(
                f"Dois minutos sem completar o cadastro de {nome}. Nada foi gravado."))
            return
        if n != 1 or not perto:
            # DOIS ROSTOS E MOTIVO PARA ESPERAR, nao para escolher o maior:
            # cadastrar a pessoa errada e um erro que ninguem percebe depois,
            # porque o nome fica certo e a cara e de outro.
            self._por(mensagem=self._dica(n, perto, tam))
            return
        if agora < self._proxima:
            return
        self._vetores.append([float(v) for v in self.motor.embedding(img, rostos[0])])
        self._proxima = agora + self.intervalo
        k = len(self._vetores)
        self._por(amostras=k, mensagem=(
            f"Amostra {k} de {self.total}. Mexa a cabeça devagar: "
            "um pouco para cada lado, um pouco para baixo."))
        if k < self.total:
            return

        self._por(fase="gravando", mensagem=f"Gravando o cadastro de {nome}…")
        r = self._mandar(self.servidor, nome, self._vetores)
        self._vetores = []
        if r.get("erro"):
            self._por(fase="erro", mensagem=f"O servidor recusou: {r['erro']}")
        else:
            self._por(fase="pronto", resultado=r, mensagem=(
                f"{r.get('nome', nome)} cadastrado: {r.get('amostras')} amostras. "
                "Já vale na sala, com o reconhecimento ligado (ir.sh --rosto)."))

    def _dica(self, n, perto, tam):
        if n == 0:
            return "Não estou vendo nenhum rosto."
        if n > 1:
            return f"Estou vendo {n} rostos. Fique sozinho na frente da câmera."
        if not perto:
            return (f"Chegue mais perto: o rosto ocupa {tam:.0%} da imagem, "
                    f"e precisa de {self.rosto_min:.0%}.")
        return "Um rosto, perto o bastante. Escreva o nome e clique em cadastrar."


def _fabricar(b):
    class Mao(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            """Calado, como o da imagem ao vivo: o log da sala e o que importa."""

        # A TELA MORA EM OUTRA MAQUINA (o PC), entao o navegador so aceita a
        # resposta se a caixa disser que aceita pedido de fora. A imagem em
        # <img> nao precisaria disso; o estado e o cadastro, por fetch, sim.
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def _json(self, codigo, obj):
            corpo = json.dumps(obj).encode("utf-8")
            self.send_response(codigo)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/video"):
                return self._video()
            if self.path.startswith("/estado"):
                return self._json(200, b.ver_estado())
            return self._json(404, {"erro": "rotas: /video, /estado, /cadastrar"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return self._json(400, {"erro": "corpo nao e JSON"})
            if self.path.startswith("/cadastrar"):
                codigo, msg = b.cadastrar(corpo.get("nome"))
                return self._json(codigo, b.ver_estado() if codigo == 200
                                  else {"erro": msg})
            if self.path.startswith("/cancelar"):
                b.cancelar()
                return self._json(200, b.ver_estado())
            return self._json(404, {"erro": "rota desconhecida"})

        def _video(self):
            # O mesmo MJPEG da imagem ao vivo (ver aibox/vivo.py): HTTP/1.0 e
            # Connection: close so nesta rota, porque fluxo sem fim nao tem
            # Content-Length. Enquanto este cano estiver aberto, a camera fica
            # ligada: fechar a aba e o que a desliga, DESLIGA_S depois.
            self.protocol_version = "HTTP/1.0"
            b.ligar()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            ultimo = None
            try:
                while True:
                    b.tocar()           # quem assiste mantem a camera acesa
                    with b._trava:
                        q = b.jpeg
                        fase = b.estado["fase"]
                    if fase == "erro" and q is None:
                        break
                    if q is None or q is ultimo:
                        time.sleep(0.03)
                        continue
                    ultimo = q
                    self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: " + str(len(q)).encode() +
                                     b"\r\n\r\n" + q + b"\r\n")
            except Exception:  # noqa: BLE001
                pass            # a aba fechou; nao e erro
    return Mao


def main():
    from aibox.sala import carregar_env
    carregar_env()
    camera = os.environ.get("CAMERA_CADASTRO") or os.environ.get("CAMERA_RTSP")
    servidor = os.environ.get("SERVIDOR", "http://127.0.0.1:8000")
    if not camera:
        print("[balcao] falta CAMERA_CADASTRO (ou CAMERA_RTSP) no .env da caixa.")
        return 2
    b = Balcao(camera, servidor, PORTA)
    print(f"[balcao] camera de cadastro: {camera}")
    print(f"[balcao] no PC, abra:  {servidor.rstrip('/')}/cadastro?caixa=<ip-da-caixa>:{PORTA}")
    print("[balcao] (Ctrl+C para parar)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        b.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
