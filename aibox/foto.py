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


def do_alerta(cv2, img, trilhas, dono=None):
    """A data URL JPEG do quadro, com toda cabeca em mosaico, ou None.

    `trilhas` sao as do quadro (precisam de `.kp`, os 17 pontos normalizados);
    `dono` e quem disparou o alerta, que ganha a moldura. O QUADRO INTEIRO, e
    nao o recorte da pessoa: um pedaco fechado mostra um corpo no chao e
    esconde o resto — se foi tropeco na mochila, se tem alguem junto.
    """
    try:
        a, l = img.shape[:2]
        k = min(1.0, LADO / max(l, a))
        tela = cv2.resize(img, (max(1, int(l * k)), max(1, int(a * k))),
                          interpolation=cv2.INTER_AREA) if k < 1 else img.copy()
        A, L = tela.shape[:2]

        cabecas = 0
        for t in trilhas:
            kp = getattr(t, "kp", None)
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
        if not cabecas:
            # Nenhuma cabeca coberta: nada sai. A queda ja esta na cadeia.
            return None

        # Uma moldura em quem disparou: numa sala com gente, quem abre a imagem
        # precisa saber para onde olhar.
        cx = getattr(dono, "caixa", None) if dono is not None else None
        if cx:   # (x0, y0, x1, y1) de 0 a 1, como medidas.caixa devolve
            p1 = (int(cx[0] * L), int(cx[1] * A))
            p2 = (int(cx[2] * L), int(cx[3] * A))
            cv2.rectangle(tela, p1, p2, (46, 87, 228), max(2, L // 200))

        ok, buf = cv2.imencode(".jpg", tela, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
    except Exception:
        # A queda ja esta gravada; so a imagem nao vai. Falhar fechado.
        return None
