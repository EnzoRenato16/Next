"""Cadastrar rostos a partir de fotos, sem precisar da camera.

  python aibox/cadastrar_fotos.py fotos-cadastro
  python aibox/cadastrar_fotos.py fotos-cadastro --conferir      # so olha, nao manda
  python aibox/cadastrar_fotos.py fotos-cadastro/enzo --nome "Enzo Renato"
  python aibox/cadastrar_fotos.py fotos-cadastro --galeria arena/galeria.json

COM --galeria, nao fala com servidor nenhum: grava os numeros num arquivo que
vai para a AIBOX e e o que o modo arena le (ver aibox/galeria.py e
aibox/arena.py). E o caminho para o NEXT, onde a caixa compara sozinha.

Uma subpasta por pessoa, e o nome da pasta vira o nome do cadastro:

  fotos-cadastro/
    Enzo Renato/   frente.jpg  sorrindo.jpg  esquerda.jpg  direita.jpg  de-cima.jpg
    Matheus Porto/ ...

POR QUE EXISTE. O grupo precisa chegar na final ja cadastrado, e nao ha tempo de
cadastrar no dia. Foto boa de celular, de perto e com luz, da um cadastro melhor
que a camera do alto da sala. Os 128 numeros saem do MESMO motor que reconhece na
caixa (YuNet + SFace, de daten/), e vao como tipo "sface": e o cadastro que a
caixa usa, nao o do navegador.

RODA NO PC, onde estao as fotos e o servidor. As fotos nunca saem do PC: daqui
para o servidor vao so os numeros, que ele gira com a chave antes de gravar.
Nada e gravado em disco por este script. Depois de cadastrar, apague as fotos;
e a pasta fotos-cadastro/ esta no .gitignore, porque o repositorio e publico.

JUNTAR COM A CAMERA DA SALA. Cadastrar o mesmo nome de novo SUBSTITUI. Para somar
as fotos com uma passada pela camera (ou o contrario), use --acrescentar aqui, ou
deixe marcado "Juntar" na tela /cadastro, ou rode `cadastrar.py --acrescentar`.

Precisa de opencv-python e numpy no Python do PC:  pip install opencv-python numpy
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

EXTENSOES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# Foto de celular tem 12 MP. O YuNet acha rosto grande sem precisar de tudo
# isso, e o SFace recorta 112x112 no fim: reduzir para este lado maior so tira
# tempo, nao qualidade.
LADO_MAX = 1600
# Rosto menor que isto (largura, em pixels, ja reduzido) da um cadastro pobre.
ROSTO_MIN_PX = 80
# Por pessoa: menos que isso nao cadastra; mais que isso o servidor recusa num
# envio so (CADASTRO_MAX no servidor.py).
MINIMO, MAXIMO = 3, 12
# Uma foto cujo rosto fica longe das outras da mesma pasta provavelmente e de
# outra pessoa. Cadastrar a pessoa errada e o erro que ninguem percebe depois:
# o nome fica certo e a cara e de outro.
DESTOA = 0.25
# A arena exige 0,05 de folga sobre o segundo nome (ARENA_MARGEM).
FOLGA_MIN = 0.05


def ler(caminho):
    """Le a imagem. imdecode em vez de imread porque o imread do Windows nao
    abre caminho com acento (e "Gonçalves" esta no grupo)."""
    import cv2
    dados = np.fromfile(caminho, dtype=np.uint8)
    img = cv2.imdecode(dados, cv2.IMREAD_COLOR) if dados.size else None
    if img is None:
        return None
    alt, larg = img.shape[:2]
    escala = LADO_MAX / max(alt, larg)
    if escala < 1:
        img = cv2.resize(img, (int(larg * escala), int(alt * escala)),
                         interpolation=cv2.INTER_AREA)
    return img


def em_pe(linha):
    """O rosto esta de pe? Olhos lado a lado (mais distantes em x que em y) e
    acima do nariz. Colunas do YuNet: 4-5 olho direito, 6-7 olho esquerdo,
    8-9 nariz."""
    dx = abs(float(linha[6]) - float(linha[4]))
    dy = abs(float(linha[7]) - float(linha[5]))
    olhos_y = (float(linha[5]) + float(linha[7])) / 2
    return dx > dy and olhos_y < float(linha[9])


def medir(motor, img):
    """Devolve (vetor, None) ou (None, motivo).

    GIRA A FOTO E FICA COM O GIRO EM QUE O ROSTO E MAIS ROSTO. Celular as vezes
    grava a foto deitada e so marca o giro no EXIF. Ficar com o primeiro giro
    que acha rosto nao serve: visto no teste, o YuNet acha rosto tambem na foto
    de cabeca para baixo, com os pontos dos olhos no lugar errado, e o vetor sai
    diferente das outras fotos da mesma pessoa. De pe, a nota dele e maior
    (0,91 contra 0,74 de cabeca para baixo, na mesma foto)."""
    import cv2
    melhor = None
    for giro in (None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE,
                 cv2.ROTATE_180):
        quadro = img if giro is None else cv2.rotate(img, giro)
        linhas = motor.detect(quadro, full_res=True)
        if len(linhas) == 0:
            continue
        nota = max(float(l[14]) for l in linhas)
        if melhor is None or nota > melhor[0]:
            melhor = (nota, quadro, linhas)
    if melhor is None:
        return None, "nenhum rosto encontrado (de lado demais, escuro ou tampado?)"
    _, quadro, linhas = melhor
    if len(linhas) > 1:
        return None, f"{len(linhas)} rostos na foto (precisa ser um so)"
    if not em_pe(linhas[0]):
        return None, "rosto torto demais (cabeca muito inclinada ou de lado)"
    if float(linhas[0][2]) < ROSTO_MIN_PX:
        return None, f"rosto pequeno ({int(linhas[0][2])} px), tire mais de perto"
    return motor.embedding(quadro, linhas[0]), None


def unitario(v):
    return v / (np.linalg.norm(v) + 1e-9)


def separar_destoantes(vetores):
    """Indices das fotos que ficam longe da media das OUTRAS da mesma pessoa."""
    if len(vetores) < 3:
        return []
    u = np.array([unitario(v) for v in vetores])
    fora = []
    for i in range(len(u)):
        outros = unitario(np.delete(u, i, axis=0).mean(axis=0))
        if float(u[i] @ outros) < DESTOA:
            fora.append(i)
    return fora


def apontar_confusas(pessoas_lidas):
    """Qual FOTO se parece mais com outra pessoa do que com o proprio dono?

    Cada foto e comparada com as outras fotos do dono e com as de cada outra
    pessoa, pelo melhor par, como o juiz da arena faz. Foto com folga menor
    que FOLGA_MIN sai melhor da galeria: alem de confundir o dono, ela puxa
    a leitura do OUTRO para o nome errado."""
    print("\n== fotos que confundem (cada uma contra as outras pastas)")
    u = [(n, o, [unitario(v) for v in vs]) for n, o, vs in pessoas_lidas]
    achou = 0
    for i, (nome, origem, vs) in enumerate(u):
        for k, v in enumerate(vs):
            proprio = max((float(v @ w) for j, w in enumerate(vs) if j != k), default=-1)
            rival, nota_rival = None, -1.0
            for i2, (n2, _, vs2) in enumerate(u):
                if i2 != i:
                    m = max(float(v @ w) for w in vs2)
                    if m > nota_rival:
                        rival, nota_rival = n2, m
            if proprio - nota_rival < FOLGA_MIN:
                achou += 1
                print(f"   ! {nome}/{origem[k]}: {proprio:.2f} com as fotos dele, "
                      f"{nota_rival:.2f} com {rival}. Tire esta foto da pasta.")
    if not achou:
        print("   nenhuma: toda foto fica mais perto do dono, com folga")


def mandar(base, nome, vetores, acrescentar):
    pedido = {"nome": nome, "tipo": "sface", "descritores": vetores}
    if acrescentar:
        pedido["acrescentar"] = True
    req = urllib.request.Request(
        base.rstrip("/") + "/api/cadastro", data=json.dumps(pedido).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"erro": f"{e.code} {e.read().decode('utf-8', 'replace')[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)}


def pessoas(pasta, nome):
    """[(nome, [arquivos])]. Com --nome, a pasta e de uma pessoa so."""
    def fotos(d):
        return sorted(os.path.join(d, f) for f in os.listdir(d)
                      if os.path.splitext(f)[1].lower() in EXTENSOES)
    if nome:
        return [(nome.strip(), fotos(pasta))]
    saida = []
    for d in sorted(os.listdir(pasta)):
        caminho = os.path.join(pasta, d)
        if os.path.isdir(caminho):
            saida.append((d.strip(), fotos(caminho)))
    return saida


def main():
    p = argparse.ArgumentParser(description="Cadastrar rostos a partir de fotos")
    p.add_argument("pasta", nargs="?", default=os.path.join(RAIZ, "fotos-cadastro"))
    p.add_argument("--nome", help="a pasta e de uma pessoa so, com este nome")
    p.add_argument("--servidor",
                   default=os.environ.get("SERVIDOR", "http://127.0.0.1:8000"))
    p.add_argument("--acrescentar", action="store_true",
                   help="junta com as amostras que a pessoa ja tem em vez de substituir")
    p.add_argument("--conferir", action="store_true",
                   help="so confere as fotos, nao manda nada para o servidor")
    p.add_argument("--galeria", metavar="ARQUIVO",
                   help="grava no arquivo da arena em vez de mandar ao servidor")
    a = p.parse_args()

    if not os.path.isdir(a.pasta):
        print(f"[fotos] a pasta {a.pasta} nao existe.")
        return 2
    lista = pessoas(a.pasta, a.nome)
    if not lista:
        print(f"[fotos] nenhuma subpasta de pessoa em {a.pasta}.")
        return 2

    from daten.app.recognizer import FaceEngine
    motor = FaceEngine()

    falhou = 0
    conferidos = []                          # (nome, [arquivo], [vetor])
    for nome, arquivos in lista:
        print(f"\n== {nome}: {len(arquivos)} foto(s)")
        vetores, origem = [], []
        for arq in arquivos:
            img = ler(arq)
            if img is None:
                print(f"   - {os.path.basename(arq)}: nao abriu (se for HEIC do "
                      "iPhone, exporte como JPG)")
                continue
            v, motivo = medir(motor, img)
            del img
            if v is None:
                print(f"   - {os.path.basename(arq)}: {motivo}")
                continue
            vetores.append(v)
            origem.append(os.path.basename(arq))
            print(f"   + {os.path.basename(arq)}")

        for i in reversed(separar_destoantes(vetores)):
            print(f"   ! {origem[i]}: o rosto destoa das outras fotos desta pasta "
                  "(e de outra pessoa?). Fica de fora.")
            del vetores[i], origem[i]

        if len(vetores) > MAXIMO:
            print(f"   ({len(vetores)} fotos boas; vao as {MAXIMO} primeiras)")
            vetores = vetores[:MAXIMO]
        if len(vetores) < MINIMO:
            print(f"   NAO CADASTRADO: so {len(vetores)} foto(s) boa(s), "
                  f"precisa de {MINIMO}.")
            falhou += 1
            continue
        if a.conferir:
            print(f"   ok: {len(vetores)} fotos boas (nada foi mandado, --conferir)")
            conferidos.append((nome, origem, vetores))
            continue

        if a.galeria:
            from aibox import galeria
            try:
                total = galeria.gravar(nome, [[float(x) for x in v] for v in vetores],
                                       a.acrescentar, a.galeria)
                print(f"   NA GALERIA: {nome}, {total} amostras no total ({a.galeria}).")
            except ValueError as e:
                print(f"   NAO GRAVEI: {e}")
                falhou += 1
            continue
        r = mandar(a.servidor, nome, [[float(x) for x in v] for v in vetores],
                   a.acrescentar)
        if r.get("erro"):
            print(f"   O SERVIDOR RECUSOU: {r['erro']}")
            falhou += 1
        else:
            print(f"   CADASTRADO: {r['nome']}, {r['amostras']} amostras no total, "
                  f"tipo {r['tipo']}, vence em {r['vence']}.")

    if a.conferir and len(conferidos) > 1:
        apontar_confusas(conferidos)
    if not a.conferir:
        print("\nAs fotos continuam na pasta. Depois de conferir que todo mundo foi "
              "reconhecido, apague-as: o sistema so precisa dos numeros.")
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
