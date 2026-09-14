# Rede de detecção de queda

Um classificador pequeno, treinado em quedas reais, que roda **dentro do
`auditix-sala.html`** — 113 pesos escritos no próprio arquivo. Nada para
baixar, nenhum runtime, nenhum CDN.

## Por que ele existe

A Sala detectava queda por regras geométricas. Medindo essas regras contra
4.509 clipes com esqueleto anotado:

| | precisão | revocação | F1 |
|---|---|---|---|
| regra geométrica | **100%** | **60%** | 0,75 |
| rede | 98% | **89%** | **0,94** |

A geometria **perde 4 de cada 10 quedas**, e isso não se conserta baixando
limiar: as quedas que ela perde não se parecem com as que ela pega — cair de
costas para a câmera, cair sobre um móvel, cair e ficar sentado.

As duas ficam no ar juntas. A geometria não errou **uma vez** nesses clipes;
descartá-la para ganhar revocação seria trocar uma coisa boa por outra.

## Os dados

**Fall Vision**, Harvard Dataverse, `doi:10.7910/DVN/75QPKK`, licença **CC0
1.0** (domínio público — sem restrição de uso, nem para produto).

Baixamos só os `*_keypoints_csv` (284 MB), não os vídeos (49 GB): o dataset já
traz os 17 pontos do esqueleto por quadro, e é disso que precisamos. Os 17
existem todos no MediaPipe que a Sala roda, o que é a razão de esse dataset
servir e não outro.

4.509 clipes aproveitados, 2.680 com queda.

## Taxa de quadros da camera

A rede foi treinada a 30fps. Camera IP domestica (Tapo C200/C210) entrega 15.
`treino/taxa.py` reextrai os MESMOS clipes de teste jogando fora quadros e
pontua com o modelo que ja esta no ar, sem retreinar:

| fps | AUC | precisao | revocacao | quedas perdidas (de 1.020) |
|---|---|---|---|---|
| 30 | 0,977 | 98% | **89%** | 55 |
| 15 | 0,972 | 99% | **87%** | 70 |
| 10 | 0,959 | 98% | 86% | 75 |

Ou seja: 15fps custa **2 pontos de revocacao**, nao a deteccao. As entradas que
dependem de tempo sao divididas pelo intervalo real entre quadros, e a Sala
mede o fps em vez de presumir — e por isso que a queda e pequena.

O que 15fps quase quebrou foi o codigo, nao o modelo: a janela exigia 15
amostras, e 15fps entrega ~15. Ver `QUEDA_AMOSTRAS` no `auditix-sala.html`.

## Fora do que o modelo viu

Um modelo nao avisa quando esta fora do seu mundo: responde com a mesma
convicção de sempre. Numa camera alta e inclinada, amarrar o cadarco marcou
**1,00** — o topo da escala — enquanto na base o alarme falso fica em 2 a 3%.
Nao e limiar mal escolhido: e vista que nao existia nos 4.509 clipes, todos
gravados na altura da pessoa.

Por isso a Sala mede, a cada janela, a distancia ao treino: o maior |z| entre
os 12 atributos. Acima de `QUEDA_FORA = 6`, a nota da rede e descartada e so a
geometria decide — ela nao aprendeu nada, so mede, e nao tem como extrapolar.

Custo medido na base: revocacao de 93,7% para 93,5%, com 0,6% das janelas
descartadas.

Isto **reduz** o estrago de uma camera mal posicionada; nao conserta. O jeito
de consertar continua sendo montar a camera de lado, como diz o CAMERA-IP.md.

## Treinar com a camera de voces

Os scripts declaram a propria dependencia (numpy), entao rodam com `uv run` e
ninguem precisa instalar Python separado — o `uv` que ja roda o servidor
resolve.

A base publica foi gravada noutro lugar, com outras camaras. A de voces ve
outra sala, de outra altura. Da para somar as duas:

1. Na Sala, escolha o rotulo ao lado do botao, clique **Gravar amostra**, faca
   a acao, clique **Parar e salvar**. Vale gravar ~10 quedas, ~10 corridas e
   uns 10 minutos de atividade normal.
2. `uv run treino/local.py` — mede e mostra, sem alterar nada.
3. `uv run treino/local.py --aplicar` — reescreve os pesos no
   `auditix-sala.html` e refaz `provas.json`.
4. `node testes/rede-queda.mjs` — confere que o JavaScript calcula o mesmo.

**Somar, nao trocar.** Um modelo so do quarto de voces acerta tudo no quarto de
voces e ninguem sabe o que faz na escola; um modelo so da base publica ja nos
mostrou o que faz num angulo que nunca viu. O script junta os dois e mede
separado: desempenho nos cenarios da base E nas gravacoes de voces.

O que e gravado sao **numeros do esqueleto ja normalizados** — nenhuma imagem,
nenhum rosto, nenhum nome. Fica em `treino/local/`, fora do git.

Duas armadilhas que o script evita, e que custaram divergencia no teste de
porte quando nao evitava: a janela e descrita pelo NUMERO DE AMOSTRAS (e assim
que a Sala chama a funcao, e nao pelo fps medido), e gravacoes com menos de 8
amostras por segundo sao descartadas, porque a Sala tambem as descarta.

## Mais dados melhoram? (treino/curva.py)

| clipes de treino | precisao | revocacao | F1 |
|---|---|---|---|
| 20 | 93% | 87% | 0,89 |
| 100 | 93% | 88% | 0,90 |
| 500 | 94% | 89% | 0,91 |
| 2.000 | 95% | 94% | 0,95 |
| 3.489 | 98% | 89% | 0,94 |

Com 20 clipes o modelo ja chega a 0,89; com 175 vezes mais dados, a 0,94. Sao
113 pesos — ele satura cedo. **Quantidade nao e a alavanca.** O que rende e
cobrir os casos em que ele erra, e o angulo da camera, que mudou mais o
resultado do que qualquer treino nesta base.

## Ensinar pelo erro (o dado mais caro)

Quando um alerta de queda dispara e nao houve queda, o alerta tem um link
**"foi engano"**. Clicar guarda a JANELA EXATA que causou aquele alerta como
exemplo de "aqui nao houve queda", com o rotulo `engano`.

Isso vale mais que gravar horas de atividade normal: o modelo so erra em
situacoes especificas, e horas de gravacao comum podem nao conter uma unica.
Um clique num alerta errado produz exatamente o exemplo que falta.

Medido nesta base: a quantidade satura (veja curva.py), a cobertura nao. Vinte
janelas de erro valem mais que duzentas gravacoes genericas.

## Aproveitar video que ja existe

    uv run treino/video.py queda caminho/do/video.mp4
    uv run treino/video.py normal "C:/videos/*.mp4"

Usa o MESMO detector de pose da Sala e escreve no MESMO arquivo, entao o
resultado e indistinguivel do botao "Gravar amostra". Do video sai apenas
geometria do esqueleto; nenhum quadro e guardado.

**So vale se o video vier da camera que vai ser usada, no lugar onde ela vai
ficar.** Video de celular tem outra lente, outra altura e outro angulo —
treinar com ele ensina a camera errada, que e exatamente o erro que custou um
dia inteiro neste projeto.

## Cuidar das gravacoes

    uv run treino/local.py --listar          # numera todas
    uv run treino/local.py --apagar 2,5      # apaga por numero
    uv run treino/local.py --apagar deitar   # apaga por rotulo
    uv run treino/local.py --apagar tudo     # recomeca do zero

Mexeu na posicao da camera? **Apague o que foi gravado antes.** Gravacao da
posicao antiga ensina a posicao antiga, e ainda estraga a medicao, porque o
teste passa a conter duas cameras diferentes.

O arquivo anterior fica como `amostras.jsonl.anterior`, caso tenha sido engano.

## Reproduzir do zero

```bash
# 1. baixar os keypoints (precisa de unrar; os arquivos são RAR5)
#    ids em treino/extrair.py, via https://dataverse.harvard.edu/api/access/datafile/<id>

# 2. extrair as janelas  (~1 min)
DADOS=/caminho/dos/csv uv run treino/extrair.py

# 3. treinar  (~8 s, CPU, só numpy)
uv run treino/treinar.py

# 4. gerar as provas do porte para JS
DADOS=/caminho/dos/csv uv run treino/provas.py

# 5. conferir que o JavaScript calcula o mesmo que o Python
node testes/rede-queda.mjs
```

`janelas.npz` (2 MB) está no repositório: são as janelas já extraídas, então
os passos 3 a 5 rodam sem baixar os 284 MB.

## O desenho, e por que cada escolha

**12 entradas, todas adimensionais.** Razões: alturas de corpo, frações do
próprio máximo, graus sobre 90. Um modelo treinado nos pixels de outra sala,
com outra câmera e outra distância, não serviria para a de vocês. Em razões,
serve.

**Rótulo fraco.** O dataset diz "este clipe TEM uma queda", não diz em que
quadro. O treino agrega por clipe: a nota do clipe é a maior entre as janelas
dele. Um clipe sem queda empurra **todas** as janelas para baixo; um com queda
só exige que **uma** passe. É exatamente como a Sala decide ao vivo.

**Teste por cenário inteiro, não por clipe.** Duas pastas inteiras ficaram de
fora do treino. Separar por clipe deixaria quadros do mesmo cenário dos dois
lados e a nota sairia otimista.

**Limiar escolhido no treino.** Escolher no teste é decorar a prova.

## O que o teste JS trava

`testes/rede-queda.mjs` pega 30 janelas reais do dataset, refaz o caminho
inteiro em JavaScript e compara com o Python número a número. Existe porque
divergência entre as duas implementações **não dá erro**: dá número plausível e
errado. Já aconteceu nesta base de código.

## Limites honestos

- Revocação de 89% quer dizer **1 em cada 9 quedas passa despercebida**. Isso
  não é um detector infalível e a tela não promete que seja.
- O dataset é de quedas **encenadas**, em ambientes interiores. Uma queda real
  de um aluno numa quadra pode não se parecer com nada disso.
- Nada foi medido na câmera de vocês. Os números aqui são do dataset.
- Como todo o resto do projeto: **alerta não é acusação**. O evento chama uma
  pessoa para olhar.
