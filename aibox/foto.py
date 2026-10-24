"""A foto do instante do alerta, com a cabeca de TODO MUNDO em mosaico.

A caixa nunca mandava imagem: so os pontos do corpo (aibox/trilhas.py). Isso
basta para auditar uma queda, e e o certo numa escola. Mas com a analise
rodando no PC de quem apresenta, com a camera do proprio grupo, o pedido foi
ver a cena de verdade — e ai a regra do navegador vale igual: a imagem so sai
com a cabeca coberta.

O MOSAICO E O MESMO DO NAVEGADOR, pelo mesmo motivo: reduzir pela metade ate
caber em quatro blocos, e nao desfocar. Desfoque deixa reconhecer.

A cabeca vem dos PONTOS que o YOLO ja mediu (nariz, olhos, orelhas), com a
largura dos ombros de piso: nenhum detector novo, nenhum custo a mais. Sem
cabeca medida nao ha o que cobrir, e entao NAO sai foto — falhar fechado.
"""
import base64

LADO = 640          # maior lado da imagem guardada
BLOCOS = 4          # quantos quadrados atravessam a cabeca
NARIZ, OLHO_E, OLHO_D, ORELHA_E, ORELHA_D = 0, 1, 2, 3, 4
OMBRO_E, OMBRO_D = 5, 6
CONF_MIN = 0.30


def caixa_da_cabeca(kp, larg, alt):
    """(x, y, w, h) em pixels, ou None quando nenhum ponto da cabeca foi visto."""
    pts = [kp[i] for i in (NARIZ, OLHO_E, OLHO_D, ORELHA_E, ORELHA_D)
           if kp[i][2] >= CONF_MIN]
    if not pts:
        return None
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d = max(x1 - x0, y1 - y0)
    oe, od = kp[OMBRO_E], kp[OMBRO_D]
    if oe[2] >= CONF_MIN and od[2] >= CONF_MIN:
        # Com um ponto so (nariz de costas) a caixa tem tamanho zero; o ombro a
        # ombro da a escala, e a cabeca mede perto da metade dele.
        d = max(d, ((oe[0] - od[0]) ** 2 + (oe[1] - od[1]) ** 2) ** 0.5 * 0.5)
    d = max(d, 0.04)
    # Os pontos vao de orelha a orelha e param na boca: falta cabelo em cima e
    # queixo embaixo, e os dois identificam.
    rx, ry = d * 0.62, d * 0.78
    return ((cx - rx) * larg, (cy - ry) * alt, 2 * rx * larg, 2 * ry * alt)


def _apagar(cv2, img, x, y, w, h):
    pedaco = img[y:y + h, x:x + w]
    if pedaco.size == 0:
        return
    # Reduz PELA METADE de cada vez: de uma vez so o resize amostra em vez de
    # fazer media, e amostrar PRESERVA o detalhe fino em vez de destrui-lo.
    pw, ph = w, h
    while pw > BLOCOS * 2 and ph > BLOCOS * 2:
        pw, ph = max(BLOCOS, pw // 2), max(BLOCOS, ph // 2)
        pedaco = cv2.resize(pedaco, (pw, ph), interpolation=cv2.INTER_AREA)
    pequeno = cv2.resize(pedaco, (BLOCOS, BLOCOS), interpolation=cv2.INTER_AREA)
    img[y:y + h, x:x + w] = cv2.resize(pequeno, (w, h),
                                       interpolation=cv2.INTER_NEAREST)


def _reduzir(cv2, img, lado):
    a, l = img.shape[:2]
    k = min(1.0, lado / max(l, a))
    return (cv2.resize(img, (max(1, int(l * k)), max(1, int(a * k))),
                       interpolation=cv2.INTER_AREA) if k < 1 else img.copy())


def _cobrir(cv2, tela, kps):
    """Poe em mosaico a cabeca de cada corpo de `kps`. Devolve quantas cobriu."""
    A, L = tela.shape[:2]
    cabecas = 0
    for kp in kps:
        if not kp:
            continue
        b = caixa_da_cabeca(kp, L, A)
        if not b:
            continue
        x, y = int(max(0, b[0])), int(max(0, b[1]))
        w, h = int(min(L, b[0] + b[2])) - x, int(min(A, b[1] + b[3])) - y
        if w > 1 and h > 1:
            _apagar(cv2, tela, x, y, w, h)
            cabecas += 1
    return cabecas


def _moldura(cv2, tela, cx):
    # Uma moldura em quem disparou: numa sala com gente, quem abre a imagem
    # precisa saber para onde olhar.
    if cx:   # (x0, y0, x1, y1) de 0 a 1, como medidas.caixa devolve
        A, L = tela.shape[:2]
        cv2.rectangle(tela, (int(cx[0] * L), int(cx[1] * A)),
                      (int(cx[2] * L), int(cx[3] * A)), (46, 87, 228), max(2, L // 200))


def _jpeg(cv2, tela, qualidade):
    ok, buf = cv2.imencode(".jpg", tela, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    return ("data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
            if ok else None)


def do_alerta(cv2, img, kps, dono=None):
    """A data URL JPEG do quadro, com toda cabeca em mosaico, ou None.

    `kps` sao os corpos que o detector achou NESTE quadro (17 pontos
    normalizados cada); `dono` e a trilha de quem disparou, que ganha a
    moldura. O QUADRO INTEIRO, e nao o recorte da pessoa: um pedaco fechado
    mostra um corpo no chao e esconde o resto — se foi tropeco na mochila, se
    tem alguem junto.

    Os pontos sao os do DETECTOR, e nao os da trilha: a trilha so guarda
    pontos quando o corpo da para julgar (quadril a vista, longe da camera),
    e a queda decidida pela linha do chao, de corpo cortado, saia sem foto.
    """
    try:
        tela = _reduzir(cv2, img, LADO)
        if not _cobrir(cv2, tela, kps):
            # Nenhuma cabeca coberta: nada sai. A queda ja esta na cadeia.
            return None
        _moldura(cv2, tela, getattr(dono, "caixa", None) if dono is not None else None)
        return _jpeg(cv2, tela, 70)
    except Exception:
        # A queda ja esta gravada; so a imagem nao vai. Falhar fechado.
        return None


FILME_S = 10.0      # quantos segundos antes do alerta
FILME_FPS = 4.0     # quadros por segundo guardados
FILME_LADO = 480    # maior lado de cada quadro do filme


class Filme:
    """Os ultimos FILME_S segundos da camera, para ver o que levou ao alerta.

    Guarda o quadro REDUZIDO e os pontos que o detector achou nele, e so poe
    o mosaico na hora de mandar: borrar todo quadro custaria CPU a toa, porque
    quase nenhum vira filme. O que fica na memoria e o quadro cru — por isso
    ele nunca sai daqui sem passar por `filme()`, e some sozinho em FILME_S.
    """

    def __init__(self, cv2, segundos=FILME_S, fps=FILME_FPS):
        import collections
        self.cv2, self.segundos, self.passo = cv2, segundos, 1.0 / fps
        self.fps = fps
        self.quadros = collections.deque()
        self._ultimo = -1e9

    def guardar(self, img, kps, t):
        if t - self._ultimo < self.passo:
            return
        self._ultimo = t
        try:
            self.quadros.append((t, _reduzir(self.cv2, img, FILME_LADO),
                                 [list(k) for k in kps]))
        except Exception:
            return
        while self.quadros and t - self.quadros[0][0] > self.segundos:
            self.quadros.popleft()

    def filme(self):
        """Lista de data URLs JPEG, do mais velho ao do alerta, ou None.

        Quadro sem cabeca coberta fica de FORA, como na foto: o detector pode
        ter perdido alguem naquele instante, e entao ninguem garante que nao
        ha rosto inteiro nele. Falhar fechado, quadro a quadro.
        """
        saida = []
        for _, img, kps in list(self.quadros):
            try:
                tela = img.copy()
                if not _cobrir(self.cv2, tela, kps):
                    continue
                j = _jpeg(self.cv2, tela, 60)
                if j:
                    saida.append(j)
            except Exception:
                continue
        return saida or None
