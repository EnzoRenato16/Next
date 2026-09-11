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

## Reproduzir do zero

```bash
# 1. baixar os keypoints (precisa de unrar; os arquivos são RAR5)
#    ids em treino/extrair.py, via https://dataverse.harvard.edu/api/access/datafile/<id>

# 2. extrair as janelas  (~1 min)
DADOS=/caminho/dos/csv python3 treino/extrair.py

# 3. treinar  (~8 s, CPU, só numpy)
python3 treino/treinar.py

# 4. gerar as provas do porte para JS
DADOS=/caminho/dos/csv python3 treino/provas.py

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
