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
So o motor SFace (o da caixa): o do navegador mede outra coisa (ver
"DOIS MOTORES QUE NAO SE FALAM" no CLAUDE.md).
"""
import json
import os

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PADRAO = os.environ.get("GALERIA") or os.path.join(RAIZ, "arena", "galeria.json")
# Por pessoa. Mais amostras so deixa a comparacao mais lenta sem ganho: o que
# ajuda e variedade de angulo, e 24 cobre fotos e uma passada pela camera.
MAX_POR_PESSOA = 24


def ler(caminho=PADRAO):
    if not os.path.exists(caminho):
        return {"motor": "sface", "pessoas": {}}
    with open(caminho, encoding="utf-8") as f:
        dados = json.load(f)
    if dados.get("motor") != "sface":
        raise ValueError(f"{caminho}: motor {dados.get('motor')!r}, esperado 'sface'")
    return dados


def gravar(nome, vetores, acrescentar=False, caminho=PADRAO):
    """Grava as amostras de uma pessoa. Sem acrescentar, substitui as que ela
    tinha (o mesmo jeito do /api/cadastro). Devolve o total dela."""
    nome = nome.strip()
    if not nome:
        raise ValueError("nome vazio")
    for v in vetores:
        if len(v) != 128:
            raise ValueError(f"vetor com {len(v)} numeros; o esperado e 128")
    dados = ler(caminho)
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
    pessoas = ler(caminho)["pessoas"]
    nomes = sorted(pessoas)
    linhas, dono = [], []
    for i, n in enumerate(nomes):
        for v in pessoas[n]:
            linhas.append(v)
            dono.append(i)
    if not linhas:
        return nomes, np.empty((0, 128), np.float32), np.empty(0, int)
    M = np.asarray(linhas, np.float32)
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
    return nomes, M, np.asarray(dono, int)


if __name__ == "__main__":
    # $P aibox/galeria.py                   lista quem esta autorizado
    # $P aibox/galeria.py remover "Nome"    tira uma pessoa
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "remover":
        print("removido" if remover(sys.argv[2]) else "nao achei esse nome")
        sys.exit(0)
    pessoas = ler()["pessoas"]
    print(f"{PADRAO}: {len(pessoas)} pessoa(s) autorizada(s)")
    for n in sorted(pessoas):
        print(f"  {n}: {len(pessoas[n])} amostras")
