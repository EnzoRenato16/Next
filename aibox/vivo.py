"""A imagem ao vivo da AIBOX, servida por ela mesma.

POR QUE ISTO EXISTE. Sem imagem, ninguem confia no que o sistema diz — e com
razao: "3 corpos" numa linha de texto pode ser tres pessoas ou tres cadeiras.
Esta pagina mostra O QUE A CAIXA ESTA VENDO, com os pontos que ela usou para
decidir desenhados por cima. Quem assiste pode discordar na hora.

NAO e a Sala do navegador. A Sala usa a webcam do PC e faz a analise nela; aqui
a analise ja aconteceu na caixa, e o que viaja e so o resultado desenhado. Dois
sistemas olhando a mesma sala dariam duas respostas diferentes, e a apresentacao
nao teria como dizer qual e a do projeto.

MJPEG e de proposito, em vez de algo mais moderno: e uma sequencia de fotos num
cano HTTP, funciona em qualquer navegador sem biblioteca, sem plugin e sem
negociacao. Numa rede de laboratorio na vespera da entrega, essa chatice toda e
exatamente o que nao se quer.

O ENCODE SO ACONTECE COM ALGUEM OLHANDO. Sem cliente conectado a analise nao
paga nada por esta janela — e detectar queda e mais importante que exibi-la.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Ligacoes do esqueleto COCO-17: ombro-cotovelo-punho dos dois lados, o tronco,
# e quadril-joelho-tornozelo. E o mesmo corpo que a rede enxerga.
OSSOS = ((5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
         (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4))

VERDE = (160, 191, 95)      # BGR do verde da marca
RUBI = (90, 90, 230)
BRANCO = (240, 240, 240)

PAGINA = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auditix IA na AIBOX</title><style>
:root{color-scheme:dark;--verde:#5FBFA0;--fundo:#0C1512;--caixa:#16302A;
      --linha:#2C5A4C;--texto:#E3F2EC;--fraco:#8FB3A7}
*{box-sizing:border-box}
body{margin:0;background:var(--fundo);color:var(--texto);
     font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
       padding:18px 20px;border-bottom:1px solid var(--linha)}
h1{margin:0;font-size:21px;letter-spacing:-.3px}
h1 i{font-style:normal;color:var(--verde)}
nav{margin-left:auto;display:flex;gap:16px}
nav a{color:var(--verde);font-size:14px;text-decoration:none}
nav a:hover{text-decoration:underline}
.sub{color:var(--fraco);font-size:12px;letter-spacing:.14em;text-transform:uppercase}
main{padding:20px;max-width:1100px;margin:0 auto}
.palco{position:relative;background:#000;border:1px solid var(--linha);
       border-radius:12px;overflow:hidden;line-height:0}
.palco img{width:100%;height:auto;display:block}
.nums{display:grid;gap:10px;margin-top:16px;
      grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.n{background:var(--caixa);border:1px solid var(--linha);border-radius:10px;padding:12px 14px}
.n b{display:block;font-size:23px;font-variant-numeric:tabular-nums;color:var(--verde)}
.n span{color:var(--fraco);font-size:11.5px;letter-spacing:.09em;text-transform:uppercase}
.nota{margin-top:16px;color:var(--fraco);font-size:13.5px;max-width:70ch}
.morto{color:#E08A9B}
</style>
<header>
  <h1>Audit<i>ix</i> IA</h1>
  <span class="sub">ao vivo, direto da AIBOX</span>
  <nav id="atalhos"></nav>
</header>
<main>
  <div class="palco"><img src="/video" alt="imagem ao vivo da camera da sala"></div>
  <div class="nums">
    <div class="n"><b id="fps">--</b><span>quadros/s</span></div>
    <div class="n"><b id="rede">--</b><span>modelo (ms)</span></div>
    <div class="n"><b id="analise">--</b><span>analise (ms)</span></div>
    <div class="n"><b id="cpu">--</b><span>cpu</span></div>
    <div class="n"><b id="ram">--</b><span>ram (MB)</span></div>
    <div class="n"><b id="corpos">--</b><span>pessoas</span></div>
    <div class="n"><b id="alertas">--</b><span>alertas enviados</span></div>
    <div class="n"><b id="perdidos">--</b><span>nao chegaram</span></div>
  </div>
  <p class="nota">Os pontos e as linhas sao os 17 pontos do corpo que o modelo
  devolveu <b>e que a analise realmente usou</b> — nao uma ilustracao. Uma
  pessoa fica <b>vermelha</b> enquanto o relogio de queda esta armado.</p>
</main>
<script>
const $ = i => document.getElementById(i);
setInterval(async () => {
  try{
    const e = await (await fetch('/estado')).json();
    $('fps').textContent = e.fps.toFixed(1);
    $('rede').textContent = Math.round(e.rede);
    $('analise').textContent = e.analise.toFixed(1);
    $('cpu').textContent = Math.round(e.cpu) + '%';
    $('ram').textContent = Math.round(e.ram);
    $('corpos').textContent = e.corpos;
    $('alertas').textContent = e.enviados;
    /* O QUE NAO CHEGOU FICA NA CARA. Um enviador que erra calado e
       indistinguivel de um que funciona: o painel ficaria vazio e ninguem
       saberia se e porque nada aconteceu ou porque nada chegou. */
    $('perdidos').textContent = e.falhas;
    $('perdidos').style.color = e.falhas ? '#ff6b6b' : '';
    /* Os atalhos apontam para o SERVIDOR, que roda noutra maquina — a caixa so
       enxerga e avisa. O endereco vem do .env pelo /estado, e nao escrito na
       pagina, porque numa outra instalacao o servidor tem outro IP. */
    if(e.servidor && !$('atalhos').dataset.pronto){
      $('atalhos').dataset.pronto = '1';
      $('atalhos').innerHTML =
        '<a href="' + e.servidor + '/cadastro">Cadastrar rosto</a>' +
        '<a href="' + e.servidor + '/painel">Painel de eventos</a>';
    }
    document.body.classList.remove('morto');
  }catch(_){ document.body.classList.add('morto'); }
}, 1000);
</script>
""".encode("utf-8")   # a pagina tem acento; bytes literal so aceita ASCII


class Vivo:
    """Guarda o ultimo quadro e os numeros, e serve os dois por HTTP."""

    def __init__(self, porta):
        self.porta = porta
        self.jpeg = None
        self.estado = dict(fps=0.0, rede=0.0, analise=0.0, cpu=0.0,
                           ram=0.0, corpos=0, enviados=0, falhas=0,
                           servidor="")
        self.clientes = 0
        self._trava = threading.Lock()
        self._srv = ThreadingHTTPServer(("0.0.0.0", porta), _fabricar(self))
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()

    def publicar(self, jpeg, estado):
        with self._trava:
            self.jpeg = jpeg
            self.estado.update(estado)

    def pegar(self):
        with self._trava:
            return self.jpeg

    def fechar(self):
        try:
            self._srv.shutdown()
        except Exception:
            pass


def _fabricar(vivo):
    class Mao(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            """Calado. O log do laco e o que importa nesta janela, e uma linha
            por quadro do MJPEG esconderia qualquer alerta de queda."""

        def do_GET(self):
            if self.path.startswith("/video"):
                return self._video()
            if self.path.startswith("/estado"):
                with vivo._trava:
                    corpo = json.dumps(vivo.estado).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(corpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return self.wfile.write(corpo)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGINA)))
            self.end_headers()
            self.wfile.write(PAGINA)

        def _video(self):
            import time
            # HTTP/1.0 e `Connection: close` nesta rota, e so nesta: um fluxo
            # sem fim nao tem Content-Length, e em HTTP/1.1 isso obriga
            # chunked — que o BaseHTTPRequestHandler nao faz sozinho. O
            # resultado seria um cano aberto que o cliente nunca le.
            self.protocol_version = "HTTP/1.0"
            self.send_response(200)
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=quadro")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            vivo.clientes += 1
            ultimo = None
            try:
                while True:
                    q = vivo.pegar()
                    # `is` e nao `==`: comparar dois JPEGs byte a byte a cada
                    # volta custaria mais que enviar o quadro.
                    if q is None or q is ultimo:
                        time.sleep(0.02)
                        continue
                    ultimo = q
                    self.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: " + str(len(q)).encode() +
                                     b"\r\n\r\n" + q + b"\r\n")
            except Exception:
                pass            # o navegador fechou a aba; nao e erro
            finally:
                vivo.clientes = max(0, vivo.clientes - 1)
    return Mao


def desenhar(cv2, img, trilhas, conf_min=0.30):
    """O esqueleto por cima do quadro. Vermelho = relogio de queda armado."""
    alt, larg = img.shape[:2]
    for t in trilhas:
        kp = getattr(t, "_kp", None)
        if not kp:
            continue
        cor = RUBI if t.quedaDesde else VERDE
        px = [(int(p[0] * larg), int(p[1] * alt), p[2]) for p in kp]
        for a, b in OSSOS:
            if px[a][2] >= conf_min and px[b][2] >= conf_min:
                cv2.line(img, px[a][:2], px[b][:2], cor, 2, cv2.LINE_AA)
        for p in px:
            if p[2] >= conf_min:
                cv2.circle(img, p[:2], 3, BRANCO, -1, cv2.LINE_AA)
        cx = getattr(t, "caixa", None)
        if cx:
            x0, y0 = int(cx[0] * larg), int(cx[1] * alt)
            x1, y1 = int(cx[2] * larg), int(cx[3] * alt)
            cv2.rectangle(img, (x0, y0), (x1, y1), cor, 1, cv2.LINE_AA)
            # A nota da rede fica na etiqueta de proposito: e o numero que
            # decide, e quem assiste tem de poder ver que ele NAO estourou o
            # limiar quando o sistema fica calado.
            etiq = f"#{t.id}  {t.notaQueda:.2f}"
            cv2.putText(img, etiq, (x0, max(12, y0 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, cor, 1, cv2.LINE_AA)
    return img
