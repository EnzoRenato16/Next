"""A galeria da arena: quem esta autorizado, num arquivo da propria AIBOX.

POR QUE EXISTE, SE O SISTEMA JA TEM CADASTRO NO SERVIDOR. Na arena do NEXT o
notebook so pode ser terminal (SSH e tela), o processamento tem de estar na
caixa, e o setup inteiro cabe em uns dois minutos, numa rede que nao e a do
laboratorio. Depender do servidor do PC ali seria depender de IP fixo, de
firewall e de mais um programa no ar. Por isso a arena compara na caixa, contra
este arquivo.

O QUE ISSO CUSTA, DITO NA CARA. No sistema da escola a caixa nunca tem o
cadastro na mao (ver CLAUDE.md, "Rosto na caixa"). Aqui tem: os 128 numeros de
cada autorizado ficam em arena/galeria.json. Nenhuma foto, so os numeros, de
pessoas que consentiram, e o arquivo deve ser apagado depois do evento. A pasta
arena/ esta no .gitignore.

FORMATO:  {"motor": "sface", "pessoas": {"Nome": [[128 numeros], ...]}}
O motor e "sface" (128 numeros, o padrao) ou "arcface" (512, ver
aibox/arcface.py), e a galeria inteira e de um motor so: a arena le o motor
daqui e mede com ele. O do navegador (faceapi) nunca entra (ver "DOIS MOTORES
QUE NAO SE FALAM" no CLAUDE.md).
"""
import json
import os

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PADRAO = os.environ.get("GALERIA") or os.path.join(RAIZ, "arena", "galeria.json")
# Por pessoa. Mais amostras so deixa a comparacao mais lenta sem ganho: o que
# ajuda e variedade de angulo, e 24 cobre fotos e uma passada pela camera.
# 36 desde 24/10: fotos tiradas NO LOCAL do evento (a luz de la) entram por
# cima das 24 de antes. GALERIA_MAX no ambiente muda.
MAX_POR_PESSOA = int(os.environ.get("GALERIA_MAX", "36"))
DIM = {"sface": 128, "arcface": 512}


def ler(caminho=PADRAO):
    if not os.path.exists(caminho):
        return {"motor": "sface", "pessoas": {}}
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("motor") not in DIM:
        raise ValueError(f"{caminho}: motor {dados.get('motor')!r}, esperado "
                         "'sface' ou 'arcface'")
    return dados


def motor_de(caminho=PADRAO, padrao="sface"):
    """O motor da galeria; o `padrao` vale para galeria vazia ou que nao existe."""
    dados = ler(caminho)
    return dados["motor"] if dados["pessoas"] else padrao


def gravar(nome, vetores, acrescentar=False, caminho=PADRAO, motor=None):
    """Grava as amostras de uma pessoa. Sem acrescentar, substitui as que ela
    tinha (o mesmo jeito do /api/cadastro). Devolve o total dela.

    `motor` diz com qual modelo os vetores foram medidos. Galeria que ja tem
    gente de OUTRO motor recusa: misturar da ruido sem erro nenhum."""
    nome = nome.strip()
    if not nome:
        raise ValueError("nome vazio")
    dados = ler(caminho)
    motor = motor or dados["motor"]
    if motor not in DIM:
        raise ValueError(f"motor desconhecido: {motor!r}")
    if dados["pessoas"] and dados["motor"] != motor:
        raise ValueError(f"a galeria {caminho} e do motor {dados['motor']}, e estes "
                         f"numeros sao do {motor}. Use outro arquivo, ou apague este.")
    dados["motor"] = motor
    for v in vetores:
        if len(v) != DIM[motor]:
            raise ValueError(f"vetor com {len(v)} numeros; o {motor} da {DIM[motor]}")
    antes = dados["pessoas"].get(nome, []) if acrescentar else []
    juntos = antes + [[float(x) for x in v] for v in vetores]
    if len(juntos) > MAX_POR_PESSOA:
        raise ValueError(f"{nome} ficaria com {len(juntos)} amostras; "
                         f"o maximo e {MAX_POR_PESSOA}")
    dados["pessoas"][nome] = juntos
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    # Escreve noutro arquivo e troca: um Ctrl+C no meio nao deixa a galeria
    # pela metade na vespera do evento.
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    os.replace(tmp, caminho)
    return len(juntos)


def remover(nome, caminho=PADRAO):
    dados = ler(caminho)
    if dados["pessoas"].pop(nome.strip(), None) is None:
        return False
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    os.replace(tmp, caminho)
    return True


def matriz(caminho=PADRAO):
    """(nomes, M, dono): M tem uma linha por amostra, ja com tamanho 1, e
    dono[i] diz de quem e a linha i. Pronto para comparar por cosseno."""
    dados = ler(caminho)
    pessoas = dados["pessoas"]
    nomes = sorted(pessoas)
    linhas, dono = [], []
    for i, n in enumerate(nomes):
        for v in pessoas[n]:
            linhas.append(v)
            dono.append(i)
    if not linhas:
        return nomes, np.empty((0, DIM[dados["motor"]]), np.float32), np.empty(0, int)
    M = np.asarray(linhas, np.float32)
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    return nomes, M, np.asarray(dono, int)


def conferir(caminho=PADRAO):
    """Quanto cada autorizado se parece com ele mesmo e com os outros.

    O perigo que isto procura: dois do grupo parecidos demais entre si. Na
    arena o juiz exige folga de MARGEM sobre o segundo nome, e com dois
    parecidos essa folga nao aparece: a pessoa fica em "analisando" e nao e
    autorizada. Melhor descobrir aqui, com tempo de juntar mais fotos."""
    nomes, M, dono = matriz(caminho)
    if len(nomes) == 0:
        print("galeria vazia")
        return
    S = M @ M.T
    print("mesma pessoa (media entre as fotos dela; quanto MAIOR, melhor):")
    for i, n in enumerate(nomes):
        idx = np.where(dono == i)[0]
        bloco = S[np.ix_(idx, idx)]
        k = len(idx)
        media = (bloco.sum() - k) / max(1, k * k - k)
        aviso = "   <- fotos muito diferentes entre si" if media < 0.45 else ""
        print(f"  {n:20s} {media:.2f}  ({k} amostras){aviso}")
    print("\nentre pessoas (o mais parecido de cada par; quanto MENOR, melhor):")
    pior = 0.0
    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            a = np.where(dono == i)[0]
            b = np.where(dono == j)[0]
            maior = float(S[np.ix_(a, b)].max())
            pior = max(pior, maior)
            media = float(S[np.ix_(a, b)].mean())
            aviso = "   <- parecidos: ver o teste abaixo" if maior >= 0.30 else ""
            print(f"  {nomes[i]} x {nomes[j]}: pior {maior:.2f}, media {media:.2f}{aviso}")
    print(f"\no par mais parecido da {pior:.2f} no pior caso (uma foto contra uma "
          "foto). O pior caso assusta mais do que pesa: o juiz compara a leitura "
          "com TODAS as fotos de cada pessoa, e o teste abaixo faz isso.")

    # O TESTE QUE IMPORTA: cada foto faz o papel de uma leitura da camera, e e
    # comparada com a galeria SEM ela mesma, do jeito que o juiz compara (o
    # melhor de cada pessoa). Acertou o dono, e com quanta folga sobre o
    # segundo nome? Foto e melhor que a camera da sala, entao isto e o teto:
    # se aqui ja confunde, na sala confunde mais.
    print("\ncada foto contra a galeria sem ela (como o juiz faz na arena):")
    problemas = 0
    for i, n in enumerate(nomes):
        idx = np.where(dono == i)[0]
        if len(idx) < 2:
            continue
        certas, folgas, rivais = 0, [], {}
        for k in idx:
            notas = np.full(len(nomes), -1.0)
            for j in range(len(nomes)):
                outras = [x for x in np.where(dono == j)[0] if x != k]
                if outras:
                    notas[j] = float(S[k, outras].max())
            ordem = np.argsort(notas)[::-1]
            if ordem[0] == i:
                certas += 1
            folga = notas[i] - max(notas[x] for x in range(len(nomes)) if x != i)
            folgas.append(folga)
            r = nomes[int(ordem[1] if ordem[0] == i else ordem[0])]
            rivais[r] = rivais.get(r, 0) + 1
        menor = min(folgas)
        rival = max(rivais, key=rivais.get)
        aviso = ""
        if certas < len(idx) or menor < 0.05:
            aviso = "   <- ATENCAO"
            problemas += 1
        print(f"  {n:20s} acertou {certas} de {len(idx)}, menor folga {menor:+.2f}, "
              f"folga media {np.mean(folgas):+.2f} (rival: {rival}){aviso}")
    print("\nconclusao: " + (
        "toda foto escolhe o dono com folga. A galeria separa bem o grupo; o "
        "resto e calibrar o limiar na camera da caixa." if not problemas else
        f"{problemas} pessoa(s) com foto que confunde ou com folga menor que 0,05. "
        "Junte fotos mais variadas (angulos, luz, outro lugar) dessas pessoas."))


if __name__ == "__main__":
    # $P aibox/galeria.py                   lista quem esta autorizado
    # $P aibox/galeria.py remover "Nome"    tira uma pessoa
    # $P aibox/galeria.py conferir          o grupo se parece entre si?
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "remover":
        print("removido" if remover(sys.argv[2]) else "nao achei esse nome")
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "conferir":
        conferir(sys.argv[2] if len(sys.argv) > 2 else PADRAO)
        sys.exit(0)
    dados = ler()
    pessoas = dados["pessoas"]
    print(f"{PADRAO}: {len(pessoas)} pessoa(s) autorizada(s), motor {dados['motor']}")
    for n in sorted(pessoas):
        print(f"  {n}: {len(pessoas[n])} amostras")
